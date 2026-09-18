# Lab quickstart: testing on the PicoScope 3000A Windows computer

Step-by-step instructions for testing this driver against real hardware, on
the lab Windows computer, over Remote Desktop, **without merging this
branch to `master`**. Every command below is meant to be copy-pasted
as-is into **PowerShell**.

Everything here defaults to safe, non-destructive checks: nothing here
touches `master`, and nothing here needs Master Control or the GEECS
device database to be set up — that's a separate step, covered in
`docs/MASTER_CONTROL_INTEGRATION.md`.

## 0. Before you start

- **Connect to the lab computer over Remote Desktop Connection** as you
  normally would.
- **Close the native PicoScope software** (PicoScope 6/7/etc.) if it's
  running. PicoSDK only allows one process to hold the USB device open at
  a time — if the native app has it open, this driver's attempt to open it
  will fail with a confusing-looking error. This is the #1 thing to check
  if step 4 or 5 below fails.
- You do **not** need anything connected to the scope's inputs for the
  first tests below — with no trigger configured the scope free-runs and
  you'll just see a flat, noisy trace. If you want to see a real signal,
  connect the scope's probe-compensation / cal signal output (if it has
  one) to the channel you're testing.
- Open **PowerShell**: click Start, type `powershell`, press Enter. You
  don't need Administrator rights for most of this — only step 6
  (firewall rule) needs it, and only if you go on to test with a real
  Master Control on another machine.

## 1. Check prerequisites are installed

```powershell
python --version
git --version
```

- **`python` not found**, or older than 3.10: download the installer from
  https://www.python.org/downloads/windows/ and run it. **On the first
  install screen, check "Add python.exe to PATH"** before clicking
  Install — this is the single most common thing people forget. Close and
  reopen PowerShell afterward so it picks up the new `PATH`. (3.10 is
  fine — this driver doesn't need 3.11+, no need to install a second
  Python version if 3.10 is already what's on this machine.)
- **`git` not found right after installing Git for Windows`**: this is
  almost always just a stale `PATH` in the PowerShell window you already
  had open — **close this PowerShell window completely and open a new
  one**, then `cd` back into wherever you were and retry `git --version`.
  If it's still not found in a fresh window:
  - Check whether **Git Bash** (a Start-menu app installed alongside Git
    for Windows) can run `git --version` — if so, the installer put Git
    on Git Bash's PATH but not PowerShell's. Easiest fix: just do all the
    `git` commands below in Git Bash instead of PowerShell (everything
    from step 2 onward can also run there); or re-run the Git for Windows
    installer and, on the "Adjusting your PATH environment" screen,
    choose **"Git from the command line and also from 3rd-party
    software"**.
  - If Git Bash doesn't have it either, the install may not have
    finished — re-run the installer from gitforwindows.org.
  - Either way, you can skip git entirely — see the "No git?" box in
    step 2 below.

## 2. Get the code, without touching `master`

```powershell
git clone https://github.com/antanthonylu/GEECS-Device-Drivers-PicoscopeDriver.git picoscope-test
cd picoscope-test
git checkout claude/zealous-cannon-qpk46r
cd PicoscopeDriverPython
```

This clones into a brand-new `picoscope-test` folder in whatever directory
you ran it from (e.g. `C:\Users\<you>\picoscope-test`) — it never touches
`master` or any existing checkout of this repo elsewhere on that computer.

> **No git, or `git clone` asks for credentials you don't have?**
> In a browser on the lab computer, go to the repository on GitHub, use
> the branch dropdown to select `claude/zealous-cannon-qpk46r`, click the
> green **Code** button → **Download ZIP**, then right-click the
> downloaded file → **Extract All...**. `cd` into the extracted
> `PicoscopeDriverPython` folder and continue at step 3.

## 3. Set up an isolated Python environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If that second command fails with something like *"running scripts is
disabled on this system"*, PowerShell's default execution policy is
blocking it — this is normal on locked-down lab machines. Fix it for just
this window (doesn't need Administrator, doesn't change anything
permanently) and try again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

Your prompt should now start with `(.venv)`. Every command from here on
assumes that's the case — if you close and reopen PowerShell, `cd` back
into `PicoscopeDriverPython` and re-run the `Activate.ps1` line before
continuing.

Now install this driver plus the real-hardware and plotting extras:

```powershell
pip install -e ".[dev,hardware,viz]"
```

## 4. Check PicoSDK is actually reachable

```powershell
python -c "from picosdk.ps3000a import ps3000a"
```

- **No output / no error** → good, move to step 5.
- **`CannotFindPicoSDKError`** → the native PicoScope app is likely using
  its own bundled copy of the driver that isn't on `PATH`. Install
  PicoTech's standalone **PicoSDK** package (a separate download from the
  PicoScope application itself) from
  https://www.picotech.com/downloads — pick "PicoSDK (64-bit)" for your
  scope's product page — then close and reopen PowerShell, reactivate the
  venv (`.venv\Scripts\Activate.ps1`), and retry.

## 5. Hardware smoke test (bypasses the GEECS protocol entirely)

This talks directly to the oscilloscope — it's the fastest way to confirm
"does this computer, this driver, and this scope actually work together"
before worrying about the GEECS protocol layer at all.

```powershell
python scripts\hardware_smoke_test.py
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

...and a plot window should pop up (a `smoke_test.png` is saved in the
current folder either way — double-click it in File Explorer if no window
appears). A flat noisy trace around 0 V is expected with nothing
connected — that's a pass, not a failure.

**If it fails to open the unit**, the printed error will suggest the two
most common causes (native software still running, or PicoSDK not found —
steps 0 and 4 above).

**Useful variations:**
```powershell
python scripts\hardware_smoke_test.py --channel B --range 2.0 --samples 5000
python scripts\hardware_smoke_test.py --serial "JR628/0017"   # if multiple units are attached
python scripts\hardware_smoke_test.py --help                   # see all options
```

## 6. Full protocol demo (this is what actually matters)

This is the real test: it starts the same `GeecsDeviceServer` +
`PicoscopeDevice` that would run in production, and drives it purely by
sending it the same `set{var}>>{value}` / `get{var}>>` commands Master
Control sends — not calling any Python method directly. If this works,
Master Control will be able to drive this scope once it's registered in
the GEECS device database (see `docs/MASTER_CONTROL_INTEGRATION.md`).

```powershell
python scripts\hardware_protocol_demo.py
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
`data\U_TestPicoscope3000A_shot00001.csv` for the raw numbers.

```powershell
python scripts\hardware_protocol_demo.py --channel B --range 2.0
python scripts\hardware_protocol_demo.py --help
```

## 7. (Optional) Turn this into a repeatable regression test

Rather than manual runs, this can be checked automatically any time with
`pytest`, using the same real hardware:

```powershell
$env:PICOSCOPE_HW_TEST=1
pytest -m hardware -v
```

These tests are skipped by default (a plain `pytest` never touches the
hardware) — the two lines above are the only way to run them.

## 8. (Only if testing against a real Master Control) Firewall + run as a standalone process

Skip this section entirely if you're only doing the tests above. Only do
this once you're ready to have an actual Master Control instance (on this
machine or another one on the lab network) talk to this driver — see
`docs/MASTER_CONTROL_INTEGRATION.md` first for what else that requires
(mainly: someone with access to the GEECS device database registering
this device).

Pick a fixed port (Master Control needs one it can be told to dial
consistently — port `0` used in steps 5–7 means "OS picks a random one
each run", which is fine for the tests above but not for a real
integration). Then, **in an Administrator PowerShell** (right-click
PowerShell → "Run as Administrator"), open that port through Windows
Defender Firewall — replace `4030` with whatever port you picked:

```powershell
New-NetFirewallRule -DisplayName "GEECS Picoscope Driver (UDP)" -Direction Inbound -Protocol UDP -LocalPort 4030 -Action Allow
New-NetFirewallRule -DisplayName "GEECS Picoscope Driver (TCP)" -Direction Inbound -Protocol TCP -LocalPort 4030 -Action Allow
```

Back in your regular (non-Administrator) PowerShell, with the venv still
active:

```powershell
python -c "from picoscope_driver.config import EXAMPLE_TOML; open('config.toml', 'w').write(EXAMPLE_TOML)"
notepad config.toml
```

In Notepad, set:
```toml
use_mock_hardware = false
port = 4030
```
(and `serial = "..."` if more than one PicoScope could be attached). Save,
close Notepad, then run:

```powershell
python -m picoscope_driver --config config.toml --verbose
```

Leave that window open — it's now listening for commands. From another
window (or another machine on the lab network — it's just UDP/TCP on
whatever IP this computer has), you can drive it with
`picoscope_driver.client.GeecsClient` the same way
`scripts\hardware_protocol_demo.py` does, or point a real Master Control
instance at `<this computer's IP>:4030` once it's registered in the GEECS
device database.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `git` not recognized right after installing Git for Windows | Stale `PATH` in an already-open PowerShell window. Close it, open a new one, retry. See step 1. |
| `running scripts is disabled on this system` | PowerShell execution policy. See step 3's fix. |
| `CannotFindPicoSDKError` | PicoSDK driver not installed / not on `PATH`. See step 4. |
| Fails to open unit, no Python traceback about PicoSDK | Native PicoScope software still has it open. Close it and retry. |
| Trace is a perfectly flat line at exactly 0 V (not just noisy) | Possible real problem — a live ADC essentially never reads bit-identical samples. Check the connection / channel enable state. |
| `ModuleNotFoundError: No module named 'picosdk'` | Run `pip install -e ".[hardware]"` from inside `PicoscopeDriverPython\` with the venv active. |
| No plot window pops up | Either matplotlib isn't installed (`pip install -e ".[viz]"`) or there's no GUI toolkit reachable over this RDP session — either way, the `.png` file is still written; open it in File Explorer. |
| A real Master Control can't reach the driver (step 8) | Check the firewall rule went in (`Get-NetFirewallRule -DisplayName "GEECS Picoscope*"`), that `port` in `config.toml` matches what you opened, and that the device is actually registered in the GEECS database pointing at this machine's IP and that port. |

## Appendix: Linux / macOS

Everything above works the same on Linux/macOS with the obvious
substitutions:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,hardware,viz]"
python scripts/hardware_smoke_test.py
python scripts/hardware_protocol_demo.py
PICOSCOPE_HW_TEST=1 pytest -m hardware -v
```

PicoSDK not found there means the native `libps3000a.so`/`.dylib` isn't on
`LD_LIBRARY_PATH`/`DYLD_LIBRARY_PATH` — same fix, install PicoTech's
standalone PicoSDK package for that OS.
