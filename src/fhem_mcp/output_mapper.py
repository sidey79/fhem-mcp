from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .models import FhemDevice
from .output_models import (
    CompactDeviceDto,
    ResponseMetaDto,
    ScalarValue,
    SourceRefDto,
    TableDto,
)


def relative_source_file(file_path: Path, config_root: Path) -> str:
    """Return a stable config-root-relative path where possible."""

    try:
        return str(file_path.resolve().relative_to(config_root.resolve()))
    except ValueError:
        return str(file_path)


def source_ref(file_path: Path, line: int, config_root: Path) -> SourceRefDto:
    return SourceRefDto(file=relative_source_file(file_path, config_root), line=line)


def device_to_compact(
    device: FhemDevice,
    config_root: Path,
    *,
    include_source: bool = False,
    include_raw: bool = False,
) -> dict[str, object]:
    attribute_sources = None
    if include_source:
        attribute_sources = {
            attr.name: source_ref(attr.source.file_path, attr.source.line_number, config_root)
            for attr in device.attributes
        }

    omitted = ["raw_lines"]
    if not include_source:
        omitted.append("source")
    if not include_raw:
        omitted.append("definition")

    dto = CompactDeviceDto(
        meta=ResponseMetaDto(
            format="compact",
            complete=False,
            omitted=omitted,
            request_more={"format": "full"},
        ),
        name=device.name,
        type=device.device_type,
        definition=list(device.definition_tokens) if include_raw else None,
        source=(
            source_ref(device.source.file_path, device.source.line_number, config_root)
            if include_source
            else None
        ),
        attributes={attr.name: attr.value for attr in device.attributes},
        attribute_sources=attribute_sources,
    )
    return dto.model_dump(exclude_none=True)


def rows_to_table(
    rows: Iterable[Mapping[str, ScalarValue]],
    columns: Sequence[str],
    *,
    limit: int | None = None,
    cursor: str | None = None,
) -> dict[str, object]:
    if limit is not None and limit < 1:
        raise ValueError("limit must be >= 1")

    try:
        offset = 0 if cursor is None else int(cursor)
    except ValueError as exc:
        raise ValueError("cursor must be a non-negative integer") from exc
    if offset < 0:
        raise ValueError("cursor must be a non-negative integer")

    materialized = list(rows)
    end = len(materialized) if limit is None else min(len(materialized), offset + limit)
    selected = materialized[offset:end]
    truncated = end < len(materialized)
    omitted = []
    request_more: dict[str, ScalarValue] = {}
    if "file" not in columns and any("file" in row for row in materialized):
        omitted.append("source")
        request_more["include_source"] = True
    if truncated:
        omitted.append("remaining_rows")
        request_more["cursor"] = str(end)

    dto = TableDto(
        meta=ResponseMetaDto(
            format="table",
            complete=not omitted,
            omitted=omitted,
            request_more=request_more or None,
        ),
        columns=list(columns),
        rows=[[row.get(column) for column in columns] for row in selected],
        count=len(selected),
        truncated=truncated,
        next_cursor=str(end) if truncated else None,
    )
    return dto.model_dump(exclude_none=True)
