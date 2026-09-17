"""Hardware-agnostic interface for a 4-channel block-mode oscilloscope.

Mirrors the settings and lifecycle already used by the LabVIEW
``PicoscopeV2`` driver (``picoscopeInitializeSettings.vi``,
``intialize picoscope trigger settings.vi``,
``picoscopeIndividualChannelSettings.vi``,
``picoscopeInitializeAcquisition.vi``), so the same acquisition model can be
driven by either a real PicoScope 3000A (:mod:`.ps3000a`) or a hardware-free
double (:mod:`.mock`) for development and tests.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

CHANNELS = ("A", "B", "C", "D")

#: Allowed full-scale ranges, volts, in ps3000a PS3000A_RANGE enum order
#: (index N here == PS3000A_RANGE value N on the real hardware).
VOLTAGE_RANGES_V = (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0)

COUPLINGS = ("AC", "DC")
TRIGGER_DIRECTIONS = ("RISING", "FALLING")


def voltage_range_index(range_v: float) -> int:
    """Return the PS3000A_RANGE enum index for *range_v* volts.

    Raises ``ValueError`` if *range_v* is not one of :data:`VOLTAGE_RANGES_V`.
    """
    for index, allowed in enumerate(VOLTAGE_RANGES_V):
        if math.isclose(range_v, allowed, rel_tol=1e-6):
            return index
    raise ValueError(
        f"unsupported voltage range {range_v}V; must be one of {VOLTAGE_RANGES_V}"
    )


@dataclass
class ChannelSettings:
    """One analog channel's configuration."""

    enabled: bool = False
    range_v: float = 1.0
    coupling: str = "DC"
    offset_v: float = 0.0


@dataclass
class TriggerSettings:
    """Simple (single-source, single-threshold) trigger configuration."""

    enabled: bool = False
    channel: str = "A"
    threshold_v: float = 0.0
    direction: str = "RISING"
    delay_samples: int = 0
    auto_trigger_ms: int = 1000


@dataclass
class AcquisitionSettings:
    """Block-mode capture configuration."""

    timebase: int = 8
    num_samples: int = 2000
    pre_trigger_samples: int = 500


class PicoscopeHardware(ABC):
    """Abstract control surface for a block-mode PicoScope acquisition.

    A concrete implementation owns exactly one physical (or simulated) unit
    between :meth:`open` and :meth:`close`.
    """

    @abstractmethod
    def open(self, serial: str | None = None) -> None:
        """Open a connection to the unit, optionally selecting it by serial."""

    @abstractmethod
    def close(self) -> None:
        """Close the connection to the unit."""

    @abstractmethod
    def set_channel(self, channel: str, settings: ChannelSettings) -> None:
        """Apply *settings* to *channel* (one of :data:`CHANNELS`)."""

    @abstractmethod
    def set_trigger(self, trigger: TriggerSettings) -> None:
        """Apply the simple trigger configuration."""

    @abstractmethod
    def get_timebase_interval_ns(self, timebase: int, num_samples: int) -> float:
        """Return the sample interval, in nanoseconds, for *timebase*."""

    @abstractmethod
    def run_block(self, acquisition: AcquisitionSettings) -> None:
        """Arm and run one block capture; blocks until data is ready."""

    @abstractmethod
    def get_values_v(self, channel: str, acquisition: AcquisitionSettings) -> np.ndarray:
        """Return the captured trace for *channel*, in volts."""

    def get_time_axis_s(self, acquisition: AcquisitionSettings) -> np.ndarray:
        """Return the capture's time axis, in seconds, relative to the trigger."""
        interval_ns = self.get_timebase_interval_ns(
            acquisition.timebase, acquisition.num_samples
        )
        sample_index = np.arange(acquisition.num_samples) - acquisition.pre_trigger_samples
        return sample_index * interval_ns * 1e-9

    def __enter__(self) -> "PicoscopeHardware":
        self.open()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
