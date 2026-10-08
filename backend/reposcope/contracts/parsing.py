"""Option A v1 extraction DTOs.

These models contain extraction metadata, not persistence IDs
or live Tree-sitter nodes.
"""

import hashlib
import json
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


DefinitionKind = Literal["class", "function", "method"]

ParameterKind = Literal[
    "positional_only",
    "positional_or_keyword",
    "var_positional",
    "keyword_only",
    "var_keyword",
]


def make_local_key(
    file_path: str,
    kind: DefinitionKind,
    qualname: str,
    definition_start_byte: int,
) -> str:
    """Return a reproducible, file-local identity."""
    return json.dumps(
        [file_path, kind, qualname, definition_start_byte],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("value must contain non-whitespace content")
    return value


class _ExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParsedParameter(_ExtractionModel):
    name: str = Field(min_length=1)
    kind: ParameterKind
    annotation: str | None
    default_text: str | None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _nonblank(value)


class ParsedSymbol(_ExtractionModel):
    local_key: str = Field(min_length=1)
    parent_key: str | None

    name: str = Field(min_length=1)
    qualname: str = Field(min_length=1)
    kind: DefinitionKind

    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    definition_start_byte: int = Field(ge=0)
    definition_end_byte: int = Field(ge=0)

    content_start_line: int = Field(ge=1)
    content_end_line: int = Field(ge=1)

    content_start_byte: int = Field(ge=0)
    content_end_byte: int = Field(ge=0)

    signature: str | None
    docstring: str | None
    parameters: list[ParsedParameter]
    is_async: bool

    cyclomatic_complexity: int | None = Field(ge=1)
    complexity_policy: str | None

    @field_validator("local_key", "name", "qualname")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        return _nonblank(value)

    @field_validator("parent_key", "complexity_policy")
    @classmethod
    def validate_optional_nonblank(
        cls,
        value: str | None,
    ) -> str | None:
        return _nonblank(value) if value is not None else None

    @model_validator(mode="after")
    def validate_ranges_and_metadata(self) -> Self:
        if self.end_line < self.start_line:
            raise ValueError("definition line range is reversed")

        if self.content_end_line < self.content_start_line:
            raise ValueError("content line range is reversed")

        if self.definition_end_byte <= self.definition_start_byte:
            raise ValueError(
                "definition byte range must be nonempty and ordered"
            )

        if self.content_end_byte <= self.content_start_byte:
            raise ValueError(
                "content byte range must be nonempty and ordered"
            )

        if not (
            self.content_start_byte <= self.definition_start_byte
            and self.definition_end_byte <= self.content_end_byte
            and self.content_start_line <= self.start_line
            and self.end_line <= self.content_end_line
        ):
            raise ValueError(
                "content range must contain the definition range"
            )

        if (
            self.cyclomatic_complexity is None
        ) != (
            self.complexity_policy is None
        ):
            raise ValueError(
                "complexity value and policy must be supplied together"
            )

        if self.kind == "class":
            if (
                self.signature is not None
                or self.parameters
                or self.is_async
            ):
                raise ValueError(
                    "classes require null signature, empty parameters, "
                    "and is_async=False"
                )

            if self.cyclomatic_complexity is not None:
                raise ValueError(
                    "class callable complexity must be null"
                )

        elif self.signature is None or not self.signature.strip():
            raise ValueError(
                "callables require a nonblank signature"
            )

        return self


class ParsedFile(_ExtractionModel):
    schema_version: Literal[1] = 1

    file_path: str = Field(min_length=1)

    source_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    source_text: str
    parse_buffer_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )

    symbols: list[ParsedSymbol]

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, value: str) -> str:
        _nonblank(value)
        parts = value.split("/")

        if (
            value.startswith("/")
            or "\\" in value
            or "\x00" in value
            or any(part in ("", ".", "..") for part in parts)
            or ":" in parts[0]
        ):
            raise ValueError(
                "file_path must be a repository-relative POSIX path "
                "without traversal"
            )

        return value

    @model_validator(mode="after")
    def validate_buffer_and_symbols(self) -> Self:
        buffer = self.source_text.encode("utf-8")

        if (
            hashlib.sha256(buffer).hexdigest()
            != self.parse_buffer_sha256
        ):
            raise ValueError(
                "parse_buffer_sha256 does not match source_text"
            )

        keys = [symbol.local_key for symbol in self.symbols]

        if len(set(keys)) != len(keys):
            raise ValueError(
                "symbol local keys must be unique"
            )

        expected_order = sorted(
            self.symbols,
            key=lambda symbol: (
                symbol.definition_start_byte,
                symbol.definition_end_byte,
                symbol.local_key,
            ),
        )

        if keys != [
            symbol.local_key for symbol in expected_order
        ]:
            raise ValueError(
                "symbols must follow deterministic "
                "definition-byte ordering"
            )

        by_key = {
            symbol.local_key: symbol
            for symbol in self.symbols
        }

        for symbol in self.symbols:
            expected_key = make_local_key(
                self.file_path,
                symbol.kind,
                symbol.qualname,
                symbol.definition_start_byte,
            )

            if symbol.local_key != expected_key:
                raise ValueError(
                    "local_key does not match "
                    "the canonical structured identity"
                )

            ranges = (
                (
                    symbol.definition_start_byte,
                    symbol.definition_end_byte,
                    symbol.start_line,
                    symbol.end_line,
                ),
                (
                    symbol.content_start_byte,
                    symbol.content_end_byte,
                    symbol.content_start_line,
                    symbol.content_end_line,
                ),
            )

            for start, end, first_line, last_line in ranges:
                if end > len(buffer):
                    raise ValueError(
                        "symbol byte range exceeds the parse buffer"
                    )

                try:
                    buffer[:start].decode("utf-8")
                    buffer[start:end].decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise ValueError(
                        "symbol offsets must lie on "
                        "UTF-8 character boundaries"
                    ) from exc

                expected_first = (
                    buffer.count(b"\n", 0, start) + 1
                )
                expected_last = (
                    buffer.count(b"\n", 0, end - 1) + 1
                )

                if (
                    first_line,
                    last_line,
                ) != (
                    expected_first,
                    expected_last,
                ):
                    raise ValueError(
                        "line range does not match the byte range"
                    )

            if (
                symbol.parent_key is not None
                and symbol.parent_key not in by_key
            ):
                raise ValueError(
                    "parent_key must reference a definition "
                    "in the same file"
                )

        for symbol in self.symbols:
            seen = {symbol.local_key}
            parent = symbol.parent_key

            while parent is not None:
                if parent in seen:
                    raise ValueError(
                        "symbol parent references contain a cycle"
                    )

                seen.add(parent)
                parent = by_key[parent].parent_key

        return self