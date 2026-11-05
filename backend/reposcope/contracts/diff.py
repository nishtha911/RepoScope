"""Side-aware unified-diff and symbol-change records. No database IDs."""
from typing import Literal, Self
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def validate_path(value):
    if (not isinstance(value, str) or not value.strip() or value.startswith("/")
            or "\\" in value or "\0" in value or ":" in value.split("/")[0]
            or any(p in {"", ".", ".."} for p in value.split("/"))):
        raise ValueError("Expected a repository-relative POSIX path without traversal")
    return value


class LineRange(_Record):
    start: int = Field(ge=1, strict=True)
    end: int = Field(ge=1, strict=True)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end < self.start:
            raise ValueError("Reversed line range")
        return self


class DiffLine(_Record):
    kind: Literal[" ", "+", "-"]
    text: str
    base_line: int | None = Field(default=None, ge=1, strict=True)
    head_line: int | None = Field(default=None, ge=1, strict=True)
    no_newline: bool = False

    @model_validator(mode="after")
    def coordinates(self) -> Self:
        normalized = self.text.replace("\r\n", "\n")
        if "\n" in normalized[:-1]:
            raise ValueError("One diff row cannot contain multiple physical lines")
        if ((self.base_line is not None) != (self.kind != "+")
                or (self.head_line is not None) != (self.kind != "-")):
            raise ValueError("Diff line has invalid side coordinates")
        return self


class DiffHunk(_Record):
    base_start: int = Field(ge=0, strict=True)
    base_count: int = Field(ge=0, strict=True)
    head_start: int = Field(ge=0, strict=True)
    head_count: int = Field(ge=0, strict=True)
    lines: tuple[DiffLine, ...]

    @model_validator(mode="after")
    def counts(self) -> Self:
        if (self.base_count and not self.base_start) or (self.head_count and not self.head_start):
            raise ValueError("Nonempty hunk sides must start at line 1 or later")
        old, new = self.base_start, self.head_start
        for row in self.lines:
            if row.base_line is not None:
                if row.base_line != old:
                    raise ValueError("Nonconsecutive base coordinates")
                old += 1
            if row.head_line is not None:
                if row.head_line != new:
                    raise ValueError("Nonconsecutive head coordinates")
                new += 1
        if old - self.base_start != self.base_count or new - self.head_start != self.head_count:
            raise ValueError("Hunk line counts do not match its header")
        return self


def ranges(numbers):
    ordered = sorted(set(numbers))
    result = []
    for number in ordered:
        if result and number == result[-1].end + 1:
            result[-1] = LineRange(start=result[-1].start, end=number)
        else:
            result.append(LineRange(start=number, end=number))
    return tuple(result)


class FileDiff(_Record):
    base_path: str | None
    head_path: str | None
    status: Literal["ADDED", "REMOVED", "MODIFIED", "RENAMED", "COPIED"]
    binary: bool = False
    symlink: bool = False
    submodule: bool = False
    hunks: tuple[DiffHunk, ...] = ()

    @model_validator(mode="after")
    def inventory(self) -> Self:
        if self.base_path is None and self.head_path is None:
            raise ValueError("File diff has no path")
        for path in (self.base_path, self.head_path):
            if path is not None:
                validate_path(path)
        if self.status == "ADDED" and (self.base_path is not None or self.head_path is None):
            raise ValueError("Added file requires head path only")
        if self.status == "REMOVED" and (self.base_path is None or self.head_path is not None):
            raise ValueError("Removed file requires base path only")
        if self.status in {"MODIFIED", "RENAMED", "COPIED"} and (self.base_path is None or self.head_path is None):
            raise ValueError("Both paths are required")
        if self.status == "MODIFIED" and self.base_path != self.head_path:
            raise ValueError("Modified file paths must agree")
        old_end, new_end = 0, 0
        for hunk in self.hunks:
            old_pos = hunk.base_start - 1 if hunk.base_count else hunk.base_start
            new_pos = hunk.head_start - 1 if hunk.head_count else hunk.head_start
            if old_pos < old_end or new_pos < new_end:
                raise ValueError("Overlapping or out-of-order hunks")
            old_end, new_end = old_pos + hunk.base_count, new_pos + hunk.head_count
        return self

    @property
    def base_ranges(self):
        return ranges(row.base_line for h in self.hunks for row in h.lines if row.kind == "-")

    @property
    def head_ranges(self):
        return ranges(row.head_line for h in self.hunks for row in h.lines if row.kind == "+")


class DiffPatch(_Record):
    files: tuple[FileDiff, ...] = ()

    @model_validator(mode="after")
    def unique_files(self) -> Self:
        old, new = set(), set()
        for file in self.files:
            for path, seen in ((file.base_path if file.status != "COPIED" else None, old), (file.head_path, new)):
                if path is not None:
                    if path in seen:
                        raise ValueError("Duplicate file entry on one patch side")
                    seen.add(path)
        return self


class MappingGap(_Record):
    code: str
    path: str
    side: Literal["base", "head", "both"] = "both"
    detail: str
    lines: tuple[LineRange, ...] = ()


class LineSymbolMapping(_Record):
    path: str
    side: Literal["base", "head"]
    changed_range: LineRange
    symbol_keys: tuple[str, ...] = ()
    unmapped_lines: tuple[int, ...] = ()


class SymbolVersion(_Record):
    path: str
    local_key: str
    name: str
    qualname: str
    kind: Literal["class", "function", "method"]
    start_line: int = Field(ge=1, strict=True)
    end_line: int = Field(ge=1, strict=True)
    content_start_line: int = Field(ge=1, strict=True)
    content_end_line: int = Field(ge=1, strict=True)


class SymbolChange(_Record):
    classification: Literal["ADDED", "REMOVED", "SIGNATURE_CHANGED", "BODY_CHANGED"]
    base_symbol: SymbolVersion | None = None
    head_symbol: SymbolVersion | None = None
    base_changed_ranges: tuple[LineRange, ...] = ()
    head_changed_ranges: tuple[LineRange, ...] = ()

    @model_validator(mode="after")
    def sides(self) -> Self:
        if self.classification == "ADDED":
            valid = self.base_symbol is None and self.head_symbol is not None
        elif self.classification == "REMOVED":
            valid = self.base_symbol is not None and self.head_symbol is None
        else:
            valid = self.base_symbol is not None and self.head_symbol is not None
        if not valid:
            raise ValueError("Classification has invalid symbol sides")
        return self


class SymbolDiffReport(_Record):
    patch: DiffPatch
    changes: tuple[SymbolChange, ...] = ()
    line_mappings: tuple[LineSymbolMapping, ...] = ()
    gaps: tuple[MappingGap, ...] = ()
    base_revision: str | None = None
    head_revision: str | None = None
