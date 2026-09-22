# Handoff: PicoScope 3000A Python GEECS driver

Read this first in a new session picking up this work. It's a snapshot as
of 2026-09-22 — check `git log` for anything more recent than what's
described here.

## What this is

A ground-up Python reimplementation of a GEECS device driver for the
PicoScope 3000A series, replacing the LabVIEW `PicoscopeV2`/`picoscope`
drivers that live elsewhere in this same repository. It speaks the same
UDP/TCP wire protocol GEECS Master Control uses to talk to any
`BaseDriver`-derived LabVIEW device, so — once registered in the lab's
GEECS device database — Master Control should be able to drive it exactly
like any other device.

**Repo:** `antanthonylu/GEECS-Device-Drivers-PicoscopeDriver` (private fork
of `GEECS-BELLA/GEECS-Device-Drivers`)
**Branch:** `claude/zealous-cannon-qpk46r` — all work lives here, nothing
has touched `master`, no PR has been opened yet (not requested).
**Code lives in:** `PicoscopeDriverPython/` (this directory) — a
self-contained Python package alongside the repo's many LabVIEW driver
folders.

## Why this exists / how the design was derived

- This repo itself only contains LabVIEW device drivers — there was no
  existing Python implementation or documented wire protocol to copy from.
  Neither existing LabVIEW driver (`picoscope/`, `PicoscopeV2/`) actually
  targets the 3000A series either (one's LeCroy-derived, one targets the
  5000A series via `ps5000a`).
- The actual GEECS UDP/TCP wire protocol (get/set/ACK/exe over UDP, a
  `Wait>>` subscription over TCP) was **not** recoverable from the
  LabVIEW `.vi`/`.lvclass` binaries (compiled, not text) — it was instead
  confirmed against `GEECS-BELLA/GEECS-Plugins`, the actively-maintained
  modern GEECS control stack, specifically its `GEECS-Core` package
  (`geecs_core/transport/udp_client.py` and
  `geecs_core/testing/fake_device_server.py`, a protocol-accurate test
  double). Full details and citations: `docs/PROTOCOL.md`.
- Real hardware control uses PicoTech's official `picosdk` PyPI package
  (ctypes bindings over the native PicoSDK driver), with function
  signatures verified against the actual installed package, not memory.

## Current state

**Built and fully tested against a hardware-free mock backend**: 36 tests
pass (`pytest`), covering the wire-protocol primitives, the GEECS server,
the device lifecycle, and a Windows-specific PATH fix (see below). Two
demo scripts (`scripts/hardware_smoke_test.py`,
`scripts/hardware_protocol_demo.py`) both run clean end-to-end with
`--mock` and produce a plotted trace.

**Real-hardware validation is in progress, not yet complete.** The user
is on a lab Windows computer (via Remote Desktop) working through
`LAB_QUICKSTART.md` live, with me steering via chat. Issues hit and fixed
so far, each pushed to the branch:

1. Lab machine has Python 3.10.11, not 3.11+. Fixed: `config.py` now
   falls back to the `tomli` backport, `pyproject.toml` floor lowered to
   3.10. Verified by actually running the full suite + both demo scripts
   in a real Python 3.10.20 venv.
2. `git --version` not found right after installing Git for Windows —
   diagnosed as a stale PATH in an already-open PowerShell window (not a
   broken install). Documented in `LAB_QUICKSTART.md`.
3. Private repo — `git clone` failed with "repository does not exist"
   (GitHub's 404-for-unauthenticated-private-repo behavior). Pointed the
   user at the browser ZIP-download fallback and Git Credential
   Manager/PAT auth, both already documented in `LAB_QUICKSTART.md`.
4. **Currently being debugged**: `picosdk.errors.CannotOpenPicoSDKError:
   ... not compatible (check 32 vs 64-bit): [WinError 193]`. Root cause
   confirmed via `Get-ChildItem`: the machine has both a 64-bit
   `ps3000a.dll` (`C:\Program Files\Pico Technology\SDK\lib`, from a
   standalone PicoSDK install) and an older 32-bit one
   (`C:\Program Files (x86)\Pico Technology\SDK\lib`, bundled with the
   native PicoScope app), and PicoSDK's Python wrapper's `find_library()`
   (which re-scans `os.environ["PATH"]` itself, not a delegated OS
   search) was finding the wrong one for the confirmed-64-bit Python.
   Fixed in code: `Ps3000aHardware.open()` now calls
   `_prioritize_64bit_picosdk_on_path()` first, which prepends the
   standard 64-bit install directory to this process's `PATH` (scoped to
   this process only — doesn't touch system/user env vars or the native
   app). 4 unit tests added for this logic
   (`tests/test_ps3000a_path_fix.py`), all pass.
   **Not yet confirmed working on the real machine** — the user reported
   still seeing the same error after `git pull`, but that was very likely
   because they re-tested with the raw
   `python -c "from picosdk.ps3000a import ps3000a"` diagnostic
   one-liner, which bypasses the fix entirely (the fix only runs inside
   `Ps3000aHardware.open()`). They were last pointed at
   `python scripts\hardware_smoke_test.py` (the actual code path that
   includes the fix) and a one-liner that exercises the fix directly. **No
   response yet on whether that resolved it** — this is the immediate
   next thing to follow up on.

**Not started at all**: actual signal acquisition against real hardware
(the smoke test hasn't successfully run against the real scope yet, only
against the mock), and anything involving a real Master Control instance
(no device-database registration has happened — see
`docs/MASTER_CONTROL_INTEGRATION.md` for exactly what that needs and why
it can't be done from inside this repo).

## Where to look

Read in this order:
1. `README.md` — architecture overview, file layout, LabVIEW-to-Python
   lifecycle mapping.
2. `docs/PROTOCOL.md` — the wire protocol and exactly how it was
   determined (important: what's confirmed vs. inferred).
3. `LAB_QUICKSTART.md` — the Windows/RDP step-by-step the user has been
   following live; **this is the actual current task in progress**. Pick
   up around step 4-5 (hardware smoke test) once the PATH fix is
   confirmed or refuted.
4. `docs/MASTER_CONTROL_INTEGRATION.md` — what's needed to actually wire
   this into a real Master Control (device database registration,
   variable-name reconciliation, network/firewall), and what is/isn't
   validated about protocol compatibility with the real (not just
   GEECS-Core's modern-stack) Master Control.

## Immediate next step

Check whether the user has responded about whether
`python scripts\hardware_smoke_test.py` (or the direct one-liner) now
gets past the PicoSDK open error on the lab machine. If yes, continue
down `LAB_QUICKSTART.md` (full protocol demo, then eventually the opt-in
`pytest -m hardware` suite). If the PATH fix didn't work, the likely next
diagnostic is that PicoSDK isn't actually installed at the standard
`C:\Program Files\Pico Technology\SDK\lib` path assumed by
`_prioritize_64bit_picosdk_on_path()` in
`picoscope_driver/hardware/ps3000a.py` — ask for the real path (from the
`Get-ChildItem` output already gathered) and either generalize the
function to search more locations or let it read an override from an
environment variable.

## Access needed for a new session

- Read (and push) access to `antanthonylu/GEECS-Device-Drivers-PicoscopeDriver`
  on the same branch, `claude/zealous-cannon-qpk46r`.
- Nothing else — no other credentials, secrets, or external services are
  involved. The lab computer itself is accessed by the user directly via
  Remote Desktop; this session only ever saw it through screenshots the
  user pasted into chat.
