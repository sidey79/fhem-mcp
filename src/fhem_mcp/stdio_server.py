from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from .mcp_schema import TOOL_DEFINITIONS, build_tool_list
from .server import FhemMcpServer


@dataclass
class StdioMcpServer:
    config_root: Path
    SUPPORTED_PROTOCOL_VERSIONS = ("2024-11-05",)

    def __post_init__(self) -> None:
        self.backend = FhemMcpServer(config_root=self.config_root)

    def run(self, instream: TextIO, outstream: TextIO) -> None:
        for raw in instream:
            raw = raw.strip()
            if not raw:
                continue

            try:
                request = json.loads(raw)
            except json.JSONDecodeError:
                outstream.write(json.dumps(self._error(None, -32700, "Parse error")) + "\n")
                outstream.flush()
                continue

            if isinstance(request, list) and not request:
                outstream.write(json.dumps(self._error(None, -32600, "Invalid Request")) + "\n")
                outstream.flush()
                continue

            requests = request if isinstance(request, list) else [request]
            responses: list[dict[str, Any]] = []

            for item in requests:
                if not isinstance(item, dict):
                    responses.append(self._error(None, -32600, "Invalid Request"))
                    continue
                if not isinstance(item.get("method"), str):
                    responses.append(self._error(item.get("id"), -32600, "Invalid Request"))
                    continue
                if "id" not in item:
                    continue
                responses.append(self._handle_request(item))

            if not responses:
                continue

            payload = responses if isinstance(request, list) else responses[0]
            outstream.write(json.dumps(payload) + "\n")
            outstream.flush()

    def _tools(self) -> list[dict[str, Any]]:
        return build_tool_list()

    def _handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        req_id = request["id"]
        method = request.get("method")
        params = request.get("params", {})

        if not isinstance(method, str):
            return self._error(req_id, -32600, "Invalid Request")

        if not isinstance(params, dict):
            return self._error(req_id, -32602, "Invalid params")

        try:
            if method == "initialize":
                requested_version = params.get("protocolVersion")
                if requested_version in self.SUPPORTED_PROTOCOL_VERSIONS:
                    protocol_version = requested_version
                else:
                    protocol_version = self.SUPPORTED_PROTOCOL_VERSIONS[0]
                return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": protocol_version, "serverInfo": {"name": "fhem-mcp", "version": "0.1.0"}, "capabilities": {"tools": {}}}}

            if method == "tools/list":
                return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": self._tools()}}

            if method == "tools/call":
                if "arguments" in params and not isinstance(params["arguments"], dict):
                    return self._error(req_id, -32602, "Invalid params")
                tool_name = params.get("name")
                if tool_name not in TOOL_DEFINITIONS:
                    return self._error(req_id, -32602, "Invalid params")
                _, model = TOOL_DEFINITIONS[tool_name]
                try:
                    validated = model.model_validate(params.get("arguments", {})).model_dump(exclude_none=False)
                except Exception:
                    return self._error(req_id, -32602, "Invalid params")
                try:
                    return {"jsonrpc": "2.0", "id": req_id, "result": self._call_tool(tool_name, validated)}
                except (ValueError, OSError) as exc:
                    return {"jsonrpc": "2.0", "id": req_id, "result": {"isError": True, "content": [{"type": "text", "text": str(exc)}]}}

            return self._error(req_id, -32601, f"Method not found: {method}")
        except ValueError as exc:
            return self._error(req_id, -32001, str(exc))
        except KeyError as exc:
            return self._error(req_id, -32602, f"Missing parameter: {exc}")
        except OSError as exc:
            return self._error(req_id, -32002, str(exc))
        except Exception as exc:
            return self._error(req_id, -32000, f"Unhandled server error: {exc}")

    def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:

        if tool_name == "list_config_files":
            payload = self.backend.list_config_files()
        elif tool_name == "read_config_file":
            payload = self.backend.read_config_file(arguments["relative_path"])
        elif tool_name == "list_devices":
            payload = self.backend.list_devices(arguments["relative_path"])
        elif tool_name == "get_device":
            payload = self.backend.get_device(arguments["relative_path"], arguments["device_name"])
        elif tool_name == "list_groups":
            payload = self.backend.list_groups(arguments.get("relative_path"), arguments.get("group_name"))
        elif tool_name == "list_rooms":
            payload = self.backend.list_rooms(arguments.get("relative_path"))
        elif tool_name == "list_attributes":
            payload = self.backend.list_attributes(arguments["relative_path"], arguments.get("device_name"))
        elif tool_name == "find_devices_by_attr":
            payload = self.backend.find_devices_by_attr(arguments["relative_path"], arguments["attribute"], arguments.get("value"))
        elif tool_name == "find_devices_by_type":
            payload = self.backend.find_devices_by_type(arguments["relative_path"], arguments["device_type"])
        elif tool_name == "list_includes":
            payload = self.backend.list_includes(arguments["relative_path"])
        elif tool_name == "list_config_summary":
            payload = self.backend.list_config_summary(arguments.get("relative_path"))
        elif tool_name == "search_config":
            payload = self.backend.search_config(arguments["pattern"], arguments.get("relative_path"))
        elif tool_name == "validate_config":
            payload = self.backend.validate_config(arguments.get("relative_path"))
        elif tool_name == "get_device_full":
            payload = self.backend.get_device_full(arguments["device_name"])
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

        return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}

    @staticmethod
    def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
