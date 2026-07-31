from __future__ import annotations

from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field


ScalarValue: TypeAlias = str | int | float | bool | None


class OutputModel(BaseModel):
    """Strict base class for serialized MCP tool output."""

    model_config = ConfigDict(extra="forbid")


class ResponseMetaDto(OutputModel):
    format: str
    complete: bool
    omitted: list[str] = Field(default_factory=list)
    request_more: dict[str, ScalarValue] | None = None


class SourceRefDto(OutputModel):
    file: str
    line: int


class TableDto(OutputModel):
    meta: ResponseMetaDto
    columns: list[str]
    rows: list[list[ScalarValue]]
    count: int = Field(ge=0)
    truncated: bool = False
    next_cursor: str | None = None


class CompactDeviceDto(OutputModel):
    meta: ResponseMetaDto
    name: str
    type: str
    definition: list[str] | None = None
    source: SourceRefDto | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    attribute_sources: dict[str, SourceRefDto] | None = None


class RawLogPageDto(OutputModel):
    meta: ResponseMetaDto
    text: str
    matched: int = Field(ge=0)
    returned_matches: int = Field(ge=0)
    returned_lines: int = Field(ge=0)
    truncated: bool = False
    next_cursor: str | None = None


class CompactReadingDto(OutputModel):
    value: str | None = None
    time: str | None = None


class CompactRuntimeDeviceDto(OutputModel):
    name: str
    type: str | None = None
    state: str | None = None
    attributes: dict[str, str | None] = Field(default_factory=dict)
    readings: dict[str, CompactReadingDto] = Field(default_factory=dict)
    internals: dict[str, str | None] | None = None
    possible_sets: str | None = None
    possible_attributes: str | None = None
