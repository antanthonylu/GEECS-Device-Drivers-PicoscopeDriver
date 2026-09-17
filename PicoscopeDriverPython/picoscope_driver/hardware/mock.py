"""Hardware-free double for :class:`PicoscopeHardware`.

Generates a synthetic pulse (a Gaussian bump plus noise) on every enabled
channel so the rest of the driver — settings validation, the GEECS wire
protocol, saving — can be developed and tested without a physical PicoScope
or PicoSDK installed. This is the backend selected when no real unit is
requested (see :mod:`picoscope_driver.config`).
"""

from __future__ import annotations

import numpy as np

from .base import AcquisitionSettings, ChannelSettings, PicoscopeHardware, TriggerSettings


class MockPicoscopeHardware(PicoscopeHardware):
    """Simulates a 4-channel PicoScope well enough to exercise the driver."""

    def __init__(self, noise_v: float = 0.01, seed: int | None = None) -> None:
        self._noise_v = noise_v
        self._rng = np.random.default_rng(seed)
        self._is_open = False
        self._channels: dict[str, ChannelSettings] = {}
        self._trigger = TriggerSettings()

    def open(self, serial: str | None = None) -> None:
        self._is_open = True

    def close(self) -> None:
        self._is_open = False

    def _require_open(self) -> None:
        if not self._is_open:
            raise RuntimeError("mock hardware is not open; call open() first")

    def set_channel(self, channel: str, settings: ChannelSettings) -> None:
        self._require_open()
        self._channels[channel] = settings

    def set_trigger(self, trigger: TriggerSettings) -> None:
        self._require_open()
        self._trigger = trigger

    def get_timebase_interval_ns(self, timebase: int, num_samples: int) -> float:
        # ps3000a timebase 0-2 are fixed fast rates; from 3 up it is
        # (timebase - 2) / 125e6 seconds. Reproduced here only so mock and
        # real backends report comparable sample intervals for a given
        # timebase index.
        if timebase <= 2:
            return (2.0**timebase) / 5.0
        return (timebase - 2) * 8.0

    def run_block(self, acquisition: AcquisitionSettings) -> None:
        self._require_open()
        self._last_acquisition = acquisition

    def get_values_v(self, channel: str, acquisition: AcquisitionSettings) -> np.ndarray:
        self._require_open()
        settings = self._channels.get(channel)
        if settings is None or not settings.enabled:
            return np.zeros(acquisition.num_samples)

        sample_index = np.arange(acquisition.num_samples) - acquisition.pre_trigger_samples
        pulse_width = max(acquisition.num_samples // 40, 1)
        pulse = 0.5 * settings.range_v * np.exp(-0.5 * (sample_index / pulse_width) ** 2)
        noise = self._rng.normal(0.0, self._noise_v, acquisition.num_samples)
        trace = settings.offset_v + pulse + noise
        limit = settings.range_v
        return np.clip(trace, -limit, limit)
