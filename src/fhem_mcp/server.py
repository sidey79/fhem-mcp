from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Literal

from .models import FhemAttribute, FhemDevice
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

    def find_references(self, reference: str, relative_path: str | None = None) -> list[dict[str, object]]:
        if not reference.strip():
            raise ValueError("reference must not be empty")

        files: list[Path]
        if relative_path is None:
            files, _ = self._safe_resolve_cfg_files()
        else:
            file_path = self._resolve_in_root(relative_path)
            self._ensure_cfg_file(file_path)
            files = self._collect_cfg_files_recursive(file_path)

        word_re = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(reference) + r"(?![A-Za-z0-9_])")
        results: list[dict[str, object]] = []

        for path in files:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, RuntimeError):
                continue

            for idx, line in enumerate(lines, start=1):
                stripped = line.strip()
                if not stripped:
                    continue

                score = 0.0
                evidence: list[str] = []

                if word_re.search(line):
                    score += 0.6
                    evidence.append("word_match")
                elif reference in line:
                    score += 0.3
                    evidence.append("substring_match")
                else:
                    continue

                if stripped.startswith("define "):
                    parts = stripped.split()
                    if len(parts) >= 2 and parts[1] == reference:
                        score += 0.35
                        evidence.append("define_target")
                    else:
                        score += 0.1
                        evidence.append("define_context")
                elif stripped.startswith("attr "):
                    parts = stripped.split()
                    if len(parts) >= 2 and parts[1] == reference:
                        score += 0.35
                        evidence.append("attr_target")
                    else:
                        score += 0.1
                        evidence.append("attr_context")
                elif stripped.startswith("include "):
                    score += 0.05
                    evidence.append("include_context")
                else:
                    score += 0.05
                    evidence.append("free_text_context")

                lowered = stripped.lower()
                if any(k in lowered for k in ("notify", "doif", "at ", "perl", "reading")):
                    score += 0.1
                    evidence.append("rule_context")

                if stripped.startswith("#"):
                    score -= 0.25
                    evidence.append("comment_penalty")

                score = max(0.0, min(1.0, round(score, 3)))
                if score < 0.3:
                    confidence = "low"
                elif score < 0.7:
                    confidence = "medium"
                else:
                    confidence = "high"

                results.append(
                    {
                        "file": str(path.relative_to(self.config_root)),
                        "line": idx,
                        "text": line,
                        "score": score,
                        "confidence": confidence,
                        "evidence": evidence,
                    }
                )

        results.sort(key=lambda item: (-float(item["score"]), str(item["file"]), int(item["line"])))
        return results
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
            parsed = self.parser.parse_file(path)
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
