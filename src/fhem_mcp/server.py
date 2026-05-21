from __future__ import annotations

from pathlib import Path

from .models import FhemDevice
from .parser import FhemConfigParser


class FhemMcpServer:
    """Read-only Phase 1 MCP tool surface for source-view operations."""

    def __init__(self, config_root: Path) -> None:
        self.config_root = config_root
        self.parser = FhemConfigParser()

    def list_config_files(self) -> list[str]:
        files = sorted(self.config_root.glob("**/*.cfg"))
        return [str(path.relative_to(self.config_root)) for path in files]

    def read_config_file(self, relative_path: str) -> str:
        file_path = (self.config_root / relative_path).resolve()
        if not str(file_path).startswith(str(self.config_root.resolve())):
            raise ValueError("Path escapes config root")
        return file_path.read_text(encoding="utf-8")

    def list_devices(self, relative_path: str) -> list[dict[str, str]]:
        result = self.parser.parse_file(self.config_root / relative_path)
        return [
            {
                "name": dev.name,
                "device_type": dev.device_type,
                "source_file": str(dev.source.file_path),
                "source_line": str(dev.source.line_number),
            }
            for dev in result.devices.values()
        ]

    def get_device(self, relative_path: str, device_name: str) -> dict | None:
        result = self.parser.parse_file(self.config_root / relative_path)
        device = result.devices.get(device_name)
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
