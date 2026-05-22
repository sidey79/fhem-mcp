from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import FhemAttribute, FhemDevice, SourceLocation


@dataclass(frozen=True)
class IncludeDirective:
    path_token: str
    source: SourceLocation


@dataclass(frozen=True)
class CommentLine:
    text: str
    source: SourceLocation


@dataclass
class ParseResult:
    devices: dict[str, FhemDevice]
    device_definitions: list[FhemDevice]
    attribute_definitions: list[FhemAttribute]
    includes: list[IncludeDirective]
    comments: list[CommentLine]


class FhemConfigParser:
    """Best-effort parser for a subset of FHEM config syntax."""

    def parse_file(self, file_path: Path) -> ParseResult:
        devices: dict[str, FhemDevice] = {}
        device_definitions: list[FhemDevice] = []
        attribute_definitions: list[FhemAttribute] = []
        includes: list[IncludeDirective] = []
        comments: list[CommentLine] = []

        with file_path.open("r", encoding="utf-8") as handle:
            buffered_line = ""
            buffered_start_line: int | None = None

            for idx, raw in enumerate(handle, start=1):
                current = raw.rstrip("\n")

                if buffered_line:
                    buffered_line = f"{buffered_line} {current.lstrip()}"
                else:
                    buffered_line = current
                    buffered_start_line = idx

                if buffered_line.lstrip().startswith("#"):
                    self._parse_line(
                        file_path,
                        buffered_start_line if buffered_start_line is not None else idx,
                        buffered_line,
                        devices,
                        device_definitions,
                        attribute_definitions,
                        includes,
                        comments,
                    )
                    buffered_line = ""
                    buffered_start_line = None
                    continue

                if self._is_continuation(buffered_line):
                    buffered_line = self._strip_continuation_marker(buffered_line)
                    continue

                self._parse_line(
                    file_path,
                    buffered_start_line if buffered_start_line is not None else idx,
                    buffered_line,
                    devices,
                    device_definitions,
                    attribute_definitions,
                    includes,
                    comments,
                )
                buffered_line = ""
                buffered_start_line = None

            if buffered_line:
                self._parse_line(
                    file_path,
                    buffered_start_line if buffered_start_line is not None else 1,
                    buffered_line,
                    devices,
                    device_definitions,
                    attribute_definitions,
                    includes,
                    comments,
                )

        return ParseResult(
            devices=devices,
            device_definitions=device_definitions,
            attribute_definitions=attribute_definitions,
            includes=includes,
            comments=comments,
        )

    @staticmethod
    def _is_continuation(line: str) -> bool:
        stripped = line.rstrip()
        if not stripped.endswith("\\"):
            return False
        return len(stripped) < 2 or stripped[-2] != "\\"

    @staticmethod
    def _strip_continuation_marker(line: str) -> str:
        stripped_right = line.rstrip()
        return stripped_right[:-1].rstrip()

    def _parse_line(
        self,
        file_path: Path,
        line_number: int,
        raw_line: str,
        devices: dict[str, FhemDevice],
        device_definitions: list[FhemDevice],
        attribute_definitions: list[FhemAttribute],
        includes: list[IncludeDirective],
        comments: list[CommentLine],
    ) -> None:
        stripped = raw_line.strip()
        if not stripped:
            return
        if stripped.startswith("#"):
            comments.append(CommentLine(text=stripped[1:].lstrip(), source=SourceLocation(file_path=file_path, line_number=line_number, raw_line=raw_line)))
            return
        if stripped.startswith("{"):
            return

        parts = stripped.split()
        if not parts:
            return

        keyword = parts[0]
        source = SourceLocation(file_path=file_path, line_number=line_number, raw_line=raw_line)

        if keyword == "define":
            name_index = self._skip_leading_flags(parts, 1)
            if len(parts) < name_index + 2:
                return
            name = parts[name_index]
            device_type = parts[name_index + 1]
            defined_device = FhemDevice(
                name=name,
                device_type=device_type,
                definition_tokens=parts[name_index + 2 :],
                source=source,
            )
            devices[name] = defined_device
            device_definitions.append(defined_device)
            return

        if keyword == "attr":
            device_index = self._skip_leading_flags(parts, 1)
            if len(parts) < device_index + 2:
                return
            device_name = parts[device_index]
            attr_name = parts[device_index + 1]
            value = " ".join(parts[device_index + 2 :])
            attr = FhemAttribute(
                device_name=device_name,
                name=attr_name,
                value=value,
                source=source,
            )
            attribute_definitions.append(attr)
            device = devices.get(device_name)
            if device is not None:
                device.attributes.append(attr)
            return

        if keyword == "include" and len(parts) >= 2:
            includes.append(IncludeDirective(path_token=parts[1], source=source))

    @staticmethod
    def _skip_leading_flags(parts: list[str], start_index: int) -> int:
        index = start_index
        while index < len(parts) and parts[index].startswith("-"):
            index += 1
        return index
