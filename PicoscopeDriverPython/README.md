# PicoscopeDriverPython

A Python-native GEECS device driver for the PicoScope 3000A series,
replacing the LabVIEW `PicoscopeV2`/`picoscope` drivers elsewhere in this
repository for that hardware. It speaks the same UDP/TCP wire protocol
Master Control uses to talk to a LabVIEW `BaseDriver`-derived device, so
(once registered in the lab's GEECS device database — see
`docs/PROTOCOL.md`) Master Control can drive it like any other device.

## Status

Developed and tested against a hardware-free mock backend
(`picoscope_driver.hardware.mock.MockPicoscopeHardware`); **not yet
validated against real PicoScope 3000A hardware or a live Master Control
instance.** See `docs/PROTOCOL.md` for exactly what is and is not confirmed.

## Layout

```
picoscope_driver/
  wire.py            GEECS UDP/TCP wire-format primitives
  geecs_server.py     asyncio server implementing that protocol
  device.py           PicoscopeDevice: settings + lifecycle + GEECS variables
  config.py           DriverConfig, loaded from a TOML file
  __main__.py          CLI entry point
  hardware/
    base.py            hardware-agnostic interface + settings dataclasses
    mock.py            hardware-free double (synthetic waveforms)
    ps3000a.py          real backend, via PicoTech's `picosdk` package
tests/
  geecs_test_client.py  minimal client used only by the tests
  test_wire.py
  test_geecs_server.py  end-to-end: real server + real wire-format client
  test_device.py
docs/
  PROTOCOL.md          the wire protocol, and how it was determined
```

## Running it

```bash
pip install -e .[dev]          # mock hardware only
pip install -e .[dev,hardware] # + picosdk, for a real PicoScope

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

Channel/trigger settings follow the same shape as
`picoscopeIndividualChannelSettings.vi` and
`intialize picoscope trigger settings.vi` (per-channel enable/range/
coupling/offset; a single trigger source/threshold/direction/delay), but
the GEECS variable *names* exposed for them
(`picoscope_driver/device.py:_register_variables`) are this driver's own
choice — see the caveat in `docs/PROTOCOL.md`.
