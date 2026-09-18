# Connecting this driver to a real Master Control

**Short answer: yes, in principle Master Control cannot tell this driver
apart from the LabVIEW `PicoscopeV2` driver it replaces — the protocol is
what defines "a device" to Master Control, not the implementation behind
it. But getting there needs a few things this repository cannot do by
itself, and there's real uncertainty about full behavioral coverage that
hasn't been tested against real Master Control. Details below.**

## Why "just like any other device" is basically true

Master Control's device abstraction is protocol-based: it doesn't know or
care whether the thing on the other end of a UDP command is LabVIEW,
Python, or anything else — it knows a device by (name, IP, port) from its
device database, and talks to it using the wire format in
`docs/PROTOCOL.md`. This driver (`GeecsDeviceServer` + `PicoscopeDevice`)
implements exactly that format:

- It answers `get{var}>>` / `set{var}>>{value}` on its UDP port with the
  same ACK + exe-response sequence a LabVIEW `BaseDriver` device sends.
- It answers a `Wait>>var1,var2,...` TCP subscription with the same 5 Hz
  push format, which is what feeds Master Control's live-value displays
  and scan data logging.

So structurally, once Master Control is told this device exists at some
`(host, port)`, it should show up and behave like any other device tile —
readable/settable variables, live values, includable in a scan.

## What has to happen for that to actually work

1. **Device database registration.** Master Control looks up a device's
   IP and port (and, in the modern stack, its variable list) from the
   lab's GEECS experiment database (`GeecsDb`). This repository has no
   access to that database and can't create the entry — it's an
   administrative step for whoever manages it in your lab. You'll need:
   - A device name (e.g. `U_Picoscope3000A`, or reuse whatever name is
     already reserved for this hardware if one exists).
   - The IP address and port this driver is listening on (see
     `LAB_QUICKSTART.md` step 8 — pick a fixed port, not `0`).
   - Entries for whichever variables you want visible/settable from the
     GUI or scans (see the variable list below).
2. **Variable name agreement.** This driver invented its own GEECS
   variable names (`ChannelA Enabled`, `Trigger Threshold (V)`, `Acquire`,
   `Save`, `shotnumber`, `status`, `Last Save Path`, ... — the full list is
   `PicoscopeDevice.variable_names`, defined in
   `picoscope_driver/device.py:_register_variables`) because there's no
   machine-readable export of `PicoscopeV2`'s variable list to copy from.
   Whatever gets registered in the device database has to use *these*
   names (or you tell me what names the lab actually wants and I'll
   rename the variables to match — that's a small, low-risk change).
3. **Network + firewall.** Master Control's host needs a route to this
   driver's `(host, port)`, and Windows Firewall on the PicoScope computer
   needs an inbound allow rule for that port (`LAB_QUICKSTART.md` step 8
   has the exact commands).

None of this can be done from inside this repository or by me — it needs
someone with access to the GEECS device database and, ideally, a
non-production Master Control setup to try it on first.

## What's confirmed vs. what isn't

**Confirmed** (validated in this session, see `docs/PROTOCOL.md`): the
wire format itself — UDP get/set/ACK/exe, TCP `Wait>>` subscription push,
value coercion/formatting rules — matches what GEECS-Core's actively
maintained client and protocol-accurate fake server implement, and this
driver's own protocol layer has been tested end-to-end against that
(`scripts/hardware_protocol_demo.py`, the pytest suite).

**Not confirmed:**
- This has **not** been tested against the actual legacy Master Control
  LabVIEW application — only against GEECS-Core's client/fake-server pair,
  which is the modern Python control stack's understanding of the same
  protocol. It's very likely the same protocol Master Control speaks (that
  fake server exists specifically to be indistinguishable from a real
  device to that stack's own tooling), but "very likely" isn't "verified."
- Master Control may expect additional behavior beyond plain get/set that
  this driver doesn't yet implement. One concrete hint: `BaseDriver`'s
  `Configure.vi` references `BuildPresetCommands.vi` and
  `load configuration_typdef.ctl` — suggesting Master Control can push a
  named "preset" (a batch of settings) to a device. Structurally this
  almost certainly still decomposes into ordinary `set{var}>>{value}`
  commands sent one after another (there's no other write primitive in the
  protocol), which this driver already handles — but that's an inference,
  not something observed directly.
- Timing/robustness under Master Control's actual timeouts and retry
  behavior, and under whatever load a real scan puts on it (rapid
  get/set/acquire cycles), hasn't been exercised.

## Recommended rollout, lowest risk first

1. Do the `LAB_QUICKSTART.md` steps first (already covers hardware +
   protocol correctness, no Master Control involved).
2. Register a **new, test-only device name** in the database (something
   like `U_TestPicoscope3000A` that can't collide with a production
   device), pointed at this driver's `(host, port)`. Don't repurpose an
   existing production device's entry for this test.
3. If your lab has a non-production/dev Master Control instance, add the
   test device there first and try a manual get/set from its GUI before
   touching a real experiment or scan.
4. Only after that works, discuss with whoever owns the real device
   database whether/how to promote this driver to replace the LabVIEW
   `PicoscopeV2` driver for actual experiments.

If anything in step 3 surfaces protocol behavior this driver doesn't
handle, that's exactly the kind of concrete, reproducible finding that's
easy to fix from here — bring back what Master Control sent and I can
add support for it.
