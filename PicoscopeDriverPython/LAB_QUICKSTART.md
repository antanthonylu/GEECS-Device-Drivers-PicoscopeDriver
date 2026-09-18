# Lab quickstart: testing on the PicoScope 3000A computer

Step-by-step instructions for testing this driver against real hardware,
on the lab computer, **without merging this branch to `master`**. Copy-paste
the commands for your OS as you go.

Everything here defaults to safe, non-destructive checks: nothing here
touches `master`, nothing here needs Master Control or the GEECS device
database to be set up.

## 0. Before you start

- **Close the native PicoScope software** (PicoScope 6/7/etc.) if it's
  running. PicoSDK only allows one process to hold the USB device open at
  a time — if the native app has it open, this driver's attempt to open it
  will fail with a confusing-looking error. This is the #1 thing to check
  if step 3 or 4 below fails.
- You do **not** need anything connected to the scope's inputs for the
  first tests below — with no trigger configured the scope free-runs and
  you'll just see a flat, noisy trace. If you want to see a real signal,
  connect the scope's probe-compensation / cal signal output (if it has
  one) to the channel you're testing.

## 1. Get the code, without touching `master`

```bash
git clone https://github.com/antanthonylu/GEECS-Device-Drivers-PicoscopeDriver.git picoscope-test
cd picoscope-test
git checkout claude/zealous-cannon-qpk46r
cd PicoscopeDriverPython
```

This clones into a brand-new `picoscope-test` folder — it never touches
`master` or any existing checkout you have of this repo elsewhere on that
computer.

## 2. Set up an isolated Python environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Then, on either OS, install this driver plus the real-hardware and
plotting extras:

```bash
pip install -e ".[dev,hardware,viz]"
```

## 3. Check PicoSDK is actually reachable

```bash
python -c "from picosdk.ps3000a import ps3000a"
```

- **No output / no error** → good, move to step 4.
- **`CannotFindPicoSDKError`** → the native PicoScope app is likely using
  its own bundled copy of the driver that isn't on `PATH`
  (Windows)/`LD_LIBRARY_PATH` (Linux). Install PicoTech's standalone
  **PicoSDK** package (separate download from the PicoScope application
  itself) from picotech.com, then retry.

## 4. Hardware smoke test (bypasses the GEECS protocol entirely)

This talks directly to the oscilloscope — it's the fastest way to confirm
"does this computer, this driver, and this scope actually work together"
before worrying about the GEECS protocol layer at all.

```bash
python scripts/hardware_smoke_test.py
```

You should see something like:

```
Opening unit (serial=auto)...
Configuring channel A: 1.0V DC, no trigger (free-running)
Timebase 8 -> 48.00 ns/sample (2000 samples = 96.0 us window)
Running block capture...
Got 2000 samples.
  min = -0.0412 V
  max = +0.0398 V
  mean = +0.0003 V
  std  = 0.0104 V
Saved plot to smoke_test.png
Unit closed.
```

...and a plot window should pop up (a `smoke_test.png` is saved either
way, so open that file if no window appears). A flat noisy trace around
0 V is expected with nothing connected — that's a pass, not a failure.

**If it fails to open the unit**, the printed error will suggest the two
most common causes (native software still running, or PicoSDK not found).

**Useful variations:**
```bash
python scripts/hardware_smoke_test.py --channel B --range 2.0 --samples 5000
python scripts/hardware_smoke_test.py --serial "JR628/0017"   # if multiple units are attached
python scripts/hardware_smoke_test.py --help                   # see all options
```

## 5. Full protocol demo (this is what actually matters)

This is the real test: it starts the same `GeecsDeviceServer` +
`PicoscopeDevice` that would run in production, and drives it purely by
sending it the same `set{var}>>{value}` / `get{var}>>` commands Master
Control sends — not calling any Python method directly. If this works,
Master Control will be able to drive this scope once it's registered in
the GEECS device database.

```bash
python scripts/hardware_protocol_demo.py
```

Expected output looks like:

```
Initializing device (opens the hardware)...
GeecsDeviceServer listening on 127.0.0.1:XXXXX (this is what Master Control would dial)

--- sending the same commands Master Control would ---
  setChannelA Enabled>>1  ->  confirmed 1
  setChannelA Range (V)>>1.0  ->  confirmed 1.0
  setChannelA Coupling>>DC  ->  confirmed 'DC'
  setNumber of Samples>>2000  ->  confirmed 2000

  setAcquire>>1 ...
  -> shot number is now 1
  setSave>>1 ...
  -> saved to data/U_TestPicoscope3000A_shot00001.csv

--- a short live subscription, exactly like a scan's Wait>> ---
  pushed: U_TestPicoscope3000A>>1>>shotnumber nval,1 nvar,status nval,idle nvar
  ...
Saved plot to protocol_demo.png

Done.
```

Open `protocol_demo.png` to see the captured trace, and
`data/U_TestPicoscope3000A_shot00001.csv` for the raw numbers.

```bash
python scripts/hardware_protocol_demo.py --channel B --range 2.0
python scripts/hardware_protocol_demo.py --help
```

## 6. (Optional) Turn this into a repeatable regression test

Rather than manual runs, this can be checked automatically any time with
`pytest`, using the same real hardware:

```bash
PICOSCOPE_HW_TEST=1 pytest -m hardware -v
```

(On Windows PowerShell: `$env:PICOSCOPE_HW_TEST=1; pytest -m hardware -v`)

These tests are skipped by default (a plain `pytest` never touches the
hardware) — this is the only command that runs them.

## 7. Running the actual driver process

Once the above all work, you can run the driver the way it would run in
production — as a standalone process listening for Master Control:

```bash
python -c "from picoscope_driver.config import EXAMPLE_TOML; open('config.toml', 'w').write(EXAMPLE_TOML)"
# edit config.toml: set use_mock_hardware = false, and a fixed `port` if
# you have one to test against (0 = OS picks a random port, fine for now)
python -m picoscope_driver --config config.toml --verbose
```

Leave it running and, from another terminal (same computer or another
machine on the lab network — it's just UDP/TCP), you can drive it with
`picoscope_driver.client.GeecsClient` the same way `scripts/hardware_protocol_demo.py`
does, or point real Master Control at it once it's in the GEECS device
database (see `docs/PROTOCOL.md` for what that step needs — it's not
covered by anything here).

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `CannotFindPicoSDKError` | PicoSDK driver not installed / not on `PATH`. See step 3. |
| Fails to open unit, no Python traceback about PicoSDK | Native PicoScope software still has it open. Close it and retry. |
| Trace is a perfectly flat line at exactly 0 V (not just noisy) | Possible real problem — a live ADC essentially never reads bit-identical samples. Check the connection / channel enable state. |
| `ModuleNotFoundError: No module named 'picosdk'` | Run `pip install -e ".[hardware]"` from inside `PicoscopeDriverPython/` with the venv active. |
| No plot window pops up | Either matplotlib isn't installed (`pip install -e ".[viz]"`) or there's no GUI toolkit available in this environment — either way, the `.png` file is still written; open it directly. |
