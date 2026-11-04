"""Framework-derived graph records.

These records use graph-local keys, not database IDs.

Endpoint CALLS edges represent static route dispatch, not literal Python
call expressions. EXPOSES edges connect the declaring module to an endpoint.

Paths are declaration-local: application mounting and router registration
prefixes are not implied unless explicitly resolved by the detector.
"""

import json
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


Framework = Literal["fastapi", "flask"]
DerivedEdgeKind = Literal["EXPOSES", "CALLS", "USES"]


def make_endpoint_key(
    file_path: str,
    decorator_start_byte: int,
    method: str,
) -> str:
    """Identify a method on one route registration deterministically."""
    return json.dumps(
        ["endpoint", file_path, decorator_start_byte, method],
        ensure_ascii=False,
        separators=(",", ":"),
    )


class _DetectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DetectionEvidence(_DetectionModel):
    file_path: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    start_byte: int = Field(ge=0)
    end_byte: int = Field(ge=0)
    expression: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_span(self) -> Self:
        if self.end_line < self.start_line:
            raise ValueError("Evidence line range is reversed")
        if self.end_byte <= self.start_byte:
            raise ValueError("Evidence byte range must be nonempty")
        if len(self.expression.encode("utf-8")) != (
            self.end_byte - self.start_byte
        ):
            raise ValueError("Evidence text must match its byte length")
        return self


class DetectedEndpoint(_DetectionModel):
    key: str = Field(min_length=1)
    module_key: str = Field(min_length=1)
    handler_key: str = Field(min_length=1)
    framework: Framework
    receiver: str = Field(min_length=1)
    method: str = Field(pattern=r"^[A-Z]+$")
    path: str
    evidence: DetectionEvidence

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        expected = make_endpoint_key(
            self.evidence.file_path,
            self.evidence.start_byte,
            self.method,
        )
        if self.key != expected:
            raise ValueError("Endpoint key does not match its evidence")
        return self


class DetectedModel(_DetectionModel):
    symbol_key: str = Field(min_length=1)
    framework: Literal["sqlalchemy", "sqlmodel"]
    evidence: DetectionEvidence


class DerivedEdge(_DetectionModel):
    source_key: str = Field(min_length=1)
    target_key: str = Field(min_length=1)
    kind: DerivedEdgeKind
    confidence: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
    )
    evidence: DetectionEvidence


class DetectionGap(_DetectionModel):
    """An unsupported or uncertain case that produced no derived edge."""

    file_path: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    rule_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class DetectionResult(_DetectionModel):
    endpoints: tuple[DetectedEndpoint, ...] = ()
    models: tuple[DetectedModel, ...] = ()
    edges: tuple[DerivedEdge, ...] = ()
    gaps: tuple[DetectionGap, ...] = ()