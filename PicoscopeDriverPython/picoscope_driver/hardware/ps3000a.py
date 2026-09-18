"""Real hardware backend for the PicoScope 3000A series, via PicoTech's PicoSDK.

Requires the ``picosdk`` Python package (PyPI) *and* the native PicoSDK
driver (``ps3000a.dll`` / ``libps3000a.so``) to be installed on the host —
see PicoTech's PicoSDK downloads. Both imports below are deferred into
:meth:`Ps3000aHardware.open` so that importing this module — and the rest of
the driver — works on a machine with no PicoSDK installed, which is what
lets :mod:`picoscope_driver.hardware.mock` stand in during development.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time

import numpy as np

from .base import (
    AcquisitionSettings,
    ChannelSettings,
    PicoscopeHardware,
    TriggerSettings,
    VOLTAGE_RANGES_V,
    voltage_range_index,
)

_POLL_INTERVAL_S = 0.01


def _prioritize_64bit_picosdk_on_path() -> None:
    """Put the 64-bit PicoSDK's lib directory at the front of this process's PATH.

    Some Windows machines end up with both the 64-bit PicoSDK (a standalone
    install, under ``Program Files``) and an older 32-bit copy bundled with
    the native PicoScope application (under ``Program Files (x86)``) on
    ``PATH`` at once. ``ctypes.util.find_library`` — what PicoSDK's Python
    wrapper uses — returns whichever comes first, which can be the 32-bit
    one even under a 64-bit Python process. That produces a cryptic
    ``WinError 193: %1 is not a valid Win32 application`` instead of a
    clear "wrong architecture" message (observed on a real lab machine).

    This only changes ``PATH`` for this Python process, not the system-wide
    or user-wide environment variable, so it can't affect the native
    PicoScope application or anything else on the machine.
    """
    if sys.platform != "win32":
        return
    program_files = os.environ.get("ProgramW6432") or os.environ.get(
        "ProgramFiles", r"C:\Program Files"
    )
    lib_dir = os.path.join(program_files, "Pico Technology", "SDK", "lib")
    if not os.path.isdir(lib_dir):
        return
    # PicoSDK's own find_library() re-scans os.environ["PATH"] at call time
    # (it's a plain Python directory walk, not a delegated OS LoadLibrary
    # search), so this ordering fix is what actually picks the right DLL.
    os.environ["PATH"] = lib_dir + os.pathsep + os.environ.get("PATH", "")
    # Belt-and-suspenders: also register it as a DLL search directory, in
    # case ps3000a.dll has its own same-folder dependencies that Python
    # 3.8+'s safe DLL loading would otherwise fail to resolve.
    try:
        os.add_dll_directory(lib_dir)
    except (AttributeError, OSError):
        pass


class Ps3000aHardware(PicoscopeHardware):
    """Drives a real PicoScope 3000A unit through ``picosdk.ps3000a``."""

    def __init__(self) -> None:
        self._ps = None
        self._assert_pico_ok = None
        self._handle: "ctypes.c_int16 | None" = None
        self._max_adc = ctypes.c_int16(0)
        self._channel_range_index: dict[str, int | None] = {}

    def open(self, serial: str | None = None) -> None:
        _prioritize_64bit_picosdk_on_path()
        from picosdk.functions import assert_pico_ok
        from picosdk.ps3000a import ps3000a as ps

        self._ps = ps
        self._assert_pico_ok = assert_pico_ok

        handle = ctypes.c_int16()
        status = ps.ps3000aOpenUnit(
            ctypes.byref(handle), serial.encode("ascii") if serial else None
        )
        assert_pico_ok(status)
        self._handle = handle

        max_adc = ctypes.c_int16()
        assert_pico_ok(ps.ps3000aMaximumValue(self._handle, ctypes.byref(max_adc)))
        self._max_adc = max_adc

    def close(self) -> None:
        if self._handle is None:
            return
        ps, assert_pico_ok = self._ps, self._assert_pico_ok
        assert ps is not None and assert_pico_ok is not None
        assert_pico_ok(ps.ps3000aStop(self._handle))
        assert_pico_ok(ps.ps3000aCloseUnit(self._handle))
        self._handle = None

    def _require_open(self):
        if self._handle is None:
            raise RuntimeError("PicoScope is not open; call open() first")
        assert self._ps is not None and self._assert_pico_ok is not None
        return self._ps, self._assert_pico_ok

    def set_channel(self, channel: str, settings: ChannelSettings) -> None:
        ps, assert_pico_ok = self._require_open()
        channel_index = ps.PICO_CHANNEL[channel]

        if not settings.enabled:
            assert_pico_ok(
                ps.ps3000aSetChannel(
                    self._handle, channel_index, 0, ps.PICO_COUPLING["DC"], 0, 0.0
                )
            )
            self._channel_range_index[channel] = None
            return

        range_index = voltage_range_index(settings.range_v)
        coupling_index = ps.PICO_COUPLING[settings.coupling]
        assert_pico_ok(
            ps.ps3000aSetChannel(
                self._handle,
                channel_index,
                1,
                coupling_index,
                range_index,
                settings.offset_v,
            )
        )
        self._channel_range_index[channel] = range_index

    def set_trigger(self, trigger: TriggerSettings) -> None:
        ps, assert_pico_ok = self._require_open()
        channel_index = ps.PICO_CHANNEL[trigger.channel]

        if not trigger.enabled:
            assert_pico_ok(
                ps.ps3000aSetSimpleTrigger(
                    self._handle,
                    0,
                    channel_index,
                    0,
                    ps.PS3000A_THRESHOLD_DIRECTION["PS3000A_RISING"],
                    0,
                    0,
                )
            )
            return

        range_index = self._channel_range_index.get(trigger.channel)
        if range_index is None:
            raise RuntimeError(
                f"trigger channel {trigger.channel} must be enabled via "
                "set_channel() before the trigger is configured"
            )
        from picosdk.functions import mV2adc

        threshold_adc = mV2adc(trigger.threshold_v * 1000.0, range_index, self._max_adc)
        direction_name = "PS3000A_RISING" if trigger.direction == "RISING" else "PS3000A_FALLING"
        assert_pico_ok(
            ps.ps3000aSetSimpleTrigger(
                self._handle,
                1,
                channel_index,
                threshold_adc,
                ps.PS3000A_THRESHOLD_DIRECTION[direction_name],
                trigger.delay_samples,
                trigger.auto_trigger_ms,
            )
        )

    def get_timebase_interval_ns(self, timebase: int, num_samples: int) -> float:
        ps, assert_pico_ok = self._require_open()
        interval_ns = ctypes.c_float()
        max_samples = ctypes.c_int32()
        assert_pico_ok(
            ps.ps3000aGetTimebase2(
                self._handle,
                timebase,
                num_samples,
                ctypes.byref(interval_ns),
                0,
                ctypes.byref(max_samples),
                0,
            )
        )
        return float(interval_ns.value)

    def run_block(self, acquisition: AcquisitionSettings) -> None:
        ps, assert_pico_ok = self._require_open()
        post_trigger_samples = acquisition.num_samples - acquisition.pre_trigger_samples
        time_indisposed_ms = ctypes.c_int32()
        assert_pico_ok(
            ps.ps3000aRunBlock(
                self._handle,
                acquisition.pre_trigger_samples,
                post_trigger_samples,
                acquisition.timebase,
                1,
                ctypes.byref(time_indisposed_ms),
                0,
                None,
                None,
            )
        )
        ready = ctypes.c_int16(0)
        while ready.value == 0:
            assert_pico_ok(ps.ps3000aIsReady(self._handle, ctypes.byref(ready)))
            if ready.value == 0:
                time.sleep(_POLL_INTERVAL_S)

    def get_values_v(self, channel: str, acquisition: AcquisitionSettings) -> np.ndarray:
        ps, assert_pico_ok = self._require_open()
        range_index = self._channel_range_index.get(channel)
        if range_index is None:
            return np.zeros(acquisition.num_samples)

        channel_index = ps.PICO_CHANNEL[channel]
        buffer = (ctypes.c_int16 * acquisition.num_samples)()
        assert_pico_ok(
            ps.ps3000aSetDataBuffer(
                self._handle,
                channel_index,
                ctypes.byref(buffer),
                acquisition.num_samples,
                0,
                0,
            )
        )

        num_samples_collected = ctypes.c_uint32(acquisition.num_samples)
        overflow = ctypes.c_int16()
        assert_pico_ok(
            ps.ps3000aGetValues(
                self._handle,
                0,
                ctypes.byref(num_samples_collected),
                1,
                0,
                0,
                ctypes.byref(overflow),
            )
        )

        counts = np.frombuffer(
            buffer, dtype=np.int16, count=num_samples_collected.value
        )
        full_scale_v = VOLTAGE_RANGES_V[range_index]
        return counts.astype(np.float64) / self._max_adc.value * full_scale_v
