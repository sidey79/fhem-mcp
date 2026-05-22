from pathlib import Path

from fhem_mcp.parser import FhemConfigParser


def test_parser_parses_define_attr_include_best_effort() -> None:
    parser = FhemConfigParser()
    result = parser.parse_file(Path("tests/fixtures/fhem.cfg"))

    assert "lamp" in result.devices
    lamp = result.devices["lamp"]
    assert lamp.device_type == "dummy"
    assert len(lamp.attributes) == 1
    assert lamp.attributes[0].name == "alias"
    assert lamp.attributes[0].value == "Living Room Lamp"

    assert len(result.includes) == 1
    assert result.includes[0].path_token == "extras.cfg"


def test_parser_ignores_unknown_and_perl_lines() -> None:
    parser = FhemConfigParser()
    result = parser.parse_file(Path("tests/fixtures/fhem.cfg"))

    assert all(device.name != "invalid" for device in result.devices.values())


def test_parser_supports_multiline_define_and_attr() -> None:
    parser = FhemConfigParser()
    result = parser.parse_file(Path("tests/fixtures/multiline.cfg"))

    weather = result.devices["weather"]
    assert weather.device_type == "HTTPMOD"
    assert weather.definition_tokens == ["https://example.invalid/api/", "interval=300"]
    assert weather.source.line_number == 1

    assert len(weather.attributes) == 1
    assert weather.attributes[0].name == "alias"
    assert weather.attributes[0].value == "Weather Station Main"
    assert weather.attributes[0].source.line_number == 3


def test_parser_handles_commandref_style_examples() -> None:
    parser = FhemConfigParser()
    result = parser.parse_file(Path("tests/fixtures/commandref_examples.cfg"))

    assert result.devices["myCUL"].device_type == "CUL"
    assert result.devices["lamp1"].device_type == "FS20"
    assert result.devices["vccu"].device_type == "CUL_HM"
    assert result.devices["FileLog_lamp1"].device_type == "FileLog"

    lamp_attrs = {attr.name: attr.value for attr in result.devices["lamp1"].attributes}
    assert lamp_attrs["room"] == "Wohnzimmer"
    assert lamp_attrs["alias"] == "Deckenlampe"

    assert len(result.includes) == 1
    assert result.includes[0].path_token == "rooms/common.cfg"


def test_parser_continuation_with_trailing_spaces() -> None:
    parser = FhemConfigParser()
    result = parser.parse_file(Path("tests/fixtures/multiline_spaces.cfg"))

    device = result.devices["s1"]
    assert device.definition_tokens == ["value", "continued"]
    assert device.attributes[0].value == "with spaces"


def test_parser_does_not_continue_comment_lines() -> None:
    parser = FhemConfigParser()
    result = parser.parse_file(Path("tests/fixtures/comment_continuation.cfg"))

    assert "lamp" in result.devices
    assert result.comments[0].text == "this is a comment with trailing continuation marker \\"


def test_parser_supports_define_and_attr_flags() -> None:
    parser = FhemConfigParser()
    result = parser.parse_file(Path("tests/fixtures/flag_syntax.cfg"))

    lamp = result.devices["lamp"]
    assert lamp.device_type == "dummy"
    attr_names = {attr.name: attr.value for attr in result.attribute_definitions}
    assert attr_names["room"] == "Living Room"
    assert attr_names["disable"] == ""


def test_parser_treats_double_backslash_line_end_as_continuation() -> None:
    parser = FhemConfigParser()
    result = parser.parse_file(Path("tests/fixtures/multiline_double_backslash.cfg"))

    lamp = result.devices["lamp"]
    assert lamp.definition_tokens == ["token\\", "continued"]
