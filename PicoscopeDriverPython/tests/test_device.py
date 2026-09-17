import numpy as np
import pytest

from picoscope_driver.device import PicoscopeDevice
from picoscope_driver.hardware.mock import MockPicoscopeHardware


@pytest.fixture
def device(tmp_path):
    hardware = MockPicoscopeHardware(seed=42)
    dev = PicoscopeDevice("U_TestPicoscope", hardware, save_directory=tmp_path)
    dev.initialize()
    yield dev
    dev.close()


def test_acquire_requires_initialize() -> None:
    hardware = MockPicoscopeHardware()
    dev = PicoscopeDevice("U_TestPicoscope", hardware)
    with pytest.raises(RuntimeError):
        dev.acquire()


def test_acquire_returns_only_enabled_channels(device) -> None:
    assert device.try_set("ChannelA Enabled", 1) is None
    traces = device.acquire()
    assert set(traces) == {"A"}
    assert len(traces["A"].volts) == device.try_get("Number of Samples")[0]


def test_acquire_shape_matches_settings(device) -> None:
    device.try_set("ChannelB Enabled", 1)
    device.try_set("Number of Samples", 500)
    traces = device.acquire()
    assert traces["B"].volts.shape == (500,)
    assert traces["B"].time_s.shape == (500,)


def test_set_bad_range_is_rejected(device) -> None:
    error = device.try_set("ChannelA Range (V)", 3.7)
    assert error is not None


def test_save_writes_csv(device) -> None:
    device.try_set("ChannelA Enabled", 1)
    device.acquire()
    path = device.save()
    assert path is not None
    assert path.exists()
    contents = path.read_text()
    assert "channel_A_v" in contents.splitlines()[0]


def test_save_without_acquire_returns_none(device) -> None:
    assert device.save() is None


def test_unknown_variable_get() -> None:
    hardware = MockPicoscopeHardware()
    dev = PicoscopeDevice("U_TestPicoscope", hardware)
    value, error = dev.try_get("NotReal")
    assert value is None
    assert error == "unknown variable"


def test_trigger_settings_round_trip(device) -> None:
    device.try_set("Trigger Channel", "b")
    assert device.try_get("Trigger Channel") == ("B", None)
