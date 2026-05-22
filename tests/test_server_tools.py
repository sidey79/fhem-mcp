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
    assert all(isinstance(device["source_line"], int) for device in devices)

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


def test_read_config_allows_only_cfg_files() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    try:
        server.read_config_file("not_config.txt")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for non-cfg file")


def test_list_devices_allows_only_cfg_files() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    try:
        server.list_devices("not_config.txt")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for non-cfg file")


def test_get_device_allows_only_cfg_files() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    try:
        server.get_device("not_config.txt", "lamp")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for non-cfg file")


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


def test_attrs_across_include_boundaries() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    sensor = server.get_device("fhem.cfg", "tempSensor")
    assert sensor is not None
    attr_names = {attr["name"] for attr in sensor["attributes"]}
    assert "room" in attr_names


def test_parent_attr_applies_to_device_defined_in_include() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    device = server.get_device("include_attr_parent.cfg", "incDev")
    assert device is not None
    attrs = {attr["name"]: attr["value"] for attr in device["attributes"]}
    assert attrs["alias"] == "From Parent"


def test_no_duplicate_attributes_after_event_replay() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    lamp = server.get_device("fhem.cfg", "lamp")
    assert lamp is not None
    attrs = [a for a in lamp["attributes"] if a["name"] == "alias"]
    assert len(attrs) == 1


def test_repeated_includes_are_reprocessed_in_order() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    lamp = server.get_device("include_repeat.cfg", "lamp")
    assert lamp is not None
    assert lamp["definition_tokens"] == ["CHILD"]


def test_symlink_loop_include_is_best_effort_non_fatal(tmp_path: Path) -> None:
    cfg = tmp_path / "fhem.cfg"
    cfg.write_text("include loop.cfg\ndefine ok dummy 1\n", encoding="utf-8")
    loop = tmp_path / "loop.cfg"
    loop.symlink_to(loop)

    server = FhemMcpServer(config_root=tmp_path)
    devices = server.list_devices("fhem.cfg")

    assert any(device["name"] == "ok" for device in devices)
