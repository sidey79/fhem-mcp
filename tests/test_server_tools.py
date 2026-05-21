from pathlib import Path

from fhem_mcp.server import FhemMcpServer


def test_list_and_read_config_files() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))
    files = server.list_config_files()

    assert "fhem.cfg" in files
    assert "extras.cfg" in files

    contents = server.read_config_file("fhem.cfg")
    assert "define lamp dummy" in contents


def test_list_devices_and_get_device() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    devices = server.list_devices("fhem.cfg")
    assert any(device["name"] == "lamp" for device in devices)
    assert any(device["name"] == "tempSensor" for device in devices)

    lamp = server.get_device("fhem.cfg", "lamp")
    assert lamp is not None
    assert lamp["device_type"] == "dummy"
    assert lamp["attributes"][0]["name"] == "alias"


def test_read_config_prevents_path_escape() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    try:
        server.read_config_file("../README.md")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for escaped path")


def test_list_devices_prevents_path_escape() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    try:
        server.list_devices("../README.md")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for escaped path")


def test_get_device_prevents_path_escape() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    try:
        server.get_device("../README.md", "foo")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for escaped path")


def test_get_device_from_included_file() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    sensor = server.get_device("fhem.cfg", "tempSensor")
    assert sensor is not None
    assert sensor["device_type"] == "MQTT2_DEVICE"


def test_include_order_respects_parent_sequence() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    lamp = server.get_device("include_order.cfg", "lamp")
    assert lamp is not None
    assert lamp["definition_tokens"] == ["B"]


def test_missing_include_is_best_effort_non_fatal() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    devices = server.list_devices("include_missing.cfg")
    names = {d["name"] for d in devices}
    assert "before" in names
    assert "after" in names
