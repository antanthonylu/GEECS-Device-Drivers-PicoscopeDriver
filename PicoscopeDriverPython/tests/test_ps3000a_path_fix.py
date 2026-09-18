"""Tests for the 64-bit-PicoSDK PATH-priority fix.

Pure logic, no hardware or PicoSDK needed — runs in the default test suite
unlike tests/test_hardware_ps3000a.py. See the fix's own docstring in
picoscope_driver/hardware/ps3000a.py for why it exists: a real lab machine
had a 32-bit PicoSDK (bundled with the native PicoScope app, under
``Program Files (x86)``) ahead of the 64-bit one on PATH, which produced a
cryptic ``WinError 193`` instead of a clear architecture-mismatch message.
"""

from __future__ import annotations

import os

import pytest

from picoscope_driver.hardware.ps3000a import _prioritize_64bit_picosdk_on_path


@pytest.fixture(autouse=True)
def _restore_environ():
    original_path = os.environ.get("PATH")
    yield
    if original_path is None:
        os.environ.pop("PATH", None)
    else:
        os.environ["PATH"] = original_path


def test_noop_on_non_windows(monkeypatch) -> None:
    monkeypatch.setattr("picoscope_driver.hardware.ps3000a.sys.platform", "linux")
    monkeypatch.setenv("PATH", "/usr/bin")
    _prioritize_64bit_picosdk_on_path()
    assert os.environ["PATH"] == "/usr/bin"


def test_noop_when_install_dir_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("picoscope_driver.hardware.ps3000a.sys.platform", "win32")
    monkeypatch.setenv("ProgramW6432", str(tmp_path / "does-not-exist"))
    monkeypatch.setenv("PATH", r"C:\Windows\System32")
    _prioritize_64bit_picosdk_on_path()
    assert os.environ["PATH"] == r"C:\Windows\System32"


def test_prepends_lib_dir_when_present(monkeypatch, tmp_path) -> None:
    program_files = tmp_path / "Program Files"
    lib_dir = program_files / "Pico Technology" / "SDK" / "lib"
    lib_dir.mkdir(parents=True)

    monkeypatch.setattr("picoscope_driver.hardware.ps3000a.sys.platform", "win32")
    monkeypatch.setenv("ProgramW6432", str(program_files))
    monkeypatch.setenv(
        "PATH", str(tmp_path / "Program Files (x86)" / "Pico Technology" / "SDK" / "lib")
    )

    _prioritize_64bit_picosdk_on_path()

    entries = os.environ["PATH"].split(os.pathsep)
    assert entries[0] == str(lib_dir)
    assert str(tmp_path / "Program Files (x86)" / "Pico Technology" / "SDK" / "lib") in entries


def test_falls_back_to_programfiles_when_programw6432_unset(monkeypatch, tmp_path) -> None:
    program_files = tmp_path / "Program Files"
    lib_dir = program_files / "Pico Technology" / "SDK" / "lib"
    lib_dir.mkdir(parents=True)

    monkeypatch.setattr("picoscope_driver.hardware.ps3000a.sys.platform", "win32")
    monkeypatch.delenv("ProgramW6432", raising=False)
    monkeypatch.setenv("ProgramFiles", str(program_files))
    monkeypatch.setenv("PATH", "")

    _prioritize_64bit_picosdk_on_path()

    assert os.environ["PATH"].split(os.pathsep)[0] == str(lib_dir)
