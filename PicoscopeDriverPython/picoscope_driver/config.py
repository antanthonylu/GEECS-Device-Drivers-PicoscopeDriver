"""Device configuration: where it listens, which unit it drives, where it saves.

Loaded from a small TOML file (see ``config.example.toml``) so the same
driver code runs unmodified in the mock-hardware development setup and on
the real acquisition PC — only the config file differs.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DriverConfig:
    """Everything needed to stand up one :class:`~picoscope_driver.device.PicoscopeDevice`."""

    device_name: str = "U_Picoscope3000A"
    host: str = "0.0.0.0"
    port: int = 0
    push_hz: float = 5.0
    use_mock_hardware: bool = True
    serial: str | None = None
    save_directory: str = "./data"

    @classmethod
    def from_toml(cls, path: str | Path) -> "DriverConfig":
        """Load a config from a TOML file; unspecified keys keep their default."""
        with open(path, "rb") as handle:
            raw = tomllib.load(handle)
        known_fields = cls.__dataclass_fields__.keys()
        unknown = set(raw) - set(known_fields)
        if unknown:
            raise ValueError(f"unknown config key(s) in {path}: {sorted(unknown)}")
        return cls(**raw)


EXAMPLE_TOML = """\
# Copy to config.toml and edit for your deployment.

device_name = "U_Picoscope3000A"

# Master Control talks to this device on this host:port. port = 0 lets the
# OS pick a port for local testing; a real deployment needs a fixed port
# that matches this device's entry in the GEECS device database.
host = "0.0.0.0"
port = 0
push_hz = 5.0

# Set to false once PicoSDK and a real PicoScope 3000A are available.
use_mock_hardware = true

# PicoScope unit serial number, e.g. "JR628/0017"; leave unset to open
# whichever unit PicoSDK finds (only safe with one unit attached).
# serial = "JR628/0017"

save_directory = "./data"
"""
