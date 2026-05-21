from __future__ import annotations

from pathlib import Path

from .models import FhemDevice
from .parser import FhemConfigParser


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

    def _collect_devices_recursive(self, entry_file: Path) -> dict[str, FhemDevice]:
        devices: dict[str, FhemDevice] = {}
        visited: set[Path] = set()

        def visit(path: Path) -> None:
            resolved = self._resolve_abs_in_root(path)
            if resolved in visited:
                return
            visited.add(resolved)

            parsed = self.parser.parse_file(resolved)

            events: list[tuple[int, str, object]] = []
            events.extend((dev.source.line_number, "define", dev) for dev in parsed.device_definitions)
            events.extend((inc.source.line_number, "include", inc) for inc in parsed.includes)
            events.sort(key=lambda item: item[0])

            parent_dir = resolved.parent
            for _, event_type, payload in events:
                if event_type == "define":
                    dev = payload
                    devices[dev.name] = dev
                    continue

                include = payload
                try:
                    include_path = self._resolve_abs_in_root(parent_dir / include.path_token)
                    visit(include_path)
                except (ValueError, OSError):
                    continue

        visit(entry_file)
        return devices

    def list_config_files(self) -> list[str]:
        files = sorted(self.config_root.glob("**/*.cfg"))
        return [str(path.relative_to(self.config_root)) for path in files]

    def read_config_file(self, relative_path: str) -> str:
        file_path = self._resolve_in_root(relative_path)
        return file_path.read_text(encoding="utf-8")

    def list_devices(self, relative_path: str) -> list[dict[str, str]]:
        file_path = self._resolve_in_root(relative_path)
        devices = self._collect_devices_recursive(file_path)
        return [
            {
                "name": dev.name,
                "device_type": dev.device_type,
                "source_file": str(dev.source.file_path),
                "source_line": str(dev.source.line_number),
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
