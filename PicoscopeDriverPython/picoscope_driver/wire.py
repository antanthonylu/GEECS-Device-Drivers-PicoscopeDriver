"""GEECS UDP/TCP wire-protocol primitives.

This reimplements the value coercion/formatting rules and message shapes
used by GEECS Master Control to talk to a device driver, so that this
Python-native driver is wire-compatible with the LabVIEW ``BaseDriver``
devices Master Control already knows how to talk to.

Protocol summary (confirmed against GEECS-Core's ``fake_device_server``,
the wire-protocol test double used by the actively-maintained GEECS-Plugins
control stack)::

    UDP (device's command port):
      Master Control -> device: "set{var}>>{value}"  or  "get{var}>>"
      device -> Master Control (reply sent to sender's port):     "accepted"
      device -> Master Control (reply sent to sender's port + 1):
          "{DeviceName}>>{Variable}>>{value}>>no error,"
          "{DeviceName}>>{Variable}>>{value}>>error,{detail}"

    TCP (same port number as the UDP command port), length-framed with a
    4-byte big-endian signed length prefix followed by ASCII payload:
      Master Control -> device: "Wait>>var1,var2,..."
      device -> Master Control (pushed periodically):
          "{DeviceName}>>{shot}>>var1 nval,val1 nvar,var2 nval,val2 nvar"
"""

from __future__ import annotations

import math
import struct
from decimal import Decimal
from typing import Any

FRAME_LENGTH_STRUCT = ">i"
FRAME_HEADER_SIZE = struct.calcsize(FRAME_LENGTH_STRUCT)

ACK_OK = "accepted"
_ACK_TOKENS = frozenset({"accepted", "ok"})


def coerce_scalar(text: str) -> Any:
    """Best-effort numeric conversion; non-numeric text passes through unchanged.

    ``"007"`` becomes ``7`` (lossy for text that merely looks numeric) and
    non-finite numerics (``inf``/``nan``) pass through as the raw string.
    """
    try:
        value = float(text)
    except ValueError:
        return text
    if not math.isfinite(value):
        return text
    return int(value) if value == int(value) and "." not in text else value


def format_float(value: float) -> str:
    """Render a float as its shortest round-trip decimal, no exponent notation.

    LabVIEW's Master Control parser rejects exponent notation, so values
    like ``1e-07`` are expanded to plain decimal form (``0.0000001``).
    """
    text = repr(float(value))
    if "e" not in text:
        return text
    expanded = format(Decimal(text), "f")
    return expanded if "." in expanded else expanded + ".0"


def format_value(value: Any) -> str:
    """Render any wire-transmissible Python value as GEECS wire text."""
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, float):
        return format_float(value)
    return str(value)


def parse_command(message: str) -> tuple[str, str, str]:
    """Parse a ``"set{var}>>{value}"`` / ``"get{var}>>"`` command.

    Returns ``(op, variable, raw_value)`` where ``op`` is ``"set"`` or
    ``"get"`` and ``raw_value`` is the unparsed text after ``>>`` (empty for
    ``get``). Raises ``ValueError`` for anything else.
    """
    if ">>" not in message:
        raise ValueError(f"malformed command (missing '>>'): {message!r}")
    sep = message.index(">>")
    op_and_var, raw_value = message[:sep], message[sep + 2 :]
    if op_and_var.startswith("set"):
        return "set", op_and_var[3:], raw_value
    if op_and_var.startswith("get"):
        return "get", op_and_var[3:], raw_value
    raise ValueError(f"unrecognized command op: {message!r}")


def is_ack(message: str) -> bool:
    """Return whether *message* is a positive command acknowledgement."""
    return message.strip() in _ACK_TOKENS


def build_exe_response(
    device_name: str, variable: str, value: Any, error: str | None = None
) -> str:
    """Build the exe (execution) reply sent after a get/set command."""
    rendered = "" if value is None else format_value(value)
    if error:
        return f"{device_name}>>{variable}>>{rendered}>>error,{error}"
    return f"{device_name}>>{variable}>>{rendered}>>no error,"


def build_subscription_payload(
    device_name: str, shot: int, values: dict[str, Any]
) -> str:
    """Build one 5 Hz TCP subscription push message."""
    parts = [f"{name} nval,{format_value(val)} nvar" for name, val in values.items()]
    return f"{device_name}>>{shot}>>" + ",".join(parts)


def parse_wait_command(message: str) -> list[str]:
    """Parse a ``"Wait>>var1,var2,..."`` TCP subscription request."""
    prefix = "Wait>>"
    if not message.startswith(prefix):
        raise ValueError(f"expected a 'Wait>>' subscription command, got {message!r}")
    remainder = message[len(prefix) :]
    return remainder.split(",") if remainder else []


def pack_frame(payload: str) -> bytes:
    """Length-prefix *payload* for the TCP framing used by subscriptions."""
    encoded = payload.encode("ascii")
    return struct.pack(FRAME_LENGTH_STRUCT, len(encoded)) + encoded


def unpack_frame_header(header: bytes) -> int:
    """Decode a 4-byte big-endian frame length prefix."""
    (length,) = struct.unpack(FRAME_LENGTH_STRUCT, header)
    return length
