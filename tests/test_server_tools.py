from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import unquote_plus

from fhem_mcp.server import FhemMcpServer, RejectRedirectHandler

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

def test_repo_wide_group_room_summary_skip_unreadable_cfg(tmp_path: Path) -> None:
    good = tmp_path / "good.cfg"
    good.write_text("define lamp dummy\nattr lamp room Living\nattr lamp group Licht\n", encoding="utf-8")

    loop = tmp_path / "loop.cfg"
    loop.symlink_to(loop)

    server = FhemMcpServer(config_root=tmp_path)

    groups = server.list_groups()
    rooms = server.list_rooms()
    summary = server.list_config_summary()

    assert groups.get("Licht") == ["lamp"]
    assert rooms.get("Living") == ["lamp"]
    assert summary["device_count"] == 1

def test_search_config_repo_wide_skips_unreadable_cfg(tmp_path: Path) -> None:
    good = tmp_path / "good.cfg"
    good.write_text("# IMPORTANT\n", encoding="utf-8")

    loop = tmp_path / "loop.cfg"
    loop.symlink_to(loop)

    server = FhemMcpServer(config_root=tmp_path)
    matches = server.search_config("IMPORTANT")

    assert any(item["file"] == "good.cfg" for item in matches)

def test_read_live_config_http_builds_expected_request() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    class _Resp:
        def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
            self._body = body
            self.headers = headers or {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return self._body

    responses = [
        _Resp(b"", {"X-FHEM-csrfToken": "csrf_123"}),
        _Resp(b"<html><textarea>define x dummy 1\n</textarea></html>"),
    ]

    with patch("fhem_mcp.server.urlopen", side_effect=responses) as mocked_urlopen:
        payload = server.read_live_config_http(
            "http://127.0.0.1:8083/fhem",
            "fhem.cfg",
            timeout_seconds=3.5,
            username="alice",
            password="secret",
        )

    assert payload == "define x dummy 1\n"
    token_request = mocked_urlopen.call_args_list[0].args[0]
    command_request = mocked_urlopen.call_args_list[1].args[0]
    assert mocked_urlopen.call_args_list[0].kwargs["timeout"] == 3.5
    assert mocked_urlopen.call_args_list[1].kwargs["timeout"] == 3.5
    assert token_request.full_url.endswith("?XHR=1")
    assert command_request.full_url.startswith("http://127.0.0.1:8083/fhem?")
    assert "cmd=style+edit+fhem.cfg" in command_request.full_url
    assert "fwcsrf=csrf_123" in command_request.full_url
    assert "XHR=1" not in command_request.full_url
    assert token_request.get_header("Authorization").startswith("Basic ")
    assert command_request.get_header("Authorization").startswith("Basic ")

def test_read_live_config_http_uses_custom_ca_bundle() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    class _Resp:
        def __init__(self, headers: dict[str, str] | None = None, body: bytes = b"") -> None:
            self.headers = headers or {}
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return self._body

    responses = [
        _Resp(headers={"X-FHEM-csrfToken": "csrf_123"}),
        _Resp(body=b"ok\n"),
    ]

    with patch("fhem_mcp.server.create_default_context", return_value="CTX") as mk_ctx:
        with patch("fhem_mcp.server.urlopen", side_effect=responses) as mocked_urlopen:
            payload = server.read_live_config_http(
                "https://zeus:8088",
                ca_file="/opt/docker/rootca/ca.pem",
                ca_path="/opt/docker/rootca",
            )

    assert payload == "ok\n"
    mk_ctx.assert_called_once_with(cafile="/opt/docker/rootca/ca.pem", capath="/opt/docker/rootca")
    assert mocked_urlopen.call_args_list[0].kwargs["context"] == "CTX"
    assert mocked_urlopen.call_args_list[1].kwargs["context"] == "CTX"

def test_read_live_config_http_rejects_invalid_inputs() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    for base_url in (
        "ftp://127.0.0.1/fhem",
        "http:///fhem",
        "https://zeus:8088/fhem?cmd=shutdown",
        "https://zeus:8088/fhem#frag",
    ):
        try:
            server.read_live_config_http(base_url=base_url)
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError for invalid base_url")

    for config_path in ("", "fhem.conf", "fhem.cfg;shutdown"):
        try:
            server.read_live_config_http(base_url="http://127.0.0.1:8083/fhem", config_path=config_path)
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError for invalid config_path")

    try:
        server.read_live_config_http(base_url="http://127.0.0.1:8083/fhem", timeout_seconds=0)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for invalid timeout")

    for bad in ("", "   "):
        try:
            server.read_live_config_http(base_url="https://127.0.0.1:8088", ca_file=bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError for invalid ca_file")

def test_read_live_config_http_requires_username_and_password_together() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    try:
        server.read_live_config_http(base_url="http://127.0.0.1:8083/fhem", username="alice")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for incomplete basic auth")

def test_read_live_config_http_without_fwcsrf_header_still_reads() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    class _Resp:
        def __init__(self, headers: dict[str, str] | None = None, body: bytes = b"") -> None:
            self.headers = headers or {}
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return self._body

    responses = [_Resp(headers={}), _Resp(body=b"<html><textarea>ok\n</textarea></html>")]
    with patch("fhem_mcp.server.urlopen", side_effect=responses) as mocked_urlopen:
        payload = server.read_live_config_http(base_url="http://127.0.0.1:8083/fhem")

    assert payload == "ok\n"
    command_request = mocked_urlopen.call_args_list[1].args[0]
    assert "fwcsrf=" not in command_request.full_url

def test_read_live_log_http_filters_and_limits_lines() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    log_body = """2026.05.25 12:00:00 1: ASC bu.Markise sunny\n2026.05.25 12:01:00 1: ASC bu.Markise cloudy\n2026.05.25 12:02:00 1: ASC dg.Rolladen1 sunny\n"""

    with patch.object(server, "read_live_config_http", return_value=log_body) as mocked_read:
        payload = server.read_live_log_http(
            base_url="https://zeus:8088/fhem",
            contains="asc",
            regex="bu\\.Markise",
            since="2026-05-25 12:00:30",
            until="2026-05-25 12:01:30",
            max_lines=10,
            ignore_case=True,
        )

    mocked_read.assert_called_once()
    assert payload == "2026.05.25 12:01:00 1: ASC bu.Markise cloudy"

def test_read_live_log_http_rejects_invalid_inputs() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    try:
        server.read_live_log_http(base_url="https://zeus:8088/fhem", max_lines=-1)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for invalid max_lines")

    try:
        server.read_live_log_http(base_url="https://zeus:8088/fhem", since="2026/05/25 12:00:00")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for invalid since format")


def test_read_live_log_http_with_zero_max_lines_returns_empty() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    log_body = """2026.05.25 12:00:00 1: ASC one\n2026.05.25 12:01:00 1: ASC two\n"""

    with patch.object(server, "read_live_config_http", return_value=log_body):
        payload = server.read_live_log_http(
            base_url="https://zeus:8088/fhem",
            contains="ASC",
            max_lines=0,
        )

    assert payload == ""

def test_list_live_logs_http_rejects_base_url_with_query_or_fragment() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    for base_url in ("https://zeus:8088/fhem?cmd=list", "https://zeus:8088/fhem#x"):
        try:
            server.list_live_logs_http(base_url=base_url)
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError for unsafe base_url")

def test_list_live_logs_http_parses_filelog_jsonlist2() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    class _Resp:
        def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
            self._body = body
            self.headers = headers or {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return self._body

    payload = (
        '{"Results":['
        '{"Name":"FileLog_fhem","DEF":"./log/fhem-%Y-%m-%d.log fhem:.*",'
        '"Internals":{"currentlogfile":"./log/fhem-2026-05-25.log"}},'
        '{"Name":"FileLog_asc","DEF":"./log/asc-%Y-%m-%d.log ASC:.*",'
        '"Internals":{"currentlogfile":"./log/asc-2026-05-25.log"}}]}'
    )
    responses = [
        _Resp(b"", {"X-FHEM-csrfToken": "csrf_123"}),
        _Resp(payload.encode("utf-8")),
    ]

    with patch("fhem_mcp.server.urlopen", side_effect=responses) as mocked_urlopen:
        result = server.list_live_logs_http(base_url="https://zeus:8088/fhem")

    assert len(result["devices"]) == 2
    assert "./log/fhem-%Y-%m-%d.log" in result["log_patterns"]
    assert "./log/asc-2026-05-25.log" in result["current_logfiles"]

    cmd_request = mocked_urlopen.call_args_list[1].args[0]
    assert "cmd=jsonlist2+TYPE%3DFileLog" in cmd_request.full_url

def test_get_live_device_http_normalizes_jsonlist2_snapshot_and_request() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    class _Resp:
        headers: dict[str, str] = {}

        def __init__(self, body: bytes) -> None:
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return self._body

    response = {
        "Results": [
            {
                "Name": "living.room-lamp",
                "Internals": {"TYPE": "dummy", "STATE": "on"},
                "Attributes": {"alias": "Living room", "room": "Lights"},
                "Readings": {
                    "state": {"Value": "on", "Time": "2026-07-15 10:11:12"},
                    "battery": {"Value": "87", "Time": "2026-07-15 09:00:00"},
                },
                "PossibleSets": "off on toggle",
                "PossibleAttrs": "alias room group",
            }
        ]
    }

    with patch("fhem_mcp.server.urlopen", return_value=_Resp(__import__("json").dumps(response).encode())) as mocked_urlopen:
        result = server.get_live_device_http(
            base_url="https://zeus:8088/fhem",
            device_name="living.room-lamp",
            fwcsrf="csrf token",
            timeout_seconds=2.5,
            username="alice",
            password="secret",
        )

    assert result == {
        "name": "living.room-lamp",
        "internals": {"TYPE": "dummy", "STATE": "on"},
        "attributes": {"alias": "Living room", "room": "Lights"},
        "readings": {
            "state": {"value": "on", "time": "2026-07-15 10:11:12"},
            "battery": {"value": "87", "time": "2026-07-15 09:00:00"},
        },
        "possible_sets": "off on toggle",
        "possible_attributes": "alias room group",
    }
    request = mocked_urlopen.call_args.args[0]
    assert request.full_url == (
        "https://zeus:8088/fhem?cmd=jsonlist2+living.room-lamp&XHR=1&fwcsrf=csrf+token"
    )
    assert request.get_header("Authorization").startswith("Basic ")
    assert mocked_urlopen.call_args.kwargs["timeout"] == 2.5

def test_get_live_device_http_returns_none_for_absent_device() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    with patch.object(server, "_http_get_text", return_value='{"Results":[]}'):
        result = server.get_live_device_http(
            base_url="https://zeus:8088/fhem",
            device_name="missing",
            fwcsrf="csrf_123",
        )

    assert result is None


def test_get_live_device_http_uses_configured_default_base_url() -> None:
    server = FhemMcpServer(
        config_root=Path("tests/fixtures"),
        active_runtime_base_url="https://default.example/fhem",
    )

    with patch.object(server, "_fetch_fwcsrf_http", return_value=None), patch.object(
        server, "_http_get_text", return_value='{"Results": []}'
    ) as http_get:
        result = server.get_live_device_http(None, "lamp")

    assert result is None
    assert http_get.call_args.args[0].startswith(
        "https://default.example/fhem?cmd=jsonlist2+lamp&XHR=1"
    )


def test_read_only_http_tool_without_any_base_url_fails_clearly() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    try:
        server.get_live_device_http(None, "lamp")
    except ValueError as exc:
        assert str(exc) == (
            "base_url is required when active_runtime_base_url is not configured"
        )
    else:
        raise AssertionError("Expected missing default URL to fail")

def test_get_live_device_http_rejects_unsafe_device_names() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    for device_name in ("", "lamp;shutdown", "lamp TYPE=dummy", "lamp\nshutdown"):
        try:
            server.get_live_device_http(
                base_url="https://zeus:8088/fhem",
                device_name=device_name,
                fwcsrf="csrf_123",
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected ValueError for unsafe device name: {device_name!r}")

def test_get_live_device_http_rejects_invalid_connection_inputs() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    invalid_arguments = (
        {"base_url": "ftp://zeus/fhem"},
        {"base_url": "https://zeus/fhem?cmd=list"},
        {"base_url": "https://zeus/fhem", "timeout_seconds": 0},
        {"base_url": "https://zeus/fhem", "username": "alice"},
    )
    for arguments in invalid_arguments:
        try:
            server.get_live_device_http(
                device_name="lamp",
                fwcsrf="csrf_123",
                **arguments,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected ValueError for invalid arguments: {arguments!r}")

def test_get_live_device_http_rejects_malformed_jsonlist2_structures() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))
    malformed_responses = (
        "not json",
        "{}",
        '{"Results":{}}',
        '{"Results":["lamp"]}',
        '{"Results":[{"Name":"lamp"},{"Name":"lamp"}]}',
        '{"Results":[{"Name":"lamp","Readings":[]}]}',
    )

    for response in malformed_responses:
        with patch.object(server, "_http_get_text", return_value=response):
            try:
                server.get_live_device_http(
                    base_url="https://zeus:8088/fhem",
                    device_name="lamp",
                    fwcsrf="csrf_123",
                )
            except ValueError:
                pass
            else:
                raise AssertionError(f"Expected ValueError for malformed response: {response}")


def test_observe_live_events_http_reads_bounded_event_stream() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    class _TokenResp:
        headers = {"X-FHEM-csrfToken": "csrf_123"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _StreamResp:
        headers: dict[str, str] = {}

        def __init__(self, lines: list[bytes]) -> None:
            self._lines = lines

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def readline(self):
            if self._lines:
                return self._lines.pop(0)
            return b""

    lines = [
        b'["dummy","lamp","state: on"]\n',
        b'{"device":"tempSensor","type":"MQTT2_DEVICE","event":"temperature: 21.4"}\n',
        b'2026-06-03 12:00:01 dummy button pressed<br>\n',
    ]

    with patch("fhem_mcp.server.urlopen", side_effect=[_TokenResp(), _StreamResp(lines)]) as mocked_urlopen:
        result = server.observe_live_events_http(
            base_url="https://zeus:8088/fhem",
            duration_seconds=10,
            event_monitor_filter="TYPE=dummy",
            max_events=10,
            username="alice",
            password="secret",
        )

    assert result["event_count"] == 3
    assert result["truncated"] is False
    assert result["summary"]["devices"] == {"button": 1, "lamp": 1, "tempSensor": 1}
    assert result["summary"]["readings"] == {"state": 1, "temperature": 1}
    assert result["events"][0]["device"] == "lamp"
    assert result["events"][0]["reading"] == "state"
    assert result["events"][0]["value"] == "on"
    assert result["events"][2]["device"] == "button"
    assert result["events"][2]["event"] == "pressed"

    token_request = mocked_urlopen.call_args_list[0].args[0]
    request = mocked_urlopen.call_args_list[1].args[0]
    assert token_request.full_url.endswith("?XHR=1")
    assert request.full_url.startswith("https://zeus:8088/fhem?")
    assert "XHR=1" in request.full_url
    assert "inform=type=raw;filter=^\\S+\\s+\\S+\\s+dummy\\s+;fmt=JSON" in unquote_plus(request.full_url)
    assert "fwcsrf=csrf_123" in request.full_url
    assert token_request.get_header("Authorization").startswith("Basic ")
    assert request.get_header("Authorization").startswith("Basic ")


def test_observe_live_events_http_translates_type_filter_to_raw_regex() -> None:
    assert FhemMcpServer._build_raw_event_monitor_filter("TYPE=MQTT2_DEVICE") == r"^\S+\s+\S+\s+MQTT2_DEVICE\s+"
    assert FhemMcpServer._build_raw_event_monitor_filter("Lichtvoute") == "Lichtvoute"

def test_observe_live_events_http_omits_fwcsrf_when_fhem_has_no_token() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    class _TokenResp:
        headers: dict[str, str] = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _StreamResp:
        headers: dict[str, str] = {}

        def __init__(self) -> None:
            self._lines = [b'["dummy","lamp","state: on"]\n']

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def readline(self):
            if self._lines:
                return self._lines.pop(0)
            return b""

    with patch("fhem_mcp.server.urlopen", side_effect=[_TokenResp(), _StreamResp()]) as mocked_urlopen:
        result = server.observe_live_events_http(
            base_url="http://127.0.0.1:8088/fhem",
            duration_seconds=5,
            max_events=5,
        )

    request = mocked_urlopen.call_args_list[1].args[0]
    assert "fwcsrf=" not in request.full_url
    assert result["event_count"] == 1
    assert result["events"][0]["device"] == "lamp"

def test_observe_live_events_http_parses_millisecond_timestamps() -> None:
    event = FhemMcpServer._parse_event_payload("2026-06-03 12:00:01.123 dummy lamp state: on")

    assert event.device_type == "dummy"
    assert event.device == "lamp"
    assert event.reading == "state"
    assert event.value == "on"
    assert event.event == "state: on"

def test_observe_live_events_http_filters_and_truncates() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    class _StreamResp:
        headers: dict[str, str] = {}

        def __init__(self) -> None:
            self._lines = [
                b'["dummy","lamp","state: on"]\n',
                b'["dummy","other","state: off"]\n',
                b'["dummy","lamp","battery: ok"]\n',
                b'["dummy","lamp","state: off"]\n',
            ]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def readline(self):
            if self._lines:
                return self._lines.pop(0)
            return b""

    with patch("fhem_mcp.server.urlopen", return_value=_StreamResp()):
        result = server.observe_live_events_http(
            base_url="http://127.0.0.1:8083/fhem",
            duration_seconds=10,
            device_regex="^lamp$",
            event_regex="^state:",
            max_events=1,
            fwcsrf="",
        )

    assert result["event_count"] == 1
    assert result["truncated"] is True
    assert result["events"][0]["device"] == "lamp"
    assert result["events"][0]["event"] == "state: on"

def test_observe_live_events_http_rejects_invalid_inputs() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    invalid_calls = [
        {"base_url": "ftp://127.0.0.1/fhem"},
        {"base_url": "http://127.0.0.1:8083/fhem?cmd=list"},
        {"base_url": "http://127.0.0.1:8083/fhem", "duration_seconds": 0},
        {"base_url": "http://127.0.0.1:8083/fhem", "duration_seconds": 61},
        {"base_url": "http://127.0.0.1:8083/fhem", "max_events": 0},
        {"base_url": "http://127.0.0.1:8083/fhem", "max_events": 5001},
        {"base_url": "http://127.0.0.1:8083/fhem", "timeout_seconds": 0},
        {"base_url": "http://127.0.0.1:8083/fhem", "event_monitor_filter": "   "},
        {"base_url": "http://127.0.0.1:8083/fhem", "device_regex": "["},
        {"base_url": "http://127.0.0.1:8083/fhem", "username": "alice"},
    ]

    for kwargs in invalid_calls:
        try:
            server.observe_live_events_http(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected ValueError for {kwargs}")


def test_observe_live_events_http_read_timeout_keeps_observing_until_deadline() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    class _Sock:
        def __init__(self) -> None:
            self.timeouts: list[float] = []

        def settimeout(self, timeout: float) -> None:
            self.timeouts.append(timeout)

    class _Raw:
        def __init__(self, sock: _Sock) -> None:
            self._sock = sock

    class _Fp:
        def __init__(self, sock: _Sock) -> None:
            self.raw = _Raw(sock)

    class _IntermittentResp:
        headers: dict[str, str] = {}

        def __init__(self) -> None:
            self.sock = _Sock()
            self.fp = _Fp(self.sock)
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def readline(self):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("idle stream")
            if self.calls == 2:
                return b'["dummy","lamp","state: on"]\n'
            return b""

    response = _IntermittentResp()
    monotonic_values = [0.0, 0.0, 3.0, 3.0, 3.0, 3.0]

    with patch("fhem_mcp.server.urlopen", return_value=response) as mocked_urlopen:
        with patch("fhem_mcp.server.monotonic", side_effect=monotonic_values):
            result = server.observe_live_events_http(
                base_url="http://127.0.0.1:8083/fhem",
                duration_seconds=10,
                timeout_seconds=5,
                event_monitor_filter="rareDevice",
                fwcsrf="",
            )

    assert mocked_urlopen.call_args.kwargs["timeout"] == 5
    assert response.sock.timeouts[:2] == [10.0, 7.0]
    assert result["event_count"] == 1
    assert result["events"][0]["device"] == "lamp"
    assert result["truncated"] is False

def test_list_devices_table_output_is_compact_and_paginated() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    first = server.list_devices(
        "fhem.cfg",
        format="table",
        include_source=False,
        limit=1,
    )

    assert first == {
        "meta": {
            "format": "table",
            "complete": False,
            "omitted": ["source", "remaining_rows"],
            "request_more": {"cursor": "1"},
            "request_details": {"include_source": True},
        },
        "columns": ["name", "type"],
        "rows": [["lamp", "dummy"]],
        "count": 1,
        "truncated": True,
        "next_cursor": "1",
    }

    follow_up = server.list_devices(
        "fhem.cfg",
        format="table",
        include_source=False,
        limit=1,
        **first["meta"]["request_more"],
    )
    assert follow_up["columns"] == first["columns"]
    assert follow_up["meta"]["request_details"] == {"include_source": True}

    second = server.list_devices(
        "fhem.cfg",
        format="table",
        include_source=True,
        limit=1,
        cursor=first["next_cursor"],
    )
    assert second["meta"] == {
        "format": "table",
        "complete": True,
        "omitted": [],
    }
    assert second["columns"] == ["name", "type", "file", "line"]
    assert second["rows"][0][2] == "extras.cfg"
    assert second["truncated"] is False

def test_list_devices_table_rejects_invalid_pagination() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    for invalid in ("-1", "not-a-cursor"):
        try:
            server.list_devices("fhem.cfg", format="table", cursor=invalid)
        except ValueError as exc:
            assert "cursor" in str(exc)
        else:
            raise AssertionError("Expected invalid cursor to fail")

def test_get_device_compact_output_omits_redundant_details() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))

    compact = server.get_device(
        "fhem.cfg",
        "lamp",
        format="compact",
        include_source=True,
    )

    assert compact is not None
    assert compact["meta"] == {
        "format": "compact",
        "complete": False,
        "omitted": ["raw_lines", "definition"],
        "request_more": {"format": "full"},
    }
    assert compact["name"] == "lamp"
    assert compact["type"] == "dummy"
    assert compact["source"] == {"file": "fhem.cfg", "line": 2}
    assert compact["attributes"]["alias"] == "Living Room Lamp"
    assert compact["attribute_sources"]["alias"]["file"] == "fhem.cfg"
    assert "definition" not in compact
    assert "raw_line" not in compact["source"]
    assert all("raw_line" not in source for source in compact["attribute_sources"].values())

def test_read_live_log_http_paged_preserves_exact_lines_and_paginates() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))
    lines = [
        "2026.05.25 12:00:00 1: keep context before",
        "2026.05.25 12:01:00 3: exact ERROR alpha: value=1",
        "2026.05.25 12:02:00 1: keep context middle",
        "2026.05.25 12:03:00 3: exact ERROR beta: value=2",
        "2026.05.25 12:04:00 1: keep context after",
    ]
    log_body = "\n".join(lines) + "\n"

    with patch.object(server, "read_live_config_http", return_value=log_body):
        first = server.read_live_log_http(
            base_url="https://zeus:8088/fhem",
            contains="ERROR",
            max_lines=1,
            response_format="paged",
            context_lines=1,
        )
        second = server.read_live_log_http(
            base_url="https://zeus:8088/fhem",
            contains="ERROR",
            max_lines=1,
            response_format="paged",
            cursor=first["next_cursor"],
        )

    assert first["text"] == "\n".join(lines[2:5])
    assert first["matched"] == 2
    assert first["returned_matches"] == 1
    assert first["returned_lines"] == 3
    assert first["truncated"] is True
    assert isinstance(first["next_cursor"], str)
    assert first["next_cursor"] != "1"
    assert first["meta"] == {
        "format": "raw",
        "complete": False,
        "omitted": ["other_matches"],
        "request_more": {
            "response_format": "paged",
            "cursor": first["next_cursor"],
        },
    }
    assert second["text"] == lines[1]
    assert second["truncated"] is False
    assert second["meta"] == {
        "format": "raw",
        "complete": True,
        "omitted": [],
    }
    assert "next_cursor" not in second

def test_read_live_log_http_paged_rejects_invalid_options() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))
    with patch.object(server, "read_live_config_http", return_value="line"):
        for kwargs in (
            {"response_format": "paged", "max_lines": 0},
            {"response_format": "paged", "cursor": "invalid"},
            {"response_format": "paged", "context_lines": -1},
            {"response_format": "text", "context_lines": 1},
        ):
            try:
                server.read_live_log_http(
                    base_url="https://zeus:8088/fhem",
                    **kwargs,
                )
            except ValueError:
                pass
            else:
                raise AssertionError(f"Expected invalid options to fail: {kwargs}")


def test_read_live_log_http_cursor_is_stable_when_new_matches_arrive() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))
    original_lines = [
        "2026.05.25 12:00:00 3: exact ERROR oldest",
        "2026.05.25 12:01:00 3: exact ERROR middle",
        "2026.05.25 12:02:00 3: exact ERROR newest",
    ]
    appended_lines = original_lines + [
        "2026.05.25 12:03:00 3: exact ERROR appended",
    ]

    with patch.object(
        server,
        "read_live_config_http",
        side_effect=["\n".join(original_lines), "\n".join(appended_lines)],
    ):
        first = server.read_live_log_http(
            base_url="https://zeus:8088/fhem",
            contains="ERROR",
            max_lines=1,
            response_format="paged",
        )
        second = server.read_live_log_http(
            base_url="https://zeus:8088/fhem",
            contains="ERROR",
            max_lines=1,
            response_format="paged",
            cursor=first["next_cursor"],
        )

    assert first["text"] == original_lines[2]
    assert second["text"] == original_lines[1]
    assert "appended" not in second["text"]
    assert second["next_cursor"] != first["next_cursor"]

def test_read_live_log_http_cursor_rejects_changed_query_or_anchor() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))
    lines = [
        "2026.05.25 12:00:00 3: exact ERROR oldest",
        "2026.05.25 12:01:00 3: exact ERROR newest",
    ]
    with patch.object(server, "read_live_config_http", return_value="\n".join(lines)):
        first = server.read_live_log_http(
            base_url="https://zeus:8088/fhem",
            contains="ERROR",
            max_lines=1,
            response_format="paged",
        )

    changed_anchor = [lines[0], "2026.05.25 12:01:00 3: replaced ERROR newest"]
    for log_body, contains in (("\n".join(lines), "WARN"), ("\n".join(changed_anchor), "ERROR")):
        with patch.object(server, "read_live_config_http", return_value=log_body):
            try:
                server.read_live_log_http(
                    base_url="https://zeus:8088/fhem",
                    contains=contains,
                    max_lines=1,
                    response_format="paged",
                    cursor=first["next_cursor"],
                )
            except ValueError as exc:
                assert "cursor" in str(exc)
            else:
                raise AssertionError("Expected mismatched cursor to fail")


def test_run_live_get_http_enabled_transport_and_response() -> None:
    server = FhemMcpServer(
        config_root=Path("tests/fixtures"),
        enable_get=True,
        active_runtime_base_url="https://zeus:8088/fhem",
    )

    class _Resp:
        headers: dict[str, str] = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b"line one\nline two\n"

    class _Opener:
        def __init__(self) -> None:
            self.request = None
            self.timeout = None

        def open(self, request, *, timeout):
            self.request = request
            self.timeout = timeout
            return _Resp()

    opener = _Opener()

    with patch("fhem_mcp.server.create_default_context", return_value="TLS") as tls_context, patch(
        "fhem_mcp.server.build_opener", return_value=opener
    ) as mocked_build_opener:
        result = server.run_live_get_http(
            "Weather", "  forecast tomorrow  ",
            fwcsrf="csrf token", timeout_seconds=2.5, username="alice",
            password="secret", ca_file="/certs/ca.pem",
        )

    assert result == {
        "device_name": "Weather", "get_option": "forecast",
        "get_parameters": "forecast tomorrow", "response": "line one\nline two\n",
    }
    request = opener.request
    assert request.full_url == "https://zeus:8088/fhem?cmd=get+Weather+forecast+tomorrow&XHR=1&fwcsrf=csrf+token"
    assert request.get_header("Authorization").startswith("Basic ")
    assert opener.timeout == 2.5
    handler_names = {type(handler).__name__ for handler in mocked_build_opener.call_args.args}
    assert handler_names == {"RejectRedirectHandler", "HTTPSHandler"}
    tls_context.assert_called_once_with(cafile="/certs/ca.pem", capath=None)


def test_run_live_set_http_enabled_transport_and_response() -> None:
    server = FhemMcpServer(
        config_root=Path("tests/fixtures"),
        enable_set=True,
        active_runtime_base_url="http://fhem:8083/fhem",
    )
    with patch.object(server, "_http_get_text_no_redirects", return_value="") as request:
        result = server.run_live_set_http(
            "lamp", "  desired-temp 21.5  ", fwcsrf="token"
        )
    assert result == {
        "device_name": "lamp", "set_option": "desired-temp",
        "set_parameters": "desired-temp 21.5", "response": "",
    }
    assert "cmd=set+lamp+desired-temp+21.5&XHR=1&fwcsrf=token" in request.call_args.args[0]


def test_active_commands_reject_all_redirects_without_following_target() -> None:
    handler = RejectRedirectHandler()
    for status in (301, 302, 307, 308):
        assert handler.redirect_request(
            None, None, status, "redirect", {"Location": "https://evil.example/fhem"},
            "https://evil.example/fhem",
        ) is None

    server = FhemMcpServer(
        config_root=Path("tests/fixtures"), enable_set=True,
        active_runtime_base_url="https://approved.example/fhem",
    )

    class _RedirectingOpener:
        calls = 0

        def open(self, request, *, timeout):
            self.calls += 1
            raise HTTPError(
                request.full_url, 302, "Found",
                {"Location": "https://evil.example/fhem"}, None,
            )

    opener = _RedirectingOpener()
    with patch("fhem_mcp.server.build_opener", return_value=opener):
        try:
            server.run_live_set_http("lamp", "on", fwcsrf="token")
        except HTTPError as exc:
            assert exc.code == 302
        else:
            raise AssertionError("Expected redirect to be rejected")
    assert opener.calls == 1

    token_opener = _RedirectingOpener()
    with patch("fhem_mcp.server.build_opener", return_value=token_opener):
        try:
            server.run_live_set_http(
                "lamp", "on", username="alice", password="secret"
            )
        except HTTPError as exc:
            assert exc.code == 302
        else:
            raise AssertionError("Expected CSRF token redirect to be rejected")
    assert token_opener.calls == 1


def test_active_commands_require_operator_approved_endpoint() -> None:
    for switch in ({"enable_get": True}, {"enable_set": True}):
        try:
            FhemMcpServer(config_root=Path("tests/fixtures"), **switch)
        except ValueError as exc:
            assert "active_runtime_base_url is required" in str(exc)
        else:
            raise AssertionError("Expected enabled active command without endpoint to fail")


def test_live_get_and_set_are_disabled_by_default_before_network() -> None:
    server = FhemMcpServer(config_root=Path("tests/fixtures"))
    calls = (
        (server.run_live_get_http, "status", "--enable-get"),
        (server.run_live_set_http, "on", "--enable-set"),
    )
    for method, parameters, switch in calls:
        with patch("fhem_mcp.server.urlopen") as no_network:
            try:
                method("lamp", parameters, fwcsrf=None)
            except ValueError as exc:
                assert switch in str(exc)
            else:
                raise AssertionError("Expected disabled command to fail")
            no_network.assert_not_called()


def test_live_get_and_set_reject_unsafe_inputs_before_network() -> None:
    server = FhemMcpServer(
        config_root=Path("tests/fixtures"), enable_get=True, enable_set=True,
        active_runtime_base_url="http://fhem:8083/fhem",
    )
    unsafe = ("", "   ", "status;shutdown", "status\nshutdown", "status\targ", "status\0arg", "status\x7farg")
    for method in (server.run_live_get_http, server.run_live_set_http):
        for parameters in unsafe:
            with patch("fhem_mcp.server.urlopen") as no_network:
                try:
                    method("lamp", parameters, fwcsrf=None)
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"Expected rejection for {parameters!r}")
                no_network.assert_not_called()

        for device in ("", "TYPE=dummy", "lamp;shutdown", "lamp other"):
            with patch("fhem_mcp.server.urlopen") as no_network:
                try:
                    method(device, "status", fwcsrf=None)
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"Expected rejection for {device!r}")
                no_network.assert_not_called()
