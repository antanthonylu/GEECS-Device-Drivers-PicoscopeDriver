"""Oscilloscope hardware backends: a real PicoScope 3000A and a mock double."""

from .base import (
    CHANNELS,
    COUPLINGS,
    TRIGGER_DIRECTIONS,
    VOLTAGE_RANGES_V,
    AcquisitionSettings,
    ChannelSettings,
    PicoscopeHardware,
    TriggerSettings,
    voltage_range_index,
)
from .mock import MockPicoscopeHardware

__all__ = [
    "CHANNELS",
    "COUPLINGS",
    "TRIGGER_DIRECTIONS",
    "VOLTAGE_RANGES_V",
    "AcquisitionSettings",
    "ChannelSettings",
    "PicoscopeHardware",
    "TriggerSettings",
    "voltage_range_index",
    "MockPicoscopeHardware",
]


def make_ps3000a_hardware() -> PicoscopeHardware:
    """Construct the real PicoScope 3000A backend (imported lazily).

    Kept out of the package's eager imports so that importing
    ``picoscope_driver`` never requires PicoSDK to be installed.
    """
    from .ps3000a import Ps3000aHardware

    return Ps3000aHardware()
