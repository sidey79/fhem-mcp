from __future__ import annotations

from dataclasses import dataclass
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
        visited: set[Path] = set()

        def visit(path: Path) -> None:
            resolved = self._resolve_abs_in_root(path)
            if resolved in visited:
                return
            visited.add(resolved)

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
                except (ValueError, OSError):
                    # best-effort parsing: unresolved/invalid includes are ignored
                    continue

        visit(entry_file)
        return devices

    def list_config_files(self) -> list[str]:
        files = sorted(self.config_root.glob("**/*.cfg"))
        return [str(path.relative_to(self.config_root)) for path in files]

    def read_config_file(self, relative_path: str) -> str:
        file_path = self._resolve_in_root(relative_path)
        if file_path.suffix.lower() != ".cfg":
            raise ValueError("Only .cfg files are allowed")
        return file_path.read_text(encoding="utf-8")

    def list_devices(self, relative_path: str) -> list[dict[str, object]]:
        file_path = self._resolve_in_root(relative_path)
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
        devices = self._collect_devices_recursive(file_path)
        device = devices.get(device_name)
        if device is None:
            return None
        return self._serialize_device(device)

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
