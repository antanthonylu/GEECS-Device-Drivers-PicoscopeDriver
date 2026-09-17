"""A Python-native GEECS device driver for the PicoScope 3000A series.

Replaces the LabVIEW ``PicoscopeV2`` driver's role in front of GEECS Master
Control: it speaks the same UDP/TCP wire protocol (:mod:`.wire`,
:mod:`.geecs_server`) and drives the oscilloscope through either PicoTech's
PicoSDK (:mod:`.hardware.ps3000a`) or a hardware-free mock
(:mod:`.hardware.mock`) for development.
"""

from .device import PicoscopeDevice, Trace
from .geecs_server import GeecsDeviceServer

__all__ = ["PicoscopeDevice", "Trace", "GeecsDeviceServer"]
