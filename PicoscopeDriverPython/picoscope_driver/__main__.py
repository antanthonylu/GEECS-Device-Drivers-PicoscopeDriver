"""Command-line entry point: ``python -m picoscope_driver [--config config.toml]``."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from .config import DriverConfig
from .device import PicoscopeDevice
from .geecs_server import GeecsDeviceServer
from .hardware import MockPicoscopeHardware, make_ps3000a_hardware

logger = logging.getLogger("picoscope_driver")


def _build_device(config: DriverConfig) -> PicoscopeDevice:
    hardware = MockPicoscopeHardware() if config.use_mock_hardware else make_ps3000a_hardware()
    return PicoscopeDevice(
        device_name=config.device_name,
        hardware=hardware,
        serial=config.serial,
        save_directory=config.save_directory,
    )


async def run(config: DriverConfig) -> None:
    device = _build_device(config)
    device.initialize()

    server = GeecsDeviceServer(
        device_name=config.device_name,
        store=device,
        host=config.host,
        port=config.port,
        push_hz=config.push_hz,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # Windows: Ctrl+C still raises KeyboardInterrupt.

    async with server:
        logger.info(
            "%s serving on %s:%s (%s hardware)",
            config.device_name,
            server.host,
            server.port,
            "mock" if config.use_mock_hardware else "PicoScope 3000A",
        )
        try:
            await stop_event.wait()
        except KeyboardInterrupt:
            pass

    device.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="picoscope_driver")
    parser.add_argument("--config", type=str, default=None, help="path to a TOML config file")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    config = DriverConfig.from_toml(args.config) if args.config else DriverConfig()
    asyncio.run(run(config))


if __name__ == "__main__":
    main()
