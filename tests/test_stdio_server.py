import io
import json
from pathlib import Path

from fhem_mcp.stdio_server import StdioMcpServer


def _run_server_lines(lines: list[dict], config_root: Path) -> list[dict]:
    inp = io.StringIO("\n".join(json.dumps(x) for x in lines) + "\n")
    out = io.StringIO()
    StdioMcpServer(config_root=config_root).run(inp, out)
    return [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]


def test_initialize_and_list_tools() -> None:
    responses = _run_server_lines(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ],
        config_root=Path("tests/fixtures"),
    )

    assert responses[0]["id"] == 1
    assert responses[0]["result"]["protocolVersion"] == "2025-06-18"
    assert responses[0]["result"]["capabilities"] == {"tools": {}}

    tools = responses[1]["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert {"list_config_files", "read_config_file", "read_live_config_http", "list_devices", "get_device", "list_groups", "list_rooms", "find_devices_by_attr", "list_config_summary"}.issubset(names)


def test_tools_call_roundtrip() -> None:
    responses = _run_server_lines(
        [
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {"name": "list_devices", "arguments": {"relative_path": "fhem.cfg"}},
            }
        ],
        config_root=Path("tests/fixtures"),
    )

    payload = json.loads(responses[0]["result"]["content"][0]["text"])
    assert any(device["name"] == "lamp" for device in payload)




def test_tools_call_list_groups_with_filter_roundtrip() -> None:
    responses = _run_server_lines(
        [
            {
                "jsonrpc": "2.0",
                "id": 13,
                "method": "tools/call",
                "params": {"name": "list_groups", "arguments": {"relative_path": "fhem.cfg", "group_name": "Licht"}},
            }
        ],
        config_root=Path("tests/fixtures"),
    )

    payload = json.loads(responses[0]["result"]["content"][0]["text"])
    assert payload == {"Licht": ["tempSensor"]}
def test_unknown_method_returns_jsonrpc_error() -> None:
    responses = _run_server_lines(
        [{"jsonrpc": "2.0", "id": 3, "method": "unknown/method", "params": {}}],
        config_root=Path("tests/fixtures"),
    )

    assert responses[0]["error"]["code"] == -32601


def test_tools_call_file_error_returns_jsonrpc_error() -> None:
    responses = _run_server_lines(
        [
            {
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {"name": "read_config_file", "arguments": {"relative_path": "missing.cfg"}},
            }
        ],
        config_root=Path("tests/fixtures"),
    )

    assert responses[0]["result"]["isError"] is True
    assert "missing.cfg" in responses[0]["result"]["content"][0]["text"]


def test_batch_request_returns_batch_response() -> None:
    inp = io.StringIO(
        json.dumps([
            {"jsonrpc": "2.0", "id": 21, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 22, "method": "tools/list", "params": {}},
        ])
        + "\n"
    )
    out = io.StringIO()

    StdioMcpServer(config_root=Path("tests/fixtures")).run(inp, out)

    payload = json.loads(out.getvalue().strip())
    assert isinstance(payload, list)
    assert {item["id"] for item in payload} == {21, 22}


def test_batch_invalid_item_returns_invalid_request_error() -> None:
    inp = io.StringIO(json.dumps(["bad", {"jsonrpc": "2.0", "id": 31, "method": "tools/list", "params": {}}]) + "\n")
    out = io.StringIO()

    StdioMcpServer(config_root=Path("tests/fixtures")).run(inp, out)

    payload = json.loads(out.getvalue().strip())
    assert isinstance(payload, list)
    assert payload[0]["error"]["code"] == -32600
    assert payload[0]["id"] is None
    assert payload[1]["id"] == 31


def test_invalid_params_type_returns_error() -> None:
    responses = _run_server_lines(
        [{"jsonrpc": "2.0", "id": 32, "method": "tools/call", "params": []}],
        config_root=Path("tests/fixtures"),
    )

    assert responses[0]["error"]["code"] == -32602


def test_invalid_tool_arguments_type_returns_error() -> None:
    responses = _run_server_lines(
        [{"jsonrpc": "2.0", "id": 33, "method": "tools/call", "params": {"name": "list_devices", "arguments": []}}],
        config_root=Path("tests/fixtures"),
    )

    assert responses[0]["error"]["code"] == -32602


def test_unknown_tool_name_returns_invalid_params() -> None:
    responses = _run_server_lines(
        [{"jsonrpc": "2.0", "id": 34, "method": "tools/call", "params": {"name": "unknown_tool", "arguments": {}}}],
        config_root=Path("tests/fixtures"),
    )

    assert responses[0]["error"]["code"] == -32602


def test_malformed_json_returns_parse_error() -> None:
    inp = io.StringIO('{"jsonrpc": "2.0", "id": 1, "method": "tools/list"\n')
    out = io.StringIO()

    StdioMcpServer(config_root=Path("tests/fixtures")).run(inp, out)

    payload = json.loads(out.getvalue().strip())
    assert payload["id"] is None
    assert payload["error"]["code"] == -32700


def test_empty_batch_returns_invalid_request() -> None:
    inp = io.StringIO('[]\n')
    out = io.StringIO()

    StdioMcpServer(config_root=Path("tests/fixtures")).run(inp, out)

    payload = json.loads(out.getvalue().strip())
    assert payload["id"] is None
    assert payload["error"]["code"] == -32600


def test_batch_malformed_notification_returns_invalid_request() -> None:
    inp = io.StringIO(json.dumps([{"jsonrpc": "2.0"}, {"jsonrpc": "2.0", "id": 41, "method": "tools/list", "params": {}}]) + "\n")
    out = io.StringIO()

    StdioMcpServer(config_root=Path("tests/fixtures")).run(inp, out)

    payload = json.loads(out.getvalue().strip())
    assert isinstance(payload, list)
    assert payload[0]["id"] is None
    assert payload[0]["error"]["code"] == -32600
    assert payload[1]["id"] == 41


def test_initialize_negotiates_requested_supported_protocol_version() -> None:
    responses = _run_server_lines(
        [{"jsonrpc": "2.0", "id": 51, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}}],
        config_root=Path("tests/fixtures"),
    )

    assert responses[0]["result"]["protocolVersion"] == "2024-11-05"


def test_initialize_falls_back_for_unsupported_protocol_version() -> None:
    responses = _run_server_lines(
        [{"jsonrpc": "2.0", "id": 52, "method": "initialize", "params": {"protocolVersion": "2099-01-01"}}],
        config_root=Path("tests/fixtures"),
    )

    assert responses[0]["result"]["protocolVersion"] == "2025-06-18"


def test_tools_list_includes_read_live_log_http() -> None:
    responses = _run_server_lines(
        [{"jsonrpc": "2.0", "id": 61, "method": "tools/list", "params": {}}],
        config_root=Path("tests/fixtures"),
    )

    tools = responses[0]["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert "read_live_log_http" in names


def test_tools_call_read_live_log_http_roundtrip() -> None:
    server = StdioMcpServer(config_root=Path("tests/fixtures"))
    server.backend.read_live_log_http = lambda *args, **kwargs: "2026.05.25 12:00:00 1: test"

    inp = io.StringIO(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 62,
                "method": "tools/call",
                "params": {"name": "read_live_log_http", "arguments": {"base_url": "https://zeus:8088/fhem"}},
            }
        )
        + "\n"
    )
    out = io.StringIO()
    server.run(inp, out)

    response = json.loads(out.getvalue().strip())
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload == "2026.05.25 12:00:00 1: test"

