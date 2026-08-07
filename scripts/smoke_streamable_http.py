#!/usr/bin/env python3
"""Exercise the stateful Streamable HTTP bridge without external packages."""

from __future__ import annotations

import json
import sys
import urllib.request


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
MCP_URL = f"{BASE_URL.rstrip('/')}/mcp"
HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def post(payload: dict[str, object], session_id: str | None = None) -> tuple[dict[str, object] | None, str | None]:
    headers = dict(HEADERS)
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    request = urllib.request.Request(
        MCP_URL,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        body = response.read().decode()
        response_session = response.headers.get("Mcp-Session-Id") or session_id
        if not body:
            return None, response_session
        if response.headers.get_content_type() == "text/event-stream":
            data_lines = [line[6:] for line in body.splitlines() if line.startswith("data: ")]
            body = data_lines[-1]
        return json.loads(body), response_session


with urllib.request.urlopen(f"{BASE_URL.rstrip('/')}/status", timeout=5) as response:
    assert response.status == 200

initialized, session = post(
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "compose-smoke", "version": "1"},
        },
    }
)
assert initialized and "result" in initialized, initialized
assert session, "The stateful endpoint did not return an Mcp-Session-Id"
post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session)

tools, _ = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session)
tool_names = {tool["name"] for tool in tools["result"]["tools"]}  # type: ignore[index]
assert "list_config_files" in tool_names, tool_names

result, _ = post(
    {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "list_config_files", "arguments": {}},
    },
    session,
)
assert result and "result" in result and not result["result"].get("isError"), result  # type: ignore[union-attr]
print("Streamable HTTP smoke test passed")
