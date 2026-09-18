import pytest

from picoscope_driver.device import PicoscopeDevice
from picoscope_driver.geecs_server import GeecsDeviceServer
from picoscope_driver.hardware.mock import MockPicoscopeHardware

from .geecs_test_client import GeecsCommandError, GeecsTestClient


@pytest.fixture
async def running_device():
    hardware = MockPicoscopeHardware(seed=1234)
    device = PicoscopeDevice("U_TestPicoscope", hardware, save_directory="/tmp")
    device.initialize()
    server = GeecsDeviceServer("U_TestPicoscope", device, host="127.0.0.1", port=0)
    await server.start()
    client = GeecsTestClient(server.host, server.port)
    await client.connect()
    try:
        yield device, server, client
    finally:
        await client.close()
        await server.stop()
        device.close()


async def test_get_status(running_device) -> None:
    _device, _server, client = running_device
    assert await client.get("status") == "idle"


async def test_set_and_get_channel_enabled(running_device) -> None:
    _device, _server, client = running_device
    assert await client.set("ChannelA Enabled", 1) == 1
    assert await client.get("ChannelA Enabled") == 1


async def test_set_rejects_unknown_variable(running_device) -> None:
    _device, _server, client = running_device
    with pytest.raises(GeecsCommandError, match="unknown variable"):
        await client.set("NotARealVariable", 1)


async def test_set_rejects_bad_voltage_range(running_device) -> None:
    _device, _server, client = running_device
    with pytest.raises(GeecsCommandError):
        await client.set("ChannelA Range (V)", 3.7)


async def test_acquire_increments_shotnumber(running_device) -> None:
    _device, _server, client = running_device
    await client.set("ChannelA Enabled", 1)
    before = await client.get("shotnumber")
    await client.set("Acquire", 1)
    after = await client.get("shotnumber")
    assert after == before + 1


async def test_save_over_protocol(running_device) -> None:
    _device, _server, client = running_device
    await client.set("ChannelA Enabled", 1)
    await client.set("Acquire", 1)
    await client.set("Save", 1)
    saved_path = await client.get("Last Save Path")
    assert saved_path


async def test_subscription_push(running_device) -> None:
    _device, _server, client = running_device
    await client.set("ChannelA Enabled", 1)
    await client.set("Acquire", 1)

    reader = await client.subscribe(["status", "shotnumber"])
    try:
        message = await reader.read_one()
        device_name, shot, rest = message.split(">>", 2)
        assert device_name == "U_TestPicoscope"
        assert int(shot) >= 0
        assert "status nval,idle nvar" in rest
    finally:
        await reader.close()
