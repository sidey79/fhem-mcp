from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SourceLocation:
    file_path: Path
    line_number: int
    raw_line: str


@dataclass(frozen=True)
class FhemAttribute:
    device_name: str
    name: str
    value: str
    source: SourceLocation


@dataclass
class FhemDevice:
    name: str
    device_type: str
    definition_tokens: list[str]
    source: SourceLocation
    attributes: list[FhemAttribute] = field(default_factory=list)


@dataclass(frozen=True)
class PatchProposal:
    target_file: Path
    description: str
    unified_diff: str
    reversible: bool = True
