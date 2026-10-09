"""Proposed v1 chunk-draft contract.

Drafts contain searchable text and source references, not database IDs.
"""

from typing import Literal, Self

from pydantic import ( #pydantic for data validation (ip and op must defined clearly, data paring ke liye we use pydantic)
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .parsing import DefinitionKind #parsing mai jo definition kind hai wahi use karna hai


SOURCE_SEPARATOR = "\n\n--- SOURCE ---\n"


class ChunkDraft(BaseModel):
    """One complete source chunk for an eligible definition."""

    model_config = ConfigDict(
        extra="forbid", #reject undeclared fields
        frozen=True, #renaming not allowed ek bar jo aya vo freeze
    )

    schema_version: Literal[1] = 1

    symbol_key: str = Field(min_length=1)
    file_path: str = Field(min_length=1)

    source_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    parse_buffer_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )

    qualname: str = Field(min_length=1)
    kind: DefinitionKind

    # Inclusive, 1-based content ranges, including decorators.
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    header_text: str = Field(min_length=1)
    body_text: str = Field(min_length=1)
    text: str = Field(min_length=1)

    @field_validator(
        "symbol_key",
        "qualname",
        "header_text",
        "body_text",
        "text",
    )
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "Value must contain non-whitespace content."
            )

        # Inspect whitespace, but never remove it.
        return value

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, value: str) -> str:
        parts = value.split("/")

        if (
            not value.strip()
            or value.startswith("/")
            or "\\" in value
            or "\x00" in value
            or any(part in ("", ".", "..") for part in parts)
            or ":" in parts[0]
        ):
            raise ValueError(
                "file_path must be a repository-relative POSIX path "
                "without traversal."
            )

        return value

    @model_validator(mode="after")
    def validate_range_and_text(self) -> Self:
        if self.end_line < self.start_line:
            raise ValueError(
                "Chunk line range is reversed."
            )

        expected_text = (
            self.header_text
            + SOURCE_SEPARATOR
            + self.body_text
        )

        if self.text != expected_text:
            raise ValueError(
                "text must equal header_text + "
                "SOURCE_SEPARATOR + body_text."
            )

        return self