from __future__ import annotations

import json
import os
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, TextIO

from .mcp_schema import TOOL_DEFINITIONS, build_tool_list
from .server import FhemMcpServer


@dataclass
class StdioMcpServer:
    config_root: Path
    enable_get: bool = False
    enable_set: bool = False
    SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
    DEFAULT_PROTOCOL_VERSION = "2024-11-05"

    def __post_init__(self) -> None:
        self.backend = FhemMcpServer(
            config_root=self.config_root,
            enable_get=self.enable_get,
            enable_set=self.enable_set,
        )

    def run(self, instream: BinaryIO | TextIO, outstream: BinaryIO | TextIO) -> None:
        while True:
            raw = self._read_message(instream)
            self._dbg(f"read raw: {raw[:200] if isinstance(raw, str) else raw}")
            if raw is None:
                return
            if not raw.strip():
                continue

            try:
                request = json.loads(raw)
            except json.JSONDecodeError:
                self._write_message(outstream, self._error(None, -32700, "Parse error"))
                continue

            if isinstance(request, list) and not request:
                self._write_message(outstream, self._error(None, -32600, "Invalid Request"))
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
            self._dbg(f"write payload: {json.dumps(payload, ensure_ascii=False)[:300]}")
            self._write_message(outstream, payload)



    @staticmethod
    def _dbg(message: str) -> None:
        if os.getenv("FHEM_MCP_DEBUG", "").lower() not in ("1", "true", "yes", "on"):
            return
        try:
            with open("/tmp/fhem-mcp-handshake.log", "a", encoding="utf-8") as fh:
                fh.write(f"{datetime.now().isoformat()} {message}\n")
        except Exception:
            pass

    @staticmethod
    def _write_message(outstream: BinaryIO | TextIO, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
        # Codex stdio uses newline-delimited JSON-RPC messages.
        text = json.dumps(payload, ensure_ascii=False) + "\n"
        try:
            outstream.write(text.encode("utf-8"))
        except TypeError:
            outstream.write(text)
        outstream.flush()

    @staticmethod
    def _read_message(instream: BinaryIO | TextIO) -> str | None:
        first = instream.readline()
        if first in (b"", ""):
            return None

        if isinstance(first, str):
            if first.lstrip()[:1] in ("{", "["):
                return first
            headers: dict[str, str] = {}
            line = first
            while True:
                if line in ("\r\n", "\n", ""):
                    break
                key, sep, value = line.partition(":")
                if sep:
                    headers[key.strip().lower()] = value.strip()
                line = instream.readline()
            length_raw = headers.get("content-length")
            if length_raw is None:
                return ""
            try:
                content_length = int(length_raw)
            except ValueError:
                return ""
            body = instream.read(content_length)
            if len(body) != content_length:
                return None
            return body

        if first.lstrip()[:1] in (b"{", b"["):
            return first.decode("utf-8", errors="replace")

        headers: dict[str, str] = {}
        line = first
        while True:
            if line in (b"\r\n", b"\n", b""):
                break
            key, sep, value = line.partition(b":")
            if sep:
                headers[key.decode("ascii", errors="ignore").strip().lower()] = value.decode(
                    "ascii", errors="ignore"
                ).strip()
            line = instream.readline()

        length_raw = headers.get("content-length")
        if length_raw is None:
            return ""
        try:
            content_length = int(length_raw)
        except ValueError:
            return ""

        body = instream.read(content_length)
        if len(body) != content_length:
            return None
        return body.decode("utf-8", errors="replace")

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
                if (
                    isinstance(requested_version, str)
                    and requested_version in self.SUPPORTED_PROTOCOL_VERSIONS
                ):
                    protocol_version = requested_version
                else:
                    protocol_version = self.SUPPORTED_PROTOCOL_VERSIONS[0]
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": protocol_version,
                        "serverInfo": {"name": "fhem-mcp", "title": "FHEM Config MCP", "version": "0.9.0"},
                        "instructions": "FHEM config server with read-only inspection and independently enabled active GET and SET access governed by FHEM authorization.",
                        "capabilities": {"tools": {}},
                    },
                }

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
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"isError": True, "content": [{"type": "text", "text": str(exc)}]},
                    }

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
            payload = self.backend.list_devices(
                arguments["relative_path"],
                arguments.get("format", "full"),
                arguments.get("include_source", True),
                arguments.get("limit"),
                arguments.get("cursor"),
            )
        elif tool_name == "read_live_config_http":
            payload = self.backend.read_live_config_http(
                arguments["base_url"],
                arguments.get("config_path", "fhem.cfg"),
                arguments.get("fwcsrf"),
                arguments.get("timeout_seconds", 5.0),
                arguments.get("username"),
                arguments.get("password"),
                arguments.get("ca_file"),
                arguments.get("ca_path"),
            )
        elif tool_name == "read_live_log_http":
            payload = self.backend.read_live_log_http(
                arguments["base_url"],
                arguments.get("log_path", "./log/fhem-%Y-%m-%d.log"),
                arguments.get("fwcsrf"),
                arguments.get("timeout_seconds", 5.0),
                arguments.get("username"),
                arguments.get("password"),
                arguments.get("ca_file"),
                arguments.get("ca_path"),
                arguments.get("contains"),
                arguments.get("regex"),
                arguments.get("since"),
                arguments.get("until"),
                arguments.get("max_lines", 500),
                arguments.get("ignore_case", False),
                arguments.get("response_format", "text"),
                arguments.get("cursor"),
                arguments.get("context_lines", 0),
            )
        elif tool_name == "list_live_logs_http":
            payload = self.backend.list_live_logs_http(
                arguments["base_url"],
                arguments.get("fwcsrf"),
                arguments.get("timeout_seconds", 5.0),
                arguments.get("username"),
                arguments.get("password"),
                arguments.get("ca_file"),
                arguments.get("ca_path"),
            )
        elif tool_name == "get_live_device_http":
            payload = self.backend.get_live_device_http(
                arguments["base_url"],
                arguments["device_name"],
                arguments.get("fwcsrf"),
                arguments.get("timeout_seconds", 5.0),
                arguments.get("username"),
                arguments.get("password"),
                arguments.get("ca_file"),
                arguments.get("ca_path"),
            )
        elif tool_name == "run_live_get_http":
            payload = self.backend.run_live_get_http(
                arguments["base_url"],
                arguments["device_name"],
                arguments["get_parameters"],
                arguments.get("fwcsrf"),
                arguments.get("timeout_seconds", 5.0),
                arguments.get("username"),
                arguments.get("password"),
                arguments.get("ca_file"),
                arguments.get("ca_path"),
            )
        elif tool_name == "run_live_set_http":
            payload = self.backend.run_live_set_http(
                arguments["base_url"],
                arguments["device_name"],
                arguments["set_parameters"],
                arguments.get("fwcsrf"),
                arguments.get("timeout_seconds", 5.0),
                arguments.get("username"),
                arguments.get("password"),
                arguments.get("ca_file"),
                arguments.get("ca_path"),
            )
        elif tool_name == "observe_live_events_http":
            payload = self.backend.observe_live_events_http(
                arguments["base_url"],
                arguments.get("duration_seconds", 10),
                arguments.get("event_monitor_filter", ".*"),
                arguments.get("device_regex"),
                arguments.get("event_regex"),
                arguments.get("max_events", 500),
                arguments.get("fwcsrf"),
                arguments.get("timeout_seconds", 5.0),
                arguments.get("username"),
                arguments.get("password"),
                arguments.get("ca_file"),
                arguments.get("ca_path"),
            )
        elif tool_name == "get_device":
            payload = self.backend.get_device(
                arguments["relative_path"],
                arguments["device_name"],
                arguments.get("format", "full"),
                arguments.get("include_source", False),
                arguments.get("include_raw", False),
            )
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
