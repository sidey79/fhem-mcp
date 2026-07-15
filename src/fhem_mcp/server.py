from __future__ import annotations

from base64 import b64encode
from html import unescape
import json
from socket import timeout as SocketTimeout
from ssl import SSLContext, create_default_context
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import monotonic
from urllib.parse import ParseResult, quote_plus, urlparse
import re
from urllib.request import Request, urlopen
from typing import Literal

from .models import FhemAttribute, FhemDevice, FhemEvent
from .parser import FhemConfigParser, IncludeDirective


@dataclass(frozen=True)
class ParseEvent:
    line_number: int
    sequence: int
    event_type: Literal["define", "attr", "include"]
    device: FhemDevice | None = None
    include: IncludeDirective | None = None
    attribute: FhemAttribute | None = None


class FhemMcpServer:
    """Read-only Phase 1 MCP tool surface for source-view operations."""

    def __init__(self, config_root: Path) -> None:
        self.config_root = config_root.resolve()
        self.parser = FhemConfigParser()

    def _resolve_in_root(self, relative_path: str) -> Path:
        target = (self.config_root / relative_path).resolve()
        try:
            target.relative_to(self.config_root)
        except ValueError as exc:
            raise ValueError("Path escapes config root") from exc
        return target

    def _resolve_abs_in_root(self, path: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.config_root)
        except ValueError as exc:
            raise ValueError("Path escapes config root") from exc
        return resolved

    @staticmethod
    def _ensure_cfg_file(path: Path) -> None:
        if path.suffix.lower() != ".cfg":
            raise ValueError("Only .cfg files are allowed")

    def _build_parse_events(self, resolved_file: Path) -> list[ParseEvent]:
        parsed = self.parser.parse_file(resolved_file)
        events: list[ParseEvent] = []

        sequence = 0
        for dev in parsed.device_definitions:
            events.append(
                ParseEvent(
                    line_number=dev.source.line_number,
                    sequence=sequence,
                    event_type="define",
                    device=dev,
                )
            )
            sequence += 1

        for attr in parsed.attribute_definitions:
            events.append(
                ParseEvent(
                    line_number=attr.source.line_number,
                    sequence=sequence,
                    event_type="attr",
                    attribute=attr,
                )
            )
            sequence += 1

        for inc in parsed.includes:
            events.append(
                ParseEvent(
                    line_number=inc.source.line_number,
                    sequence=sequence,
                    event_type="include",
                    include=inc,
                )
            )
            sequence += 1

        events.sort(key=lambda event: (event.line_number, event.sequence))
        return events

    def _collect_devices_recursive(self, entry_file: Path) -> dict[str, FhemDevice]:
        devices: dict[str, FhemDevice] = {}
        active_stack: set[Path] = set()

        def visit(path: Path) -> None:
            resolved = self._resolve_abs_in_root(path)
            if resolved in active_stack:
                return
            active_stack.add(resolved)
            try:
                parent_dir = resolved.parent
                for event in self._build_parse_events(resolved):
                    if event.event_type == "define":
                        if event.device is not None:
                            devices[event.device.name] = FhemDevice(
                                name=event.device.name,
                                device_type=event.device.device_type,
                                definition_tokens=list(event.device.definition_tokens),
                                source=event.device.source,
                            )
                        continue

                    if event.event_type == "attr":
                        if event.attribute is None:
                            continue
                        target = devices.get(event.attribute.device_name)
                        if target is not None:
                            target.attributes.append(event.attribute)
                        continue

                    if event.include is None:
                        continue
                    try:
                        include_path = self._resolve_abs_in_root(parent_dir / event.include.path_token)
                        visit(include_path)
                    except (ValueError, OSError, RuntimeError):
                        # best-effort parsing: unresolved/invalid includes are ignored
                        continue
            finally:
                active_stack.remove(resolved)

        visit(entry_file)
        return devices

    def _collect_parse_events_recursive(self, entry_file: Path) -> list[ParseEvent]:
        events: list[ParseEvent] = []
        active_stack: set[Path] = set()

        def visit(path: Path) -> None:
            resolved = self._resolve_abs_in_root(path)
            if resolved in active_stack:
                return
            active_stack.add(resolved)
            try:
                parent_dir = resolved.parent
                local_events = self._build_parse_events(resolved)
                for event in local_events:
                    events.append(event)
                    if event.event_type != "include" or event.include is None:
                        continue
                    try:
                        include_path = self._resolve_abs_in_root(parent_dir / event.include.path_token)
                        visit(include_path)
                    except (ValueError, OSError, RuntimeError):
                        continue
            finally:
                active_stack.remove(resolved)

        visit(entry_file)
        return events

    def _collect_cfg_files_recursive(self, entry_file: Path) -> list[Path]:
        files: list[Path] = []
        seen: set[Path] = set()
        active_stack: set[Path] = set()

        def visit(path: Path) -> None:
            try:
                resolved = self._resolve_abs_in_root(path)
            except (ValueError, OSError, RuntimeError):
                return
            if resolved in active_stack or resolved in seen:
                return
            if not resolved.exists():
                return
            active_stack.add(resolved)
            seen.add(resolved)
            files.append(resolved)
            try:
                parsed = self.parser.parse_file(resolved)
                parent_dir = resolved.parent
                for inc in parsed.includes:
                    try:
                        include_path = self._resolve_abs_in_root(parent_dir / inc.path_token)
                    except (ValueError, OSError, RuntimeError):
                        continue
                    visit(include_path)
            except (OSError, RuntimeError):
                pass
            finally:
                active_stack.remove(resolved)

        visit(entry_file)
        return files

    def _devices_from_optional_path(self, relative_path: str | None) -> dict[str, FhemDevice]:
        if relative_path is not None:
            file_path = self._resolve_in_root(relative_path)
            self._ensure_cfg_file(file_path)
            return self._collect_devices_recursive(file_path)

        devices: dict[str, FhemDevice] = {}
        files, _ = self._safe_resolve_cfg_files()
        for file_path in files:
            try:
                parsed_devices = self._collect_devices_recursive(file_path)
            except (ValueError, OSError, RuntimeError):
                continue
            for name, dev in parsed_devices.items():
                devices[name] = dev
        return devices

    def list_config_files(self) -> list[str]:
        files = sorted(self.config_root.glob("**/*.cfg"))
        return [str(path.relative_to(self.config_root)) for path in files]

    def _safe_resolve_cfg_files(self) -> tuple[list[Path], list[dict[str, object]]]:
        resolved_files: list[Path] = []
        errors: list[dict[str, object]] = []
        for rel in self.list_config_files():
            try:
                path = self._resolve_in_root(rel)
                if not path.exists() or not path.is_file():
                    raise OSError("File is not readable")
                resolved_files.append(path)
            except (ValueError, OSError, RuntimeError) as exc:
                errors.append(
                    {
                        "type": "unreadable_config_file",
                        "file": rel,
                        "message": str(exc),
                    }
                )
        return resolved_files, errors

    def read_config_file(self, relative_path: str) -> str:
        file_path = self._resolve_in_root(relative_path)
        self._ensure_cfg_file(file_path)
        return file_path.read_text(encoding="utf-8")

    @staticmethod
    def _validate_live_base_url(base_url: str) -> ParseResult:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("base_url must use http or https")
        if not parsed.netloc:
            raise ValueError("base_url must include host")
        if parsed.query:
            raise ValueError("base_url must not include query parameters")
        if parsed.fragment:
            raise ValueError("base_url must not include fragment")
        return parsed

    @staticmethod
    def _validate_live_edit_token(path_value: str, field_name: str) -> str:
        candidate = path_value.strip()
        if not candidate:
            raise ValueError(f"{field_name} must not be empty")
        banned = {"\n", "\r", "\t", ";", "|", "&", "`", "$", ">", "<"}
        if any(ch in candidate for ch in banned):
            raise ValueError(f"{field_name} contains unsupported characters")
        return candidate

    @staticmethod
    def _build_tls_context(ca_file: str | None, ca_path: str | None) -> SSLContext | None:
        if ca_file is not None and not ca_file.strip():
            raise ValueError("ca_file must not be empty")
        if ca_path is not None and not ca_path.strip():
            raise ValueError("ca_path must not be empty")
        if ca_file is None and ca_path is None:
            return None
        return create_default_context(cafile=ca_file, capath=ca_path)

    def _fetch_fwcsrf_http(
        self,
        base_url: str,
        timeout_seconds: float,
        username: str | None,
        password: str | None,
        ssl_context: SSLContext | None,
    ) -> str:
        separator = "&" if "?" in base_url else "?"
        token_url = f"{base_url}{separator}XHR=1"
        request = Request(token_url, method="GET")
        if username is not None and password is not None:
            auth = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
            request.add_header("Authorization", f"Basic {auth}")

        if ssl_context is None:
            response_ctx = urlopen(request, timeout=timeout_seconds)
        else:
            response_ctx = urlopen(request, timeout=timeout_seconds, context=ssl_context)
        with response_ctx as response:
            token = response.headers.get("X-FHEM-csrfToken")

        if token is None or not token.strip():
            return ""
        return token.strip()

    @staticmethod
    def _build_live_request(base_url: str, query_parts: list[str]) -> str:
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}{'&'.join(query_parts)}"

    @staticmethod
    def _request_with_optional_auth(request: Request, username: str | None, password: str | None) -> None:
        if username is not None and password is not None:
            auth = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
            request.add_header("Authorization", f"Basic {auth}")

    def _http_get_text(
        self,
        request_url: str,
        timeout_seconds: float,
        username: str | None,
        password: str | None,
        ssl_context: SSLContext | None,
    ) -> str:
        request = Request(request_url, method="GET")
        self._request_with_optional_auth(request, username, password)
        if ssl_context is None:
            response_ctx = urlopen(request, timeout=timeout_seconds)
        else:
            response_ctx = urlopen(request, timeout=timeout_seconds, context=ssl_context)
        with response_ctx as response:
            payload = response.read()
        return payload.decode("utf-8", errors="replace")

    @staticmethod
    def _parse_jsonlist2_response(
        decoded: str, context: str, *, strict_results: bool = False
    ) -> list[object]:
        try:
            payload = json.loads(decoded)
        except json.JSONDecodeError:
            match = re.search(r"(\{.*\})", decoded, flags=re.DOTALL)
            if match is None:
                raise ValueError(f"Unable to parse jsonlist2 {context} response as JSON")
            try:
                payload = json.loads(match.group(1))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Unable to parse jsonlist2 {context} response as JSON") from exc

        results = payload.get("Results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise ValueError(f"Unexpected jsonlist2 {context} response format")
        if strict_results and any(not isinstance(item, dict) for item in results):
            raise ValueError(f"Unexpected jsonlist2 {context} result format")
        return results

    @staticmethod
    def _validate_live_device_name(device_name: str) -> str:
        candidate = device_name.strip()
        if not candidate:
            raise ValueError("device_name must not be empty")
        if re.fullmatch(r"[A-Za-z0-9_.-]+", candidate) is None:
            raise ValueError("device_name must be a literal FHEM device name")
        return candidate


    @staticmethod
    def _validate_observe_limit(name: str, value: int, minimum: int, maximum: int) -> None:
        if value < minimum or value > maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")

    @staticmethod
    def _compile_optional_regex(pattern: str | None, field_name: str) -> re.Pattern[str] | None:
        if pattern is None:
            return None
        try:
            return re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"invalid {field_name}: {exc}") from exc

    @staticmethod
    def _parse_event_payload(raw_line: str) -> FhemEvent:
        line = raw_line.strip()
        if not line:
            return FhemEvent(raw=raw_line, device=None, event="")

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            payload = None

        if isinstance(payload, list) and len(payload) >= 3:
            device_type = str(payload[0]) if payload[0] is not None else None
            device = str(payload[1]) if payload[1] is not None else None
            event = str(payload[2]) if payload[2] is not None else ""
            reading, value = FhemMcpServer._split_event_reading(event)
            return FhemEvent(raw=raw_line, device=device, event=event, device_type=device_type, reading=reading, value=value)

        if isinstance(payload, dict):
            device = FhemMcpServer._first_string_value(payload, ("device", "name", "NAME", "Device", "DEVICE"))
            event = FhemMcpServer._first_string_value(payload, ("event", "EVENT", "state", "STATE", "reading")) or line
            device_type = FhemMcpServer._first_string_value(payload, ("type", "TYPE", "device_type"))
            reading, value = FhemMcpServer._split_event_reading(event)
            return FhemEvent(raw=raw_line, device=device, event=event, device_type=device_type, reading=reading, value=value)

        parts = line.split(maxsplit=3)
        if len(parts) >= 4 and FhemMcpServer._looks_like_event_date(parts[0], parts[1]):
            device_type = parts[2]
            rest = parts[3].split(maxsplit=1)
            device = rest[0] if rest else None
            event = rest[1] if len(rest) > 1 else ""
            reading, value = FhemMcpServer._split_event_reading(event)
            return FhemEvent(raw=raw_line, device=device, event=event, device_type=device_type, reading=reading, value=value)

        if len(parts) >= 3:
            device_type = parts[0]
            device = parts[1]
            event = parts[2] if len(parts) == 3 else parts[2] + " " + parts[3]
            reading, value = FhemMcpServer._split_event_reading(event)
            return FhemEvent(raw=raw_line, device=device, event=event, device_type=device_type, reading=reading, value=value)

        return FhemEvent(raw=raw_line, device=None, event=line)

    @staticmethod
    def _first_string_value(payload: dict[object, object], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str):
                return value
        return None

    @staticmethod
    def _split_event_reading(event: str) -> tuple[str | None, str | None]:
        reading, sep, value = event.partition(": ")
        if not sep or not reading:
            return None, None
        return reading, value

    @staticmethod
    def _looks_like_event_date(date_part: str, time_part: str) -> bool:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M:%S.%f"):
            try:
                datetime.strptime(f"{date_part} {time_part}", fmt)
                return True
            except ValueError:
                continue
        return False

    @staticmethod
    def _set_response_read_timeout(response: object, timeout_seconds: float) -> None:
        fp = getattr(response, "fp", None)
        raw = getattr(fp, "raw", None)
        sock = getattr(raw, "_sock", None)
        if sock is not None and hasattr(sock, "settimeout"):
            sock.settimeout(timeout_seconds)

    @staticmethod
    def _serialize_event(event: FhemEvent) -> dict[str, str | None]:
        return {
            "device": event.device,
            "device_type": event.device_type,
            "reading": event.reading,
            "value": event.value,
            "event": event.event,
            "raw": event.raw,
        }

    @staticmethod
    def _build_raw_event_monitor_filter(event_monitor_filter: str) -> str:
        candidate = event_monitor_filter.strip()
        match = re.fullmatch(r"TYPE=([^\s]+)", candidate)
        if match is not None:
            return rf"^\S+\s+\S+\s+{re.escape(match.group(1))}\s+"
        return candidate

    @staticmethod
    def _summarize_events(events: list[FhemEvent]) -> dict[str, dict[str, int]]:
        devices: dict[str, int] = {}
        readings: dict[str, int] = {}
        event_types: dict[str, int] = {}

        for event in events:
            if event.device:
                devices[event.device] = devices.get(event.device, 0) + 1
            if event.reading:
                readings[event.reading] = readings.get(event.reading, 0) + 1
                event_types[event.reading] = event_types.get(event.reading, 0) + 1
            else:
                event_key = event.event.split(maxsplit=1)[0] if event.event else ""
                if event_key:
                    event_types[event_key] = event_types.get(event_key, 0) + 1

        return {
            "devices": dict(sorted(devices.items())),
            "readings": dict(sorted(readings.items())),
            "event_types": dict(sorted(event_types.items())),
        }

    def observe_live_events_http(
        self,
        base_url: str,
        duration_seconds: int = 10,
        event_monitor_filter: str = ".*",
        device_regex: str | None = None,
        event_regex: str | None = None,
        max_events: int = 500,
        fwcsrf: str | None = None,
        timeout_seconds: float = 5.0,
        username: str | None = None,
        password: str | None = None,
        ca_file: str | None = None,
        ca_path: str | None = None,
    ) -> dict[str, object]:
        self._validate_live_base_url(base_url)
        self._validate_observe_limit("duration_seconds", duration_seconds, 1, 60)
        self._validate_observe_limit("max_events", max_events, 1, 5000)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if (username is None) != (password is None):
            raise ValueError("username and password must be provided together")
        if not event_monitor_filter.strip():
            raise ValueError("event_monitor_filter must not be empty")
        raw_event_monitor_filter = self._build_raw_event_monitor_filter(event_monitor_filter)

        device_pattern = self._compile_optional_regex(device_regex, "device_regex")
        event_pattern = self._compile_optional_regex(event_regex, "event_regex")
        ssl_context = self._build_tls_context(ca_file, ca_path)
        token = fwcsrf if fwcsrf is not None else self._fetch_fwcsrf_http(base_url, timeout_seconds, username, password, ssl_context)

        query_parts = [
            "XHR=1",
            f"inform={quote_plus(f'type=raw;filter={raw_event_monitor_filter};fmt=JSON')}",
        ]
        if token:
            query_parts.append(f"fwcsrf={quote_plus(token)}")
        request_url = self._build_live_request(base_url, query_parts)
        request = Request(request_url, method="GET")
        self._request_with_optional_auth(request, username, password)

        deadline = monotonic() + duration_seconds
        events: list[FhemEvent] = []
        truncated = False
        if ssl_context is None:
            response_ctx = urlopen(request, timeout=timeout_seconds)
        else:
            response_ctx = urlopen(request, timeout=timeout_seconds, context=ssl_context)

        with response_ctx as response:
            while True:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    break
                self._set_response_read_timeout(response, remaining)
                try:
                    raw = response.readline()
                except (TimeoutError, SocketTimeout):
                    if monotonic() >= deadline:
                        break
                    continue
                if raw in (b"", ""):
                    break
                if isinstance(raw, bytes):
                    line = raw.decode("utf-8", errors="replace").strip()
                else:
                    line = str(raw).strip()
                line = re.sub(r"<br\s*/?>$", "", line, flags=re.IGNORECASE)
                if not line:
                    continue

                event = self._parse_event_payload(line)
                if device_pattern is not None and not device_pattern.search(event.device or ""):
                    continue
                if event_pattern is not None and not event_pattern.search(event.event):
                    continue

                events.append(event)
                if len(events) >= max_events:
                    truncated = True
                    break

        elapsed = max(0.0, duration_seconds - max(0.0, deadline - monotonic()))
        return {
            "duration_seconds": duration_seconds,
            "observed_seconds": round(elapsed, 3),
            "event_count": len(events),
            "truncated": truncated,
            "events": [self._serialize_event(event) for event in events],
            "summary": self._summarize_events(events),
        }

    def read_live_config_http(
        self,
        base_url: str,
        config_path: str = "fhem.cfg",
        fwcsrf: str | None = None,
        timeout_seconds: float = 5.0,
        username: str | None = None,
        password: str | None = None,
        ca_file: str | None = None,
        ca_path: str | None = None,
        enforce_cfg_suffix: bool = True,
    ) -> str:
        self._validate_live_base_url(base_url)
        target_cfg = self._validate_live_edit_token(config_path, "config_path")
        if enforce_cfg_suffix and not target_cfg.endswith(".cfg"):
            raise ValueError("config_path must end with .cfg")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")

        if (username is None) != (password is None):
            raise ValueError("username and password must be provided together")

        ssl_context = self._build_tls_context(ca_file, ca_path)
        token = fwcsrf if fwcsrf is not None else self._fetch_fwcsrf_http(base_url, timeout_seconds, username, password, ssl_context)

        cmd = f"style edit {target_cfg}"
        query_parts = [f"cmd={quote_plus(cmd)}"]
        if token:
            query_parts.append(f"fwcsrf={quote_plus(token)}")
        request_url = self._build_live_request(base_url, query_parts)

        decoded = self._http_get_text(request_url, timeout_seconds, username, password, ssl_context)
        match = re.search(r"<textarea[^>]*>(.*?)</textarea>", decoded, flags=re.IGNORECASE | re.DOTALL)
        if match is not None:
            return unescape(match.group(1))
        return decoded

    @staticmethod
    def _parse_log_timestamp(line: str) -> datetime | None:
        if len(line) < 19:
            return None
        stamp = line[:19]
        try:
            return datetime.strptime(stamp, "%Y.%m.%d %H:%M:%S")
        except ValueError:
            return None

    @staticmethod
    def _filter_log_lines(
        content: str,
        contains: str | None,
        regex: str | None,
        since: str | None,
        until: str | None,
        max_lines: int | None,
        ignore_case: bool,
    ) -> str:
        lines = content.splitlines()
        out: list[str] = []

        since_dt = datetime.strptime(since, "%Y-%m-%d %H:%M:%S") if since else None
        until_dt = datetime.strptime(until, "%Y-%m-%d %H:%M:%S") if until else None

        regex_obj = None
        if regex:
            flags = re.IGNORECASE if ignore_case else 0
            try:
                regex_obj = re.compile(regex, flags=flags)
            except re.error as exc:
                raise ValueError(f"invalid regex: {exc}") from exc

        needle = contains.lower() if (contains and ignore_case) else contains

        for line in lines:
            ts = FhemMcpServer._parse_log_timestamp(line)
            if since_dt is not None and (ts is None or ts < since_dt):
                continue
            if until_dt is not None and (ts is None or ts > until_dt):
                continue

            if needle:
                hay = line.lower() if ignore_case else line
                if needle not in hay:
                    continue

            if regex_obj and not regex_obj.search(line):
                continue

            out.append(line)

        if max_lines is not None:
            if max_lines == 0:
                return ""
            if max_lines > 0:
                out = out[-max_lines:]

        return "\n".join(out)

    def list_live_logs_http(
        self,
        base_url: str,
        fwcsrf: str | None = None,
        timeout_seconds: float = 5.0,
        username: str | None = None,
        password: str | None = None,
        ca_file: str | None = None,
        ca_path: str | None = None,
    ) -> dict[str, object]:
        self._validate_live_base_url(base_url)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if (username is None) != (password is None):
            raise ValueError("username and password must be provided together")

        ssl_context = self._build_tls_context(ca_file, ca_path)
        token = fwcsrf if fwcsrf is not None else self._fetch_fwcsrf_http(base_url, timeout_seconds, username, password, ssl_context)

        query_parts = [f"cmd={quote_plus('jsonlist2 TYPE=FileLog')}", "XHR=1"]
        if token:
            query_parts.append(f"fwcsrf={quote_plus(token)}")
        request_url = self._build_live_request(base_url, query_parts)
        decoded = self._http_get_text(request_url, timeout_seconds, username, password, ssl_context)

        results = self._parse_jsonlist2_response(decoded, "FileLog")

        devices: list[dict[str, str | None]] = []
        log_patterns: list[str] = []
        current_logfiles: list[str] = []

        for item in results:
            if not isinstance(item, dict):
                continue
            name = item.get("Name")
            if not isinstance(name, str):
                continue

            definition = item.get("DEF")
            def_logfile: str | None = None
            if isinstance(definition, str):
                parts = definition.split()
                if parts:
                    def_logfile = parts[0]

            internals = item.get("Internals")
            current_logfile: str | None = None
            if isinstance(internals, dict):
                for key in ("currentlogfile", "CURRENTLOGFILE", "logfile", "LOGFILE"):
                    value = internals.get(key)
                    if isinstance(value, str) and value.strip():
                        current_logfile = value.strip()
                        break

            devices.append(
                {
                    "device": name,
                    "def_logfile": def_logfile,
                    "current_logfile": current_logfile,
                }
            )
            if def_logfile and def_logfile not in log_patterns:
                log_patterns.append(def_logfile)
            if current_logfile and current_logfile not in current_logfiles:
                current_logfiles.append(current_logfile)

        return {
            "devices": devices,
            "log_patterns": log_patterns,
            "current_logfiles": current_logfiles,
        }

    def get_live_device_http(
        self,
        base_url: str,
        device_name: str,
        fwcsrf: str | None = None,
        timeout_seconds: float = 5.0,
        username: str | None = None,
        password: str | None = None,
        ca_file: str | None = None,
        ca_path: str | None = None,
    ) -> dict[str, object] | None:
        self._validate_live_base_url(base_url)
        target_device = self._validate_live_device_name(device_name)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if (username is None) != (password is None):
            raise ValueError("username and password must be provided together")

        ssl_context = self._build_tls_context(ca_file, ca_path)
        token = fwcsrf if fwcsrf is not None else self._fetch_fwcsrf_http(
            base_url, timeout_seconds, username, password, ssl_context
        )
        query_parts = [f"cmd={quote_plus(f'jsonlist2 {target_device}')}", "XHR=1"]
        if token:
            query_parts.append(f"fwcsrf={quote_plus(token)}")
        request_url = self._build_live_request(base_url, query_parts)
        decoded = self._http_get_text(
            request_url, timeout_seconds, username, password, ssl_context
        )
        results = self._parse_jsonlist2_response(
            decoded, "device", strict_results=True
        )
        matches = [
            item
            for item in results
            if isinstance(item, dict) and item.get("Name") == target_device
        ]
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError("Unexpected duplicate device in jsonlist2 response")

        item = matches[0]
        internals = self._normalize_jsonlist2_values(item.get("Internals"), "Internals")
        attributes = self._normalize_jsonlist2_values(item.get("Attributes"), "Attributes")
        readings_raw = item.get("Readings", {})
        if not isinstance(readings_raw, dict):
            raise ValueError("Unexpected jsonlist2 device Readings format")

        readings: dict[str, dict[str, str | None]] = {}
        for name, reading in readings_raw.items():
            if not isinstance(name, str) or not isinstance(reading, dict):
                raise ValueError("Unexpected jsonlist2 device reading format")
            value = reading.get("Value")
            timestamp = reading.get("Time")
            if value is not None and not isinstance(value, str):
                raise ValueError("Unexpected jsonlist2 device reading value format")
            if timestamp is not None and not isinstance(timestamp, str):
                raise ValueError("Unexpected jsonlist2 device reading time format")
            readings[name] = {"value": value, "time": timestamp}

        possible_sets = item.get("PossibleSets")
        possible_attributes = item.get("PossibleAttrs")
        if possible_sets is not None and not isinstance(possible_sets, str):
            raise ValueError("Unexpected jsonlist2 device PossibleSets format")
        if possible_attributes is not None and not isinstance(possible_attributes, str):
            raise ValueError("Unexpected jsonlist2 device PossibleAttrs format")
        return {
            "name": target_device,
            "internals": internals,
            "attributes": attributes,
            "readings": readings,
            "possible_sets": possible_sets,
            "possible_attributes": possible_attributes,
        }

    @staticmethod
    def _normalize_jsonlist2_values(value: object, field_name: str) -> dict[str, str | None]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError(f"Unexpected jsonlist2 device {field_name} format")
        normalized: dict[str, str | None] = {}
        for key, item in value.items():
            if not isinstance(key, str) or (item is not None and not isinstance(item, str)):
                raise ValueError(f"Unexpected jsonlist2 device {field_name} value format")
            normalized[key] = item
        return normalized

    def read_live_log_http(
        self,
        base_url: str,
        log_path: str = "./log/fhem-%Y-%m-%d.log",
        fwcsrf: str | None = None,
        timeout_seconds: float = 5.0,
        username: str | None = None,
        password: str | None = None,
        ca_file: str | None = None,
        ca_path: str | None = None,
        contains: str | None = None,
        regex: str | None = None,
        since: str | None = None,
        until: str | None = None,
        max_lines: int | None = 500,
        ignore_case: bool = False,
    ) -> str:
        if not log_path.strip():
            raise ValueError("log_path must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if (username is None) != (password is None):
            raise ValueError("username and password must be provided together")
        if max_lines is not None and max_lines < 0:
            raise ValueError("max_lines must be >= 0")
        if since is not None:
            datetime.strptime(since, "%Y-%m-%d %H:%M:%S")
        if until is not None:
            datetime.strptime(until, "%Y-%m-%d %H:%M:%S")
        if regex:
            flags = re.IGNORECASE if ignore_case else 0
            try:
                re.compile(regex, flags=flags)
            except re.error as exc:
                raise ValueError(f"invalid regex: {exc}") from exc

        target_log = self._validate_live_edit_token(log_path, "log_path")

        raw = self.read_live_config_http(
            base_url=base_url,
            config_path=target_log,
            fwcsrf=fwcsrf,
            timeout_seconds=timeout_seconds,
            username=username,
            password=password,
            ca_file=ca_file,
            ca_path=ca_path,
            enforce_cfg_suffix=False,
        )
        return self._filter_log_lines(raw, contains, regex, since, until, max_lines, ignore_case)

    def list_devices(self, relative_path: str) -> list[dict[str, object]]:
        file_path = self._resolve_in_root(relative_path)
        self._ensure_cfg_file(file_path)
        devices = self._collect_devices_recursive(file_path)
        return [
            {
                "name": dev.name,
                "device_type": dev.device_type,
                "source_file": str(dev.source.file_path),
                "source_line": dev.source.line_number,
            }
            for dev in devices.values()
        ]

    def get_device(self, relative_path: str, device_name: str) -> dict | None:
        file_path = self._resolve_in_root(relative_path)
        self._ensure_cfg_file(file_path)
        devices = self._collect_devices_recursive(file_path)
        device = devices.get(device_name)
        if device is None:
            return None
        return self._serialize_device(device)

    def list_groups(self, relative_path: str | None = None, group_name: str | None = None) -> dict[str, list[str]]:
        return self._list_attr_values(relative_path=relative_path, attr_name="group", value_filter=group_name)

    def list_rooms(self, relative_path: str | None = None) -> dict[str, list[str]]:
        return self._list_attr_values(relative_path=relative_path, attr_name="room")

    def _list_attr_values(self, relative_path: str | None, attr_name: str, value_filter: str | None = None) -> dict[str, list[str]]:
        devices = self._devices_from_optional_path(relative_path)
        out: dict[str, list[str]] = {}
        for dev in devices.values():
            for attr in dev.attributes:
                if attr.name != attr_name:
                    continue
                tokens = [token.strip() for token in attr.value.split(",")]
                for token in tokens:
                    if not token:
                        continue
                    if value_filter is not None and token != value_filter:
                        continue
                    out.setdefault(token, [])
                    if dev.name not in out[token]:
                        out[token].append(dev.name)
        return dict(sorted(out.items()))

    def list_attributes(self, relative_path: str, device_name: str | None = None) -> dict[str, list[dict[str, object]]]:
        file_path = self._resolve_in_root(relative_path)
        self._ensure_cfg_file(file_path)
        devices = self._collect_devices_recursive(file_path)
        results: dict[str, list[dict[str, object]]] = {}
        for name, device in devices.items():
            if device_name is not None and name != device_name:
                continue
            results[name] = [
                {
                    "name": attr.name,
                    "value": attr.value,
                    "source_file": str(attr.source.file_path),
                    "source_line": attr.source.line_number,
                }
                for attr in device.attributes
            ]
        return results

    def find_devices_by_attr(self, relative_path: str, attribute: str, value: str | None = None) -> list[dict[str, object]]:
        file_path = self._resolve_in_root(relative_path)
        self._ensure_cfg_file(file_path)
        devices = self._collect_devices_recursive(file_path)
        found: list[dict[str, object]] = []
        for dev in devices.values():
            for attr in dev.attributes:
                if attr.name != attribute:
                    continue
                if value is not None and attr.value != value:
                    continue
                found.append(
                    {
                        "name": dev.name,
                        "device_type": dev.device_type,
                        "matching_attribute": attr.name,
                        "matching_value": attr.value,
                        "source_file": str(dev.source.file_path),
                        "source_line": dev.source.line_number,
                    }
                )
                break
        return found

    def find_devices_by_type(self, relative_path: str, device_type: str) -> list[dict[str, object]]:
        file_path = self._resolve_in_root(relative_path)
        self._ensure_cfg_file(file_path)
        devices = self._collect_devices_recursive(file_path)
        return [
            {
                "name": dev.name,
                "device_type": dev.device_type,
                "source_file": str(dev.source.file_path),
                "source_line": dev.source.line_number,
            }
            for dev in devices.values()
            if dev.device_type == device_type
        ]

    def list_includes(self, relative_path: str) -> list[dict[str, object]]:
        file_path = self._resolve_in_root(relative_path)
        self._ensure_cfg_file(file_path)
        events = self._collect_parse_events_recursive(file_path)
        includes: list[dict[str, object]] = []
        for event in events:
            if event.event_type != "include" or event.include is None:
                continue
            parent = event.include.source.file_path.parent
            exists = False
            rel_resolved: str | None = None
            try:
                resolved_path = self._resolve_abs_in_root(parent / event.include.path_token)
                exists = resolved_path.exists()
                if exists:
                    rel_resolved = str(resolved_path.relative_to(self.config_root))
            except (ValueError, OSError, RuntimeError):
                pass
            includes.append(
                {
                    "include_path": event.include.path_token,
                    "source_file": str(event.include.source.file_path),
                    "source_line": event.include.source.line_number,
                    "resolved_path": rel_resolved,
                    "exists": exists,
                }
            )
        return includes

    def list_config_summary(self, relative_path: str | None = None) -> dict[str, object]:
        devices = self._devices_from_optional_path(relative_path)
        type_counts: dict[str, int] = {}
        room_count = 0
        group_count = 0
        files: set[str] = set()
        line_min: int | None = None
        line_max: int | None = None

        for dev in devices.values():
            type_counts[dev.device_type] = type_counts.get(dev.device_type, 0) + 1
            files.add(str(dev.source.file_path))
            line_min = dev.source.line_number if line_min is None else min(line_min, dev.source.line_number)
            line_max = dev.source.line_number if line_max is None else max(line_max, dev.source.line_number)
            for attr in dev.attributes:
                if attr.name == "room":
                    room_count += len([token for token in attr.value.split(",") if token.strip()])
                if attr.name == "group":
                    group_count += len([token for token in attr.value.split(",") if token.strip()])
                files.add(str(attr.source.file_path))
                line_min = attr.source.line_number if line_min is None else min(line_min, attr.source.line_number)
                line_max = attr.source.line_number if line_max is None else max(line_max, attr.source.line_number)

        return {
            "device_count": len(devices),
            "type_counts": dict(sorted(type_counts.items())),
            "room_assignment_count": room_count,
            "group_assignment_count": group_count,
            "files": sorted(files),
            "line_range": {"start": line_min, "end": line_max},
        }

    def search_config(self, pattern: str, relative_path: str | None = None) -> list[dict[str, object]]:
        files: list[Path]
        if relative_path is None:
            files, _ = self._safe_resolve_cfg_files()
        else:
            file_path = self._resolve_in_root(relative_path)
            self._ensure_cfg_file(file_path)
            files = self._collect_cfg_files_recursive(file_path)

        matches: list[dict[str, object]] = []
        for path in files:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, RuntimeError):
                continue
            for idx, line in enumerate(text.splitlines(), start=1):
                if pattern in line:
                    matches.append(
                        {
                            "file": str(path.relative_to(self.config_root)),
                            "line": idx,
                            "text": line,
                        }
                    )
        return matches
    def validate_config(self, relative_path: str | None = None) -> dict[str, list[dict[str, object]]]:
        files: list[Path]
        errors: list[dict[str, object]] = []
        if relative_path is None:
            files, resolve_errors = self._safe_resolve_cfg_files()
            errors.extend(resolve_errors)
        else:
            file_path = self._resolve_in_root(relative_path)
            self._ensure_cfg_file(file_path)
            files = self._collect_cfg_files_recursive(file_path)

        seen_devices: dict[str, str] = {}
        for path in files:
            try:
                parsed = self.parser.parse_file(path)
            except (OSError, RuntimeError) as exc:
                errors.append(
                    {
                        "type": "unreadable_config_file",
                        "file": str(path),
                        "message": str(exc),
                    }
                )
                continue

            for dev in parsed.device_definitions:
                position = f"{dev.source.file_path}:{dev.source.line_number}"
                if dev.name in seen_devices:
                    errors.append(
                        {
                            "type": "duplicate_device",
                            "device": dev.name,
                            "first_seen": seen_devices[dev.name],
                            "duplicate": position,
                        }
                    )
                else:
                    seen_devices[dev.name] = position

            for inc in parsed.includes:
                include_file = inc.source.file_path.parent / inc.path_token
                try:
                    include_file = self._resolve_abs_in_root(include_file)
                    exists = include_file.exists()
                except (ValueError, RuntimeError):
                    exists = False
                if not exists:
                    errors.append(
                        {
                            "type": "missing_include",
                            "file": str(inc.source.file_path),
                            "line": inc.source.line_number,
                            "include_path": inc.path_token,
                        }
                    )

            text = path.read_text(encoding="utf-8")
            for idx, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or stripped.startswith("{"):
                    continue
                parts = stripped.split()
                if parts[0] == "define":
                    name_index = self.parser._skip_leading_flags(parts, 1)
                    if len(parts) < name_index + 2:
                        errors.append(
                            {
                                "type": "invalid_define",
                                "file": str(path),
                                "line": idx,
                                "raw_line": line,
                            }
                        )
                if parts[0] == "attr":
                    device_index = self.parser._skip_leading_flags(parts, 1)
                    if len(parts) < device_index + 2:
                        errors.append(
                            {
                                "type": "invalid_attr",
                                "file": str(path),
                                "line": idx,
                                "raw_line": line,
                            }
                        )

        return {"errors": errors}

    def get_device_full(self, device_name: str) -> dict[str, object] | None:
        files, _ = self._safe_resolve_cfg_files()
        best_device: FhemDevice | None = None
        merged_attrs: list[FhemAttribute] = []
        seen_attr_keys: set[tuple[str, str, str, int]] = set()

        for file_path in files:
            try:
                devices = self._collect_devices_recursive(file_path)
            except (ValueError, OSError, RuntimeError):
                continue
            device = devices.get(device_name)
            if device is None:
                continue

            if best_device is None or len(device.attributes) > len(best_device.attributes):
                best_device = FhemDevice(
                    name=device.name,
                    device_type=device.device_type,
                    definition_tokens=list(device.definition_tokens),
                    source=device.source,
                )

            for attr in device.attributes:
                key = (attr.name, attr.value, str(attr.source.file_path), attr.source.line_number)
                if key in seen_attr_keys:
                    continue
                seen_attr_keys.add(key)
                merged_attrs.append(attr)

        if best_device is None:
            return None

        best_device.attributes = merged_attrs
        return self._serialize_device(best_device)

    @staticmethod
    def _serialize_device(device: FhemDevice) -> dict:
        return {
            "name": device.name,
            "device_type": device.device_type,
            "definition_tokens": device.definition_tokens,
            "source": {
                "file_path": str(device.source.file_path),
                "line_number": device.source.line_number,
                "raw_line": device.source.raw_line,
            },
            "attributes": [
                {
                    "name": attr.name,
                    "value": attr.value,
                    "source": {
                        "file_path": str(attr.source.file_path),
                        "line_number": attr.source.line_number,
                        "raw_line": attr.source.raw_line,
                    },
                }
                for attr in device.attributes
            ],
        }
