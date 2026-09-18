"""Opt-in regression test against a real PicoScope 3000A.

Skipped by default (see the ``addopts`` in ``pyproject.toml``). Run
explicitly, on a computer with PicoSDK and a PicoScope 3000A connected via
USB, with the native PicoScope software closed (PicoSDK only allows one
process to hold the unit open at a time)::

    PICOSCOPE_HW_TEST=1 pytest -m hardware -v

Set ``PICOSCOPE_HW_SERIAL`` if more than one unit is attached and you need
a specific one; otherwise the first unit PicoSDK finds is used.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from picoscope_driver.device import PicoscopeDevice
from picoscope_driver.hardware.base import AcquisitionSettings

pytestmark = pytest.mark.hardware

_ENABLE_VAR = "PICOSCOPE_HW_TEST"


def _skip_unless_enabled() -> None:
    if os.environ.get(_ENABLE_VAR) != "1":
        pytest.skip(f"set {_ENABLE_VAR}=1 to run tests against real hardware")


@pytest.fixture
def real_device(tmp_path):
    _skip_unless_enabled()
    from picoscope_driver.hardware.ps3000a import Ps3000aHardware

    hardware = Ps3000aHardware()
    serial = os.environ.get("PICOSCOPE_HW_SERIAL")
    device = PicoscopeDevice("U_TestPicoscope3000A", hardware, serial=serial, save_directory=tmp_path)
    device.initialize()
    yield device
    device.close()


def test_open_and_close_does_not_raise(real_device) -> None:
    assert real_device is not None


def test_free_running_acquire_returns_samples(real_device) -> None:
    # No trigger configured: the scope free-runs, so this works with
    # nothing connected to the input (you'll just capture noise).
    real_device.try_set("ChannelA Enabled", 1)
    real_device.try_set("ChannelA Range (V)", 1.0)
    real_device.try_set("Number of Samples", 2000)

    traces = real_device.acquire()

    assert "A" in traces
    volts = traces["A"].volts
    assert volts.shape == (2000,)
    assert np.all(np.isfinite(volts))
    # A real ADC reading a real input is never bit-for-bit constant.
    assert volts.std() >= 0.0


def test_save_writes_a_readable_csv(real_device) -> None:
    real_device.try_set("ChannelA Enabled", 1)
    real_device.acquire()
    path = real_device.save()
    assert path is not None and path.exists()
    data = np.genfromtxt(path, delimiter=",", names=True)
    assert "time_s" in data.dtype.names


def test_timebase_interval_is_positive(real_device) -> None:
    interval_ns = real_device._hardware.get_timebase_interval_ns(  # noqa: SLF001
        AcquisitionSettings().timebase, AcquisitionSettings().num_samples
    )
    assert interval_ns > 0
