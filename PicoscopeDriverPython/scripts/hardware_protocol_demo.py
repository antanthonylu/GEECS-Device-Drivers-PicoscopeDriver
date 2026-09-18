#!/usr/bin/env python3
"""End-to-end check: drive the PicoScope exactly the way Master Control will.

Unlike ``hardware_smoke_test.py`` (which talks to the hardware directly),
this script starts the real :class:`~picoscope_driver.geecs_server.GeecsDeviceServer`
and a :class:`~picoscope_driver.device.PicoscopeDevice`, then talks to them
purely over the GEECS UDP/TCP wire protocol using
:class:`~picoscope_driver.client.GeecsClient` — the same commands
(``setChannelA Enabled>>1``, ``setAcquire>>1``, ...) Master Control itself
sends. It runs both sides in one process for convenience; the protocol
traffic between them is exactly what would cross the network to a real
Master Control instance.

Usage::

    python scripts/hardware_protocol_demo.py
    python scripts/hardware_protocol_demo.py --channel B --range 2.0
    python scripts/hardware_protocol_demo.py --mock       # no hardware; sanity-checks this script itself
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from picoscope_driver.client import GeecsClient  # noqa: E402
from picoscope_driver.device import PicoscopeDevice  # noqa: E402
from picoscope_driver.geecs_server import GeecsDeviceServer  # noqa: E402
from picoscope_driver.hardware.base import VOLTAGE_RANGES_V  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--channel", default="A", choices=["A", "B", "C", "D"])
    parser.add_argument("--range", type=float, default=1.0, dest="range_v", choices=VOLTAGE_RANGES_V)
    parser.add_argument("--coupling", default="DC", choices=["AC", "DC"])
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--serial", default=None, help="unit serial; omit if only one unit is attached")
    parser.add_argument("--mock", action="store_true", help="use the mock backend instead of real hardware")
    parser.add_argument("--save-dir", default="./data", help="directory the driver saves acquired CSVs into")
    parser.add_argument("--out", default="protocol_demo.png", help="where to save the plot PNG")
    parser.add_argument("--no-plot", action="store_true")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    device_name = "U_TestPicoscope3000A"

    if args.mock:
        from picoscope_driver.hardware.mock import MockPicoscopeHardware

        hardware = MockPicoscopeHardware(seed=0)
    else:
        try:
            from picoscope_driver.hardware.ps3000a import Ps3000aHardware
        except ImportError:
            print(
                "Could not import picosdk. Install it with:\n"
                "    pip install -e '.[hardware]'",
                file=sys.stderr,
            )
            return 1
        hardware = Ps3000aHardware()

    device = PicoscopeDevice(device_name, hardware, serial=args.serial, save_directory=args.save_dir)

    print("Initializing device (opens the hardware)...")
    try:
        device.initialize()
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED to initialize: {exc}", file=sys.stderr)
        print(
            "\nIs the native PicoScope software still open? PicoSDK only allows\n"
            "one process to hold the unit at a time.",
            file=sys.stderr,
        )
        return 1

    server = GeecsDeviceServer(device_name, device, host="127.0.0.1", port=0)
    await server.start()
    print(f"GeecsDeviceServer listening on {server.host}:{server.port} "
          f"(this is what Master Control would dial)")

    client = GeecsClient(server.host, server.port)
    await client.connect()

    try:
        print("\n--- sending the same commands Master Control would ---")
        for var, value in [
            (f"Channel{args.channel} Enabled", 1),
            (f"Channel{args.channel} Range (V)", args.range_v),
            (f"Channel{args.channel} Coupling", args.coupling),
            ("Number of Samples", args.samples),
        ]:
            confirmed = await client.set(var, value)
            print(f"  set{var}>>{value}  ->  confirmed {confirmed!r}")

        print("\n  setAcquire>>1 ...")
        shot = await client.set("Acquire", 1)
        print(f"  -> shot number is now {shot}")

        print("  setSave>>1 ...")
        await client.set("Save", 1)
        save_path = await client.get("Last Save Path")
        print(f"  -> saved to {save_path}")

        print("\n--- a short live subscription, exactly like a scan's Wait>> ---")
        reader = await client.subscribe(["shotnumber", "status"])
        try:
            for _ in range(3):
                message = await reader.read_one()
                print(f"  pushed: {message}")
        finally:
            await reader.close()
    finally:
        await client.close()
        await server.stop()
        device.close()

    if not args.no_plot and save_path:
        _plot_csv(save_path, args.channel, args.out)

    print("\nDone.")
    return 0


def _plot_csv(csv_path: str, channel: str, out_path: str) -> None:
    try:
        from _plot_backend import select_backend

        interactive = select_backend()
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("matplotlib isn't installed, skipping the plot (pip install -e '.[viz]').")
        return

    data = np.genfromtxt(csv_path, delimiter=",", names=True)
    time_us = data["time_s"] * 1e6
    column = f"channel_{channel}_v"
    if column not in data.dtype.names:
        print(f"'{column}' not found in {csv_path}; columns are {data.dtype.names}")
        return
    volts = data[column]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(time_us, volts, linewidth=1)
    ax.set_xlabel("time (us, relative to trigger)")
    ax.set_ylabel("voltage (V)")
    ax.set_title(f"PicoScope 3000A - Channel {channel} - via GEECS protocol - {csv_path}")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    print(f"Saved plot to {out_path}")
    if interactive:
        plt.show()
    else:
        print("(no GUI backend available here — open the PNG file to view it)")


def main() -> int:
    args = parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
