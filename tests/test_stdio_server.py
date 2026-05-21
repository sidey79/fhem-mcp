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
    assert responses[0]["result"]["capabilities"] == {"tools": {}}

    tools = responses[1]["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert {"list_config_files", "read_config_file", "list_devices", "get_device"}.issubset(names)


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

    assert responses[0]["error"]["code"] == -32002
