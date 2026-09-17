# GEECS Master Control wire protocol

This driver's job is to make a PicoScope 3000A answer to GEECS Master
Control exactly the way a LabVIEW `BaseDriver`-derived device (like the
existing `PicoscopeV2` driver in this repo) does. This document records
what that protocol is and where it came from, since it is not written down
anywhere in this repository.

## How this was determined

The LabVIEW `.vi`/`.lvclass` files in `BaseDriver/` and `UDPComm/` are
compiled National Instruments binaries — the block diagrams that implement
the wire protocol are not recoverable as text, so static inspection of them
only confirms the device *lifecycle* (`Initialize.vi`, `Configure.vi`,
`Acquire.vi`, `Save.vi`, `Close.vi`, an `IP Address` + `Saving Path (UDP)`
pair of controls, a `UDPComm.lvlib` dependency), not the byte-level format.

The actual wire format below was instead confirmed against
[`GEECS-BELLA/GEECS-Plugins`](https://github.com/GEECS-BELLA/GEECS-Plugins),
the actively-maintained modern GEECS control stack. Its `GEECS-Core` package
ships `geecs_core/transport/udp_client.py` (the client Master-Control-side
tooling uses to talk to real devices) and
`geecs_core/testing/fake_device_server.py` (an explicitly-documented
"Fake GEECS device server speaking the real UDP/TCP wire protocol", used as
a test double in that repo's own test suite). Both describe the same
protocol from opposite ends, and agree with each other and with comments
in the client citing observed behavior of real hardware — that is the
protocol this driver implements.

**This has not been validated against a live Master Control instance.**
Validate against the real system before relying on it operationally.

## Wire format

### UDP — get/set (command port)

Master Control sends one of:

```
set{Variable}>>{value}
get{Variable}>>
```

to the device's UDP command port. The device replies twice:

1. To the sender's own port: the literal ASCII bytes `accepted` (an ACK,
   observed as `"ok"` on some real hardware too — accept either).
2. To the sender's port **+ 1** (the "exe"/execution port): a status
   message

   ```
   {DeviceName}>>{Variable}>>{value}>>no error,
   {DeviceName}>>{Variable}>>{value}>>error,{detail}
   ```

   The value field on a successful `set` echoes the value that was
   actually stored; on `get` it is the current value. Exponent notation
   (`1e-07`) is never sent — LabVIEW's parser rejects it, so floats are
   expanded to plain decimal (`0.0000001`). See `picoscope_driver.wire`.

### TCP — variable subscription (same port number as the UDP command port)

Master Control opens a TCP connection to the same port number and sends one
length-framed message:

```
Wait>>{var1},{var2},...
```

Framing is a 4-byte big-endian signed length prefix followed by the ASCII
payload (`struct.pack(">i", len(payload)) + payload`, both ways).

The device then pushes, at a fixed rate (5 Hz observed), one framed message
per update:

```
{DeviceName}>>{shot}>>{var1} nval,{val1} nvar,{var2} nval,{val2} nvar,...
```

until the connection is closed.

## What is *not* determined by this document

- **Device registration.** Real Master Control looks up a device's IP and
  port from the lab's GEECS experiment database (referenced elsewhere as
  `GeecsDb`, `~/.config/geecs_python_api/config.ini`). Getting this driver
  a routable `(host, port)` that Master Control will actually dial is a
  lab-side administrative step outside this repository.
- **Variable names.** `picoscope_driver.device.PicoscopeDevice` invents its
  own variable names (`"ChannelA Range (V)"`, `"Trigger Threshold (V)"`,
  `"Acquire"`, `"shotnumber"`, `"status"`, ...) since there is no
  machine-readable export of `PicoscopeV2`'s variable list to copy. These
  names must match whatever aliases get registered for this device in the
  experiment database before Master Control can address them by the names
  scans and GUIs expect.
