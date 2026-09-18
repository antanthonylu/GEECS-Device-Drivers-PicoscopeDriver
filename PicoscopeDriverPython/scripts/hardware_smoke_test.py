#!/usr/bin/env python3
"""Standalone check: does this PicoScope 3000A actually respond?

Talks directly to :mod:`picoscope_driver.hardware` — it does not start the
GEECS server or touch the wire protocol at all — so a failure here means
"the PicoSDK/hardware plumbing is broken," separate from "the GEECS
protocol layer is broken" (that's what ``hardware_protocol_demo.py`` checks).

Usage (real hardware, the normal case on the lab computer)::

    python scripts/hardware_smoke_test.py

Nothing needs to be connected to the input for this to work: with no
trigger configured the scope free-runs and you'll just capture noise
around 0 V. To sanity-check against a real signal, connect the scope's
own AWG/probe compensation output (usually 2 kHz, 2 Vpp square wave on
those scopes that have one) to the channel you're testing.

Useful flags::

    python scripts/hardware_smoke_test.py --channel B --range 2.0 --samples 5000
    python scripts/hardware_smoke_test.py --serial "JR628/0017"   # multiple units attached
    python scripts/hardware_smoke_test.py --mock                  # no hardware; sanity-checks this script itself
    python scripts/hardware_smoke_test.py --no-plot                # stats only, no PNG/window
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from picoscope_driver.hardware.base import (  # noqa: E402
    VOLTAGE_RANGES_V,
    AcquisitionSettings,
    ChannelSettings,
    TriggerSettings,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--channel", default="A", choices=["A", "B", "C", "D"])
    parser.add_argument("--range", type=float, default=1.0, dest="range_v", choices=VOLTAGE_RANGES_V)
    parser.add_argument("--coupling", default="DC", choices=["AC", "DC"])
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--pre-trigger-samples", type=int, default=0)
    parser.add_argument("--timebase", type=int, default=8, help="ps3000a timebase index; 8 is a safe default")
    parser.add_argument("--serial", default=None, help="unit serial, e.g. 'JR628/0017'; omit if only one is attached")
    parser.add_argument("--mock", action="store_true", help="use the mock backend instead of real hardware")
    parser.add_argument("--no-plot", action="store_true", help="print stats only; skip the PNG/window")
    parser.add_argument("--out", default="smoke_test.png", help="where to save the plot PNG")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.mock:
        from picoscope_driver.hardware.mock import MockPicoscopeHardware

        hardware = MockPicoscopeHardware(seed=0)
    else:
        try:
            from picoscope_driver.hardware.ps3000a import Ps3000aHardware
        except ImportError:
            print(
                "Could not import picosdk. Install it with:\n"
                "    pip install -e '.[hardware]'\n"
                "(run from the PicoscopeDriverPython directory)",
                file=sys.stderr,
            )
            return 1
        hardware = Ps3000aHardware()

    acquisition = AcquisitionSettings(
        timebase=args.timebase,
        num_samples=args.samples,
        pre_trigger_samples=args.pre_trigger_samples,
    )

    print(f"Opening unit (serial={args.serial or 'auto'})...")
    try:
        hardware.open(args.serial)
    except Exception as exc:  # noqa: BLE001 - report and exit cleanly either way
        print(f"FAILED to open the PicoScope: {exc}", file=sys.stderr)
        print(
            "\nCommon causes:\n"
            "  - The native PicoScope software is still running and holds the unit open\n"
            "    (PicoSDK only allows one process at a time — close it and retry).\n"
            "  - PicoSDK isn't installed / its driver isn't on PATH — see README.md.\n"
            "  - No PicoScope is actually plugged in via USB.",
            file=sys.stderr,
        )
        return 1

    try:
        print(f"Configuring channel {args.channel}: {args.range_v}V {args.coupling}, no trigger (free-running)")
        hardware.set_channel(
            args.channel, ChannelSettings(enabled=True, range_v=args.range_v, coupling=args.coupling)
        )
        hardware.set_trigger(TriggerSettings(enabled=False))

        interval_ns = hardware.get_timebase_interval_ns(args.timebase, args.samples)
        print(f"Timebase {args.timebase} -> {interval_ns:.2f} ns/sample "
              f"({args.samples} samples = {interval_ns * args.samples / 1000:.1f} us window)")

        print("Running block capture...")
        hardware.run_block(acquisition)
        volts = hardware.get_values_v(args.channel, acquisition)
        time_s = hardware.get_time_axis_s(acquisition)

        print(f"Got {len(volts)} samples.")
        print(f"  min = {volts.min():+.4f} V")
        print(f"  max = {volts.max():+.4f} V")
        print(f"  mean = {volts.mean():+.4f} V")
        print(f"  std  = {volts.std():.4f} V")
        if abs(volts.max() - volts.min()) < 1e-6:
            print(
                "  NOTE: trace is perfectly flat — check the channel is actually\n"
                "  connected to something, or that isn't unexpected for your setup."
            )

        if not args.no_plot:
            _plot(time_s, volts, args.channel, args.out)
    finally:
        hardware.close()
        print("Unit closed.")

    return 0


def _plot(time_s, volts, channel: str, out_path: str) -> None:
    try:
        from _plot_backend import select_backend

        interactive = select_backend()
        import matplotlib.pyplot as plt
    except ImportError:
        print(
            "matplotlib isn't installed, skipping the plot "
            "(pip install -e '.[viz]' to enable it).",
        )
        return

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(time_s * 1e6, volts, linewidth=1)
    ax.set_xlabel("time (us, relative to trigger)")
    ax.set_ylabel("voltage (V)")
    ax.set_title(f"PicoScope 3000A - Channel {channel} - hardware smoke test")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    print(f"Saved plot to {out_path}")
    if interactive:
        plt.show()
    else:
        print("(no GUI backend available here — open the PNG file to view it)")


if __name__ == "__main__":
    raise SystemExit(main())
