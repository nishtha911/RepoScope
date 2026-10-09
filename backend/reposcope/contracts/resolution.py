"""Analysis contracts for the two-pass Python reference resolver."""

import hashlib
import json
import keyword
from pathlib import PurePosixPath
from typing import Literal, Self, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from reposcope.contracts.parsing import (
    DefinitionKind,
    ParsedFile,
    make_local_key,
)


ResolutionStatus = Literal[
    "EXACT",
    "INFERRED",
    "AMBIGUOUS",
    "UNRESOLVED",
]

ReferenceKind = Literal[
    "call",
    "import",
    "base_class",
]

TargetKind = Literal["module", "symbol"]

_HASH_PATTERN = r"^[0-9a-f]{64}$"


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("value must contain non-whitespace content")
    return value


def _validate_path(
    value: str,
    *,
    allow_root: bool = False,
) -> str:
    _nonblank(value)

    if allow_root and value == ".":
        return value

    parts = value.split("/")

    if (
        value.startswith("/")
        or "\\" in value
        or "\x00" in value
        or any(part in ("", ".", "..") for part in parts)
        or ":" in parts[0]
    ):
        raise ValueError(
            "path must be repository-relative POSIX without traversal"
        )

    return value


def _relative_python_path(
    file_path: str,
    source_root: str,
) -> PurePosixPath:
    try:
        relative = PurePosixPath(file_path).relative_to(
            PurePosixPath(source_root)
        )
    except ValueError as exc:
        raise ValueError(
            "file_path must be inside source_root"
        ) from exc

    if relative.suffix != ".py":
        raise ValueError("module file_path must identify a .py file")

    return relative


def make_module_key(
    source_root: str,
    file_path: str,
) -> str:
    return json.dumps(
        ["module", source_root, file_path],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def make_reference_key(
    file_path: str,
    reference_kind: ReferenceKind,
    start_byte: int,
    end_byte: int,
    scope_key: str,
) -> str:
    return json.dumps(
        [
            file_path,
            reference_kind,
            start_byte,
            end_byte,
            scope_key,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _module_key_parts(value: str) -> tuple[str, str]:
    try:
        parts = json.loads(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("module_key must be a JSON array") from exc

    if (
        not isinstance(parts, list)
        or len(parts) != 3
        or parts[0] != "module"
        or not isinstance(parts[1], str)
        or not isinstance(parts[2], str)
    ):
        raise ValueError(
            "module_key must contain ['module', source_root, file_path]"
        )

    source_root = _validate_path(
        parts[1],
        allow_root=True,
    )
    file_path = _validate_path(parts[2])

    _relative_python_path(file_path, source_root)

    if value != make_module_key(source_root, file_path):
        raise ValueError("module_key must use canonical JSON encoding")

    return source_root, file_path


def _symbol_key_parts(value: str) -> tuple[str, str, str, int]:
    try:
        parts = json.loads(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("symbol_key must be a JSON array") from exc

    if (
        not isinstance(parts, list)
        or len(parts) != 4
        or not isinstance(parts[0], str)
        or not isinstance(parts[1], str)
        or parts[1] not in get_args(DefinitionKind)
        or not isinstance(parts[2], str)
        or type(parts[3]) is not int
        or parts[3] < 0
    ):
        raise ValueError(
            "symbol_key must identify a Day 3 definition"
        )

    file_path = _validate_path(parts[0])
    kind = parts[1]
    qualname = _nonblank(parts[2])
    start_byte = parts[3]

    if value != make_local_key(
        file_path,
        kind,
        qualname,
        start_byte,
    ):
        raise ValueError("symbol_key must use canonical JSON encoding")

    return file_path, kind, qualname, start_byte


class _ResolverModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModuleInfo(_ResolverModel):
    module_key: str = Field(min_length=1)
    file_path: str = Field(min_length=1)
    source_root: str = Field(min_length=1)
    module_name: str | None

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, value: str) -> str:
        return _validate_path(value)

    @field_validator("source_root")
    @classmethod
    def validate_source_root(cls, value: str) -> str:
        return _validate_path(value, allow_root=True)

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        relative = _relative_python_path(
            self.file_path,
            self.source_root,
        )

        expected_key = make_module_key(
            self.source_root,
            self.file_path,
        )

        if self.module_key != expected_key:
            raise ValueError(
                "module_key does not match source_root and file_path"
            )

        parts = list(relative.parts)

        if parts[-1] == "__init__.py":
            parts.pop()
        else:
            parts[-1] = relative.stem

        importable = bool(parts) and all(
            part.isidentifier() and not keyword.iskeyword(part)
            for part in parts
        )

        expected_name = ".".join(parts) if importable else None

        if self.module_name != expected_name:
            raise ValueError(
                f"module_name must match the configured path: "
                f"{expected_name!r}"
            )

        return self


class ResolverTarget(_ResolverModel):
    target_kind: TargetKind
    module_key: str = Field(min_length=1)
    file_path: str = Field(min_length=1)
    symbol_key: str | None

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, value: str) -> str:
        return _validate_path(value)

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        _, module_path = _module_key_parts(self.module_key)

        if module_path != self.file_path:
            raise ValueError(
                "target file_path must match its module_key"
            )

        if self.target_kind == "module":
            if self.symbol_key is not None:
                raise ValueError(
                    "module targets require symbol_key=None"
                )

        else:
            if self.symbol_key is None:
                raise ValueError(
                    "symbol targets require a symbol_key"
                )

            symbol_path, _, _, _ = _symbol_key_parts(
                self.symbol_key
            )

            if symbol_path != self.file_path:
                raise ValueError(
                    "symbol_key must belong to the target file"
                )

        return self


class ReferenceSite(_ResolverModel):
    reference_key: str = Field(min_length=1)
    reference_kind: ReferenceKind
    file_path: str = Field(min_length=1)

    source_sha256: str = Field(pattern=_HASH_PATTERN)
    parse_buffer_sha256: str = Field(pattern=_HASH_PATTERN)

    scope_key: str = Field(min_length=1)
    source_owner: ResolverTarget
    expression: str = Field(min_length=1)

    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    start_byte: int = Field(ge=0)
    end_byte: int = Field(ge=0)

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, value: str) -> str:
        return _validate_path(value)

    @field_validator(
        "reference_key",
        "scope_key",
        "expression",
    )
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        return _nonblank(value)

    @model_validator(mode="after")
    def validate_location_and_owner(self) -> Self:
        if self.end_line < self.start_line:
            raise ValueError("reference line range is reversed")

        if self.end_byte <= self.start_byte:
            raise ValueError(
                "reference byte range must be nonempty and ordered"
            )

        expression_bytes = self.expression.encode("utf-8")

        if len(expression_bytes) != self.end_byte - self.start_byte:
            raise ValueError(
                "expression byte length must match the reference range"
            )

        expected_end_line = (
            self.start_line
            + expression_bytes.count(
                b"\n",
                0,
                len(expression_bytes) - 1,
            )
        )

        if self.end_line != expected_end_line:
            raise ValueError(
                "reference line span must match expression text"
            )

        if self.source_owner.file_path != self.file_path:
            raise ValueError(
                "source_owner must belong to the reference file"
            )

        if self.reference_kind == "base_class":
            if self.source_owner.target_kind != "symbol":
                raise ValueError(
                    "base_class references require a subclass owner"
                )

            _, owner_kind, _, _ = _symbol_key_parts(
                self.source_owner.symbol_key
            )

            if owner_kind != "class":
                raise ValueError(
                    "base_class source_owner must identify a class"
                )

        expected_key = make_reference_key(
            self.file_path,
            self.reference_kind,
            self.start_byte,
            self.end_byte,
            self.scope_key,
        )

        if self.reference_key != expected_key:
            raise ValueError(
                "reference_key does not match its structured identity"
            )

        return self

    def validate_against_file(self, parsed_file: ParsedFile) -> Self:
        """Check location, hashes, and owner against actual parser output."""
        if self.file_path != parsed_file.file_path:
            raise ValueError("reference file does not match ParsedFile")

        if (
            self.source_sha256 != parsed_file.source_sha256
            or self.parse_buffer_sha256
            != parsed_file.parse_buffer_sha256
        ):
            raise ValueError(
                "reference hashes do not match ParsedFile"
            )

        buffer = parsed_file.source_text.encode("utf-8")

        if (
            hashlib.sha256(buffer).hexdigest()
            != parsed_file.parse_buffer_sha256
        ):
            raise ValueError(
                "ParsedFile source buffer has changed"
            )

        if self.end_byte > len(buffer):
            raise ValueError(
                "reference range exceeds the source buffer"
            )

        if (
            buffer[self.start_byte:self.end_byte]
            != self.expression.encode("utf-8")
        ):
            raise ValueError(
                "reference expression does not match the source slice"
            )

        expected_lines = (
            buffer.count(b"\n", 0, self.start_byte) + 1,
            buffer.count(b"\n", 0, self.end_byte - 1) + 1,
        )

        if (self.start_line, self.end_line) != expected_lines:
            raise ValueError(
                "reference lines do not match source offsets"
            )

        if self.source_owner.target_kind == "symbol":
            by_key = {
                symbol.local_key: symbol
                for symbol in parsed_file.symbols
            }

            owner = by_key.get(self.source_owner.symbol_key)

            if owner is None:
                raise ValueError(
                    "source_owner is missing from ParsedFile"
                )

            if self.reference_kind == "base_class":
                owner_start = owner.definition_start_byte
                owner_end = owner.definition_end_byte
            else:
                owner_start = owner.content_start_byte
                owner_end = owner.content_end_byte

            if not (
                owner_start <= self.start_byte
                and self.end_byte <= owner_end
            ):
                raise ValueError(
                    "reference must lie inside its source owner"
                )

        return self


class ResolutionResult(_ResolverModel):
    schema_version: Literal[1] = 1
    resolution_policy: Literal["python_resolver_v1"] = (
        "python_resolver_v1"
    )

    reference: ReferenceSite
    status: ResolutionStatus
    targets: list[ResolverTarget]

    rule_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)

    confidence: float | None = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
    )

    @field_validator("rule_id", "reason")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        return _nonblank(value)

    @model_validator(mode="after")
    def validate_resolution(self) -> Self:
        identities = [
            (
                target.target_kind,
                target.module_key,
                target.symbol_key,
            )
            for target in self.targets
        ]

        if len(set(identities)) != len(identities):
            raise ValueError(
                "resolution candidate identities must be unique"
            )

        count = len(self.targets)

        if self.status in {"EXACT", "INFERRED"}:
            if count != 1:
                raise ValueError(
                    "EXACT/INFERRED require exactly one target"
                )

        elif self.status == "AMBIGUOUS":
            if count < 2:
                raise ValueError(
                    "AMBIGUOUS requires at least two targets"
                )

        elif count != 0:
            raise ValueError(
                "UNRESOLVED requires no targets"
            )

        expected_confidence = {
            "EXACT": 1.0,
            "INFERRED": 0.5,
            "AMBIGUOUS": None,
            "UNRESOLVED": None,
        }[self.status]

        if self.confidence != expected_confidence:
            raise ValueError(
                f"{self.status} requires confidence="
                f"{expected_confidence!r} under python_resolver_v1"
            )

        return self