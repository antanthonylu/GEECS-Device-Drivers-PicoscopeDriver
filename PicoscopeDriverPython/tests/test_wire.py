from picoscope_driver import wire


def test_coerce_scalar_int() -> None:
    assert wire.coerce_scalar("3") == 3
    assert isinstance(wire.coerce_scalar("3"), int)


def test_coerce_scalar_float() -> None:
    assert wire.coerce_scalar("3.5") == 3.5


def test_coerce_scalar_passthrough_text() -> None:
    assert wire.coerce_scalar("RISING") == "RISING"


def test_coerce_scalar_nonfinite_passthrough() -> None:
    assert wire.coerce_scalar("nan") == "nan"
    assert wire.coerce_scalar("inf") == "inf"


def test_format_float_plain() -> None:
    assert wire.format_float(1.5) == "1.5"


def test_format_float_expands_small_exponent() -> None:
    assert wire.format_float(1e-07) == "0.0000001"


def test_format_float_expands_large_exponent() -> None:
    assert wire.format_float(1e16) == "10000000000000000.0"


def test_parse_command_set() -> None:
    assert wire.parse_command("setChannelA Enabled>>1") == ("set", "ChannelA Enabled", "1")


def test_parse_command_get() -> None:
    assert wire.parse_command("getstatus>>") == ("get", "status", "")


def test_parse_command_rejects_malformed() -> None:
    try:
        wire.parse_command("nonsense")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_build_exe_response_success() -> None:
    message = wire.build_exe_response("U_Pico", "shotnumber", 3)
    assert message == "U_Pico>>shotnumber>>3>>no error,"


def test_build_exe_response_error() -> None:
    message = wire.build_exe_response("U_Pico", "Timebase", None, error="out of range")
    assert message == "U_Pico>>Timebase>>>>error,out of range"


def test_pack_and_unpack_frame_roundtrip() -> None:
    frame = wire.pack_frame("hello")
    header, payload = frame[: wire.FRAME_HEADER_SIZE], frame[wire.FRAME_HEADER_SIZE :]
    assert wire.unpack_frame_header(header) == len(payload)
    assert payload == b"hello"


def test_parse_wait_command() -> None:
    assert wire.parse_wait_command("Wait>>A,B,C") == ["A", "B", "C"]


def test_is_ack() -> None:
    assert wire.is_ack("accepted")
    assert wire.is_ack("ok")
    assert not wire.is_ack("rejected")
