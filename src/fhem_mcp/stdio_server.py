from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from .server import FhemMcpServer


@dataclass
class StdioMcpServer:
    config_root: Path

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
                continue

            requests = request if isinstance(request, list) else [request]
            responses: list[dict[str, Any]] = []

            for item in requests:
                if not isinstance(item, dict):
                    responses.append(self._error(None, -32600, "Invalid Request"))
                    continue
                if "id" not in item:
                    continue
                responses.append(self._handle_request(item))

            if not responses:
                continue

            payload = responses if isinstance(request, list) else responses[0]
            outstream.write(json.dumps(payload) + "\n")
            outstream.flush()

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
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "fhem-mcp", "version": "0.1.0"},
                        "capabilities": {"tools": {}},
                    },
                }

            if method == "tools/list":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [
                            {
                                "name": "list_config_files",
                                "description": "List all .cfg files under config root",
                                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                            },
                            {
                                "name": "read_config_file",
                                "description": "Read one config file",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"relative_path": {"type": "string"}},
                                    "required": ["relative_path"],
                                    "additionalProperties": False,
                                },
                            },
                            {
                                "name": "list_devices",
                                "description": "List parsed devices from one config file",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"relative_path": {"type": "string"}},
                                    "required": ["relative_path"],
                                    "additionalProperties": False,
                                },
                            },
                            {
                                "name": "get_device",
                                "description": "Get one parsed device from one config file",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "relative_path": {"type": "string"},
                                        "device_name": {"type": "string"},
                                    },
                                    "required": ["relative_path", "device_name"],
                                    "additionalProperties": False,
                                },
                            },
                        ]
                    },
                }

            if method == "tools/call":
                return {"jsonrpc": "2.0", "id": req_id, "result": self._call_tool(params)}

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
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(payload, ensure_ascii=False),
                }
            ]
        }

    @staticmethod
    def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": code,
                "message": message,
            },
        }
