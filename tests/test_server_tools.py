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


def test_list_groups_and_rooms() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    groups = server.list_groups("fhem.cfg")
    assert groups["Licht"] == ["tempSensor"]
    assert groups["Klima"] == ["tempSensor"]

    rooms = server.list_rooms("fhem.cfg")
    assert rooms["Sensors"] == ["tempSensor"]
    assert rooms["system->Datenbank"] == ["tempSensor"]


def test_list_groups_with_group_name_filter() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    filtered = server.list_groups("fhem.cfg", "Licht")
    assert filtered == {"Licht": ["tempSensor"]}


def test_list_attributes_and_finders() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    attrs = server.list_attributes("fhem.cfg", "tempSensor")
    names = {a["name"] for a in attrs["tempSensor"]}
    assert {"room", "group", "genericDeviceType"}.issubset(names)

    by_attr = server.find_devices_by_attr("fhem.cfg", "genericDeviceType", "light")
    assert any(item["name"] == "tempSensor" for item in by_attr)

    by_type = server.find_devices_by_type("fhem.cfg", "MQTT2_DEVICE")
    assert any(item["name"] == "tempSensor" for item in by_type)


def test_list_includes_and_summary() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    includes = server.list_includes("fhem.cfg")
    assert any(item["include_path"] == "extras.cfg" and item["exists"] for item in includes)

    summary = server.list_config_summary("fhem.cfg")
    assert summary["device_count"] >= 2
    assert summary["type_counts"]["dummy"] >= 1
    assert summary["room_assignment_count"] >= 1


def test_search_validate_and_get_device_full() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    matches = server.search_config("attr tempSensor room", "fhem.cfg")
    assert any(item["file"] == "extras.cfg" for item in matches)

    validation = server.validate_config("include_missing.cfg")
    assert any(err["type"] == "missing_include" for err in validation["errors"])

    full = server.get_device_full("tempSensor")
    assert full is not None
    assert full["device_type"] == "MQTT2_DEVICE"


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

def test_list_includes_symlink_loop_is_best_effort_non_fatal(tmp_path: Path) -> None:
    cfg = tmp_path / "fhem.cfg"
    cfg.write_text("include loop.cfg\ndefine ok dummy 1\n", encoding="utf-8")
    loop = tmp_path / "loop.cfg"
    loop.symlink_to(loop)

    server = FhemMcpServer(config_root=tmp_path)
    includes = server.list_includes("fhem.cfg")

    assert len(includes) == 1
    assert includes[0]["include_path"] == "loop.cfg"
    assert includes[0]["exists"] is False
    assert includes[0]["resolved_path"] is None

def test_validate_config_symlink_loop_include_is_best_effort_non_fatal(tmp_path: Path) -> None:
    cfg = tmp_path / "fhem.cfg"
    cfg.write_text("include loop.cfg\ndefine ok dummy 1\n", encoding="utf-8")
    loop = tmp_path / "loop.cfg"
    loop.symlink_to(loop)

    server = FhemMcpServer(config_root=tmp_path)
    result = server.validate_config("fhem.cfg")

    assert any(err["type"] == "missing_include" and err["include_path"] == "loop.cfg" for err in result["errors"])

def test_search_config_relative_path_includes_comment_only_child(tmp_path: Path) -> None:
    root = tmp_path / "main.cfg"
    child = tmp_path / "child.cfg"
    root.write_text("include child.cfg\n", encoding="utf-8")
    child.write_text("# IMPORTANT\n", encoding="utf-8")

    server = FhemMcpServer(config_root=tmp_path)
    matches = server.search_config("IMPORTANT", "main.cfg")

    assert any(item["file"] == "child.cfg" for item in matches)


def test_validate_config_relative_path_checks_included_files(tmp_path: Path) -> None:
    root = tmp_path / "root.cfg"
    child = tmp_path / "child.cfg"
    root.write_text("include child.cfg\n", encoding="utf-8")
    child.write_text("define dup dummy\ndefine dup dummy\n", encoding="utf-8")

    server = FhemMcpServer(config_root=tmp_path)
    result = server.validate_config("root.cfg")

    assert any(err["type"] == "duplicate_device" and err["device"] == "dup" for err in result["errors"])

def test_validate_config_repo_wide_skips_unreadable_cfg_and_continues(tmp_path: Path) -> None:
    good = tmp_path / "good.cfg"
    good.write_text("define ok dummy\n", encoding="utf-8")

    loop = tmp_path / "loop.cfg"
    loop.symlink_to(loop)

    server = FhemMcpServer(config_root=tmp_path)
    result = server.validate_config()

    # best-effort: unreadable cfg is reported, validation still returns structured result
    assert "errors" in result
    assert any(err["type"] == "unreadable_config_file" and err["file"] == "loop.cfg" for err in result["errors"])


def test_get_device_full_merges_attributes_across_entry_contexts(tmp_path: Path) -> None:
    first = tmp_path / "01-root.cfg"
    second = tmp_path / "02-root.cfg"
    child = tmp_path / "child.cfg"

    first.write_text("define d dummy\n", encoding="utf-8")
    second.write_text("include child.cfg\n", encoding="utf-8")
    child.write_text("define d dummy\nattr d room Kitchen\n", encoding="utf-8")

    server = FhemMcpServer(config_root=tmp_path)
    full = server.get_device_full("d")

    assert full is not None
    attr_names = {a["name"] for a in full["attributes"]}
    assert "room" in attr_names
