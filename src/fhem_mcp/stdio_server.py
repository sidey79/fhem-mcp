from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

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
        return [
            {"name": "list_config_files", "description": "List all .cfg files under config root", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
            {"name": "read_config_file", "description": "Read one config file", "inputSchema": {"type": "object", "properties": {"relative_path": {"type": "string"}}, "required": ["relative_path"], "additionalProperties": False}},
            {"name": "list_devices", "description": "List parsed devices from one config file", "inputSchema": {"type": "object", "properties": {"relative_path": {"type": "string"}}, "required": ["relative_path"], "additionalProperties": False}},
            {"name": "get_device", "description": "Get one parsed device from one config file", "inputSchema": {"type": "object", "properties": {"relative_path": {"type": "string"}, "device_name": {"type": "string"}}, "required": ["relative_path", "device_name"], "additionalProperties": False}},
            {"name": "list_groups", "description": "List group attribute values to devices", "inputSchema": {"type": "object", "properties": {"relative_path": {"type": "string"}, "group_name": {"type": "string"}}, "additionalProperties": False}},
            {"name": "list_rooms", "description": "List room attribute values to devices", "inputSchema": {"type": "object", "properties": {"relative_path": {"type": "string"}}, "additionalProperties": False}},
            {"name": "list_attributes", "description": "List attributes for one or all devices", "inputSchema": {"type": "object", "properties": {"relative_path": {"type": "string"}, "device_name": {"type": "string"}}, "required": ["relative_path"], "additionalProperties": False}},
            {"name": "find_devices_by_attr", "description": "Find devices by attribute/value", "inputSchema": {"type": "object", "properties": {"relative_path": {"type": "string"}, "attribute": {"type": "string"}, "value": {"type": "string"}}, "required": ["relative_path", "attribute"], "additionalProperties": False}},
            {"name": "find_devices_by_type", "description": "Find devices by device type", "inputSchema": {"type": "object", "properties": {"relative_path": {"type": "string"}, "device_type": {"type": "string"}}, "required": ["relative_path", "device_type"], "additionalProperties": False}},
            {"name": "list_includes", "description": "List include directives and resolved targets", "inputSchema": {"type": "object", "properties": {"relative_path": {"type": "string"}}, "required": ["relative_path"], "additionalProperties": False}},
            {"name": "list_config_summary", "description": "Short summary over config(s)", "inputSchema": {"type": "object", "properties": {"relative_path": {"type": "string"}}, "additionalProperties": False}},
            {"name": "search_config", "description": "Search a text pattern in config files", "inputSchema": {"type": "object", "properties": {"pattern": {"type": "string"}, "relative_path": {"type": "string"}}, "required": ["pattern"], "additionalProperties": False}},
            {"name": "find_references", "description": "Find likely references with heuristic scoring", "inputSchema": {"type": "object", "properties": {"reference": {"type": "string", "minLength": 1}, "relative_path": {"type": "string"}}, "required": ["reference"], "additionalProperties": False}},
            {"name": "validate_config", "description": "Basic config validation", "inputSchema": {"type": "object", "properties": {"relative_path": {"type": "string"}}, "additionalProperties": False}},
            {"name": "get_device_full", "description": "Find one device repo-wide", "inputSchema": {"type": "object", "properties": {"device_name": {"type": "string"}}, "required": ["device_name"], "additionalProperties": False}},
        ]

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
                valid_tools = {tool["name"] for tool in self._tools()}
                if params.get("name") not in valid_tools:
                    return self._error(req_id, -32602, "Invalid params")
                try:
                    return {"jsonrpc": "2.0", "id": req_id, "result": self._call_tool(params)}
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

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        tool_name = params["name"]
        arguments = params.get("arguments", {})

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
        elif tool_name == "find_references":
            payload = self.backend.find_references(arguments["reference"], arguments.get("relative_path"))
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
