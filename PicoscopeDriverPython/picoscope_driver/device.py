"""Ties settings, hardware and the GEECS wire protocol together.

``PicoscopeDevice`` mirrors the lifecycle of the LabVIEW
``PicoscopeV2.lvclass`` driver it replaces (``Initialize.vi``,
``Configure.vi``, ``Acquire.vi``, ``Save.vi``, ``Close.vi``) and structurally
implements :class:`picoscope_driver.geecs_server.VariableStore`, so an
instance can be handed straight to a
:class:`~picoscope_driver.geecs_server.GeecsDeviceServer` and driven by
Master Control's ``get``/``set``/``Wait`` commands exactly like the LabVIEW
driver it replaces.

Variable naming is this driver's own choice (there is no machine-readable
export of the LabVIEW driver's variable list to match against) and must be
mirrored in whatever the lab registers for this device in the GEECS
experiment database before Master Control can address it — see
``docs/PROTOCOL.md``.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .hardware.base import (
    CHANNELS,
    COUPLINGS,
    TRIGGER_DIRECTIONS,
    AcquisitionSettings,
    ChannelSettings,
    PicoscopeHardware,
    TriggerSettings,
    voltage_range_index,
)

logger = logging.getLogger(__name__)

Getter = Callable[[], Any]
Setter = Callable[[Any], "str | None"]


@dataclass
class Trace:
    """One channel's captured waveform."""

    channel: str
    time_s: np.ndarray
    volts: np.ndarray


def _validate_bool(value: Any) -> bool:
    return bool(int(value))


def _validate_float(value: Any) -> float:
    return float(value)


def _validate_int(minimum: int | None = None) -> Callable[[Any], int]:
    def validate(value: Any) -> int:
        parsed = int(value)
        if minimum is not None and parsed < minimum:
            raise ValueError(f"value {parsed} is below the minimum of {minimum}")
        return parsed

    return validate


def _validate_choice(choices: tuple[str, ...]) -> Callable[[Any], str]:
    def validate(value: Any) -> str:
        text = str(value).strip().upper()
        if text not in choices:
            raise ValueError(f"{value!r} is not one of {choices}")
        return text

    return validate


def _validate_range_v(value: Any) -> float:
    parsed = float(value)
    voltage_range_index(parsed)  # raises ValueError for an unsupported range
    return parsed


class PicoscopeDevice:
    """The picoscope's GEECS-facing state machine."""

    def __init__(
        self,
        device_name: str,
        hardware: PicoscopeHardware,
        serial: str | None = None,
        save_directory: Path | str = ".",
    ) -> None:
        self.device_name = device_name
        self._hardware = hardware
        self._serial = serial
        self._save_directory = Path(save_directory)
        self._lock = threading.Lock()

        self._channels: dict[str, ChannelSettings] = {c: ChannelSettings() for c in CHANNELS}
        self._trigger = TriggerSettings()
        self._acquisition = AcquisitionSettings()

        self._is_open = False
        self._shot_number = 0
        self._status = "idle"
        self._last_traces: dict[str, Trace] = {}
        self._last_save_path = ""

        self._variables: dict[str, tuple[Getter, Setter]] = {}
        self._register_variables()

    # -- lifecycle, mirrors PicoscopeV2.lvclass -----------------------------

    def initialize(self) -> None:
        """Open the hardware and push the current settings (``Initialize.vi``)."""
        self._hardware.open(self._serial)
        self._is_open = True
        self._apply_settings()
        self._status = "idle"
        logger.info("%s: initialized", self.device_name)

    def configure(self) -> None:
        """Re-apply channel/trigger settings to the open hardware (``Configure.vi``)."""
        self._require_open()
        self._apply_settings()

    def _apply_settings(self) -> None:
        for channel, settings in self._channels.items():
            self._hardware.set_channel(channel, settings)
        self._hardware.set_trigger(self._trigger)

    def acquire(self) -> dict[str, Trace]:
        """Apply pending settings and run one block capture (``Acquire.vi``)."""
        self._require_open()
        with self._lock:
            self._status = "acquiring"
            try:
                self._apply_settings()
                self._hardware.run_block(self._acquisition)
                time_axis = self._hardware.get_time_axis_s(self._acquisition)
                traces: dict[str, Trace] = {}
                for channel, settings in self._channels.items():
                    if not settings.enabled:
                        continue
                    volts = self._hardware.get_values_v(channel, self._acquisition)
                    traces[channel] = Trace(channel, time_axis, volts)
                self._last_traces = traces
                self._shot_number += 1
            finally:
                self._status = "idle"
        logger.debug(
            "%s: acquired shot %d (%d channels)",
            self.device_name,
            self._shot_number,
            len(self._last_traces),
        )
        return self._last_traces

    def save(self) -> Path | None:
        """Write the most recent traces to disk as CSV (``Save.vi``)."""
        if not self._last_traces:
            return None
        self._save_directory.mkdir(parents=True, exist_ok=True)
        path = self._save_directory / f"{self.device_name}_shot{self._shot_number:05d}.csv"
        ordered_channels = sorted(self._last_traces)
        columns = ["time_s"] + [f"channel_{c}_v" for c in ordered_channels]
        time_axis = self._last_traces[ordered_channels[0]].time_s
        data = np.column_stack(
            [time_axis] + [self._last_traces[c].volts for c in ordered_channels]
        )
        np.savetxt(path, data, delimiter=",", header=",".join(columns), comments="")
        logger.info("%s: saved shot %d to %s", self.device_name, self._shot_number, path)
        self._last_save_path = str(path)
        return path

    def close(self) -> None:
        """Close the hardware (``Close.vi``)."""
        if self._is_open:
            self._hardware.close()
            self._is_open = False
        self._status = "closed"
        logger.info("%s: closed", self.device_name)

    def _require_open(self) -> None:
        if not self._is_open:
            raise RuntimeError(
                f"{self.device_name}: hardware is not open; call initialize() first"
            )

    # -- GEECS VariableStore protocol ---------------------------------------
    # (see picoscope_driver.geecs_server.VariableStore)

    def try_get(self, variable: str) -> tuple[Any, "str | None"]:
        entry = self._variables.get(variable)
        if entry is None:
            return None, "unknown variable"
        getter, _setter = entry
        return getter(), None

    def try_set(self, variable: str, value: Any) -> "str | None":
        entry = self._variables.get(variable)
        if entry is None:
            return "unknown variable"
        _getter, setter = entry
        try:
            return setter(value)
        except RuntimeError as exc:
            return str(exc)

    def snapshot(self, variables: list[str]) -> tuple[int, dict[str, Any]]:
        values = {}
        for name in variables:
            entry = self._variables.get(name)
            if entry is not None:
                values[name] = entry[0]()
        return self._shot_number, values

    # -- variable registration ------------------------------------------

    def _bind(
        self,
        name: str,
        getter: Getter,
        apply: Callable[[Any], None],
        validate: Callable[[Any], Any] | None = None,
    ) -> None:
        def setter(value: Any) -> "str | None":
            try:
                parsed = validate(value) if validate is not None else value
            except (TypeError, ValueError) as exc:
                return str(exc)
            apply(parsed)
            return None

        self._variables[name] = (getter, setter)

    def _reject_readonly(self, _value: Any) -> str:
        return "variable is read-only"

    def _register_variables(self) -> None:
        self._variables["status"] = (lambda: self._status, self._reject_readonly)
        self._variables["shotnumber"] = (lambda: self._shot_number, self._reject_readonly)

        def do_acquire(value: Any) -> "str | None":
            if not _validate_bool(value):
                return None
            try:
                self.acquire()
            except RuntimeError as exc:
                return str(exc)
            return None

        self._variables["Acquire"] = (lambda: self._shot_number, do_acquire)

        def do_save(value: Any) -> "str | None":
            if not _validate_bool(value):
                return None
            try:
                path = self.save()
            except OSError as exc:
                return str(exc)
            if path is None:
                return "no acquired data to save; call Acquire first"
            return None

        self._variables["Save"] = (lambda: self._last_save_path, do_save)
        self._variables["Last Save Path"] = (lambda: self._last_save_path, self._reject_readonly)

        self._bind(
            "Timebase",
            lambda: self._acquisition.timebase,
            lambda v: setattr(self._acquisition, "timebase", v),
            _validate_int(minimum=0),
        )
        self._bind(
            "Number of Samples",
            lambda: self._acquisition.num_samples,
            lambda v: setattr(self._acquisition, "num_samples", v),
            _validate_int(minimum=1),
        )
        self._bind(
            "Pre-Trigger Samples",
            lambda: self._acquisition.pre_trigger_samples,
            lambda v: setattr(self._acquisition, "pre_trigger_samples", v),
            _validate_int(minimum=0),
        )

        self._bind(
            "Trigger Enabled",
            lambda: int(self._trigger.enabled),
            lambda v: setattr(self._trigger, "enabled", v),
            _validate_bool,
        )
        self._bind(
            "Trigger Channel",
            lambda: self._trigger.channel,
            lambda v: setattr(self._trigger, "channel", v),
            _validate_choice(CHANNELS),
        )
        self._bind(
            "Trigger Threshold (V)",
            lambda: self._trigger.threshold_v,
            lambda v: setattr(self._trigger, "threshold_v", v),
            _validate_float,
        )
        self._bind(
            "Trigger Direction",
            lambda: self._trigger.direction,
            lambda v: setattr(self._trigger, "direction", v),
            _validate_choice(TRIGGER_DIRECTIONS),
        )
        self._bind(
            "Trigger Delay (samples)",
            lambda: self._trigger.delay_samples,
            lambda v: setattr(self._trigger, "delay_samples", v),
            _validate_int(minimum=0),
        )
        self._bind(
            "Trigger Auto Trigger (ms)",
            lambda: self._trigger.auto_trigger_ms,
            lambda v: setattr(self._trigger, "auto_trigger_ms", v),
            _validate_int(minimum=0),
        )

        for channel in CHANNELS:
            self._register_channel_variables(channel)

    def _register_channel_variables(self, channel: str) -> None:
        settings = self._channels[channel]
        self._bind(
            f"Channel{channel} Enabled",
            lambda: int(settings.enabled),
            lambda v: setattr(settings, "enabled", v),
            _validate_bool,
        )
        self._bind(
            f"Channel{channel} Range (V)",
            lambda: settings.range_v,
            lambda v: setattr(settings, "range_v", v),
            _validate_range_v,
        )
        self._bind(
            f"Channel{channel} Coupling",
            lambda: settings.coupling,
            lambda v: setattr(settings, "coupling", v),
            _validate_choice(COUPLINGS),
        )
        self._bind(
            f"Channel{channel} Offset (V)",
            lambda: settings.offset_v,
            lambda v: setattr(settings, "offset_v", v),
            _validate_float,
        )

    @property
    def variable_names(self) -> list[str]:
        """All GEECS variable names this device exposes."""
        return sorted(self._variables)
