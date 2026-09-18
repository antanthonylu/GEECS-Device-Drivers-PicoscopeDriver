# PicoscopeDriverPython

A Python-native GEECS device driver for the PicoScope 3000A series,
replacing the LabVIEW `PicoscopeV2`/`picoscope` drivers elsewhere in this
repository for that hardware. It speaks the same UDP/TCP wire protocol
Master Control uses to talk to a LabVIEW `BaseDriver`-derived device, so
(once registered in the lab's GEECS device database — see
`docs/MASTER_CONTROL_INTEGRATION.md`) Master Control can drive it like any
other device.

## Status

Developed and tested against a hardware-free mock backend
(`picoscope_driver.hardware.mock.MockPicoscopeHardware`); **not yet
validated against real PicoScope 3000A hardware or a live Master Control
instance.** See `docs/PROTOCOL.md` for exactly what is and is not confirmed.

**Testing on real hardware:** see `LAB_QUICKSTART.md` for copy-paste,
step-by-step instructions (Windows/Remote Desktop-focused) to run this on
a lab computer with a PicoScope 3000A attached, including two demo scripts
that produce a plot of a real captured trace.

**Wiring it up to a real Master Control:** see
`docs/MASTER_CONTROL_INTEGRATION.md` for what that takes and what is/isn't
confirmed to work.

## Layout

```
picoscope_driver/
  wire.py            GEECS UDP/TCP wire-format primitives
  geecs_server.py     asyncio server implementing that protocol
  client.py            GEECS client (Master Control's side) — used by tests and the lab demo scripts
  device.py           PicoscopeDevice: settings + lifecycle + GEECS variables
  config.py           DriverConfig, loaded from a TOML file
  __main__.py          CLI entry point
  hardware/
    base.py            hardware-agnostic interface + settings dataclasses
    mock.py            hardware-free double (synthetic waveforms)
    ps3000a.py          real backend, via PicoTech's `picosdk` package
scripts/
  hardware_smoke_test.py    direct hardware check + plot (bypasses the GEECS protocol)
  hardware_protocol_demo.py  full pipeline over the real wire protocol + plot
tests/
  geecs_test_client.py  thin re-export of picoscope_driver.client, for import-path stability
  test_wire.py
  test_geecs_server.py  end-to-end: real server + real wire-format client (mock hardware)
  test_device.py
  test_hardware_ps3000a.py  opt-in: needs PICOSCOPE_HW_TEST=1 + real hardware
docs/
  PROTOCOL.md          the wire protocol, and how it was determined
  MASTER_CONTROL_INTEGRATION.md  what it takes to register this with a real Master Control
LAB_QUICKSTART.md      step-by-step guide for testing on real hardware
```

## Running it

```bash
pip install -e ".[dev]"                 # mock hardware only
pip install -e ".[dev,hardware,viz]"    # + picosdk and matplotlib, for a real PicoScope

pytest

# write out an example config, then edit it (host/port/serial/save path)
python -c "from picoscope_driver.config import EXAMPLE_TOML; open('config.toml', 'w').write(EXAMPLE_TOML)"
python -m picoscope_driver --config config.toml
```

Running against real hardware additionally requires PicoTech's native
PicoSDK driver (`ps3000a.dll` / `libps3000a.so`) installed on the host, and
`use_mock_hardware = false` in the config file.

## Mapping to the LabVIEW driver

`PicoscopeDevice`'s lifecycle mirrors `PicoscopeV2.lvclass`:

| LabVIEW                  | Python                         |
| ------------------------ | ------------------------------- |
| `Initialize.vi`           | `PicoscopeDevice.initialize()`  |
| `Configure.vi`            | `PicoscopeDevice.configure()`   |
| `Acquire.vi`               | `PicoscopeDevice.acquire()`     |
| `Save.vi`                  | `PicoscopeDevice.save()`        |
| `Close.vi`                 | `PicoscopeDevice.close()`       |

`Acquire` and `Save` are also exposed as GEECS variables (`setAcquire>>1`,
`setSave>>1`) so Master Control — or `scripts/hardware_protocol_demo.py` —
can trigger them purely over the wire protocol; `Last Save Path` is a
read-only variable naming the most recently written CSV.

Channel/trigger settings follow the same shape as
`picoscopeIndividualChannelSettings.vi` and
`intialize picoscope trigger settings.vi` (per-channel enable/range/
coupling/offset; a single trigger source/threshold/direction/delay), but
the GEECS variable *names* exposed for them
(`picoscope_driver/device.py:_register_variables`) are this driver's own
choice — see the caveat in `docs/PROTOCOL.md`.
