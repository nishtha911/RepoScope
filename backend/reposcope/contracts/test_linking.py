"""Static test-to-implementation linking contracts.

TESTED_BY direction:
    implementation symbol -> test function/method

A link is static evidence of association, not runtime coverage or a
statement that the test passed.
"""

from typing import ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from reposcope.contracts.detection import (
    DerivedEdge,
    DetectionGap,
)


TestLinkRule = Literal[
    "direct_call",
    "two_hop_call",
    "name_match",
]


class TestLink(BaseModel):
    __test__: ClassVar[bool] = False

    model_config = ConfigDict(extra="forbid", frozen=True)

    implementation_key: str = Field(min_length=1)
    test_key: str = Field(min_length=1)
    rule: TestLinkRule

    confidence: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
    )

    # Ordered test -> [intermediate] -> implementation.
    # Naming-only links have no call path.
    call_path: tuple[str, ...] = ()

    # One resolver reference key per traversed call edge.
    reference_keys: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_path(self) -> Self:
        if self.implementation_key == self.test_key:
            raise ValueError("A test cannot link to itself")

        if self.rule == "name_match":
            if self.call_path or self.reference_keys:
                raise ValueError(
                    "Naming-only links cannot claim call-path evidence"
                )

            return self

        expected_nodes = (
            2 if self.rule == "direct_call" else 3
        )

        if len(self.call_path) != expected_nodes:
            raise ValueError(
                "Call path length does not match the linking rule"
            )

        if self.call_path[0] != self.test_key:
            raise ValueError("Call path must start at the test")

        if self.call_path[-1] != self.implementation_key:
            raise ValueError(
                "Call path must end at the implementation"
            )

        if len(set(self.call_path)) != len(self.call_path):
            raise ValueError("Call paths cannot contain cycles")

        if len(self.reference_keys) != expected_nodes - 1:
            raise ValueError(
                "Each call hop requires a reference key"
            )

        return self


class TestLinkingResult(BaseModel):
    __test__: ClassVar[bool] = False

    model_config = ConfigDict(extra="forbid", frozen=True)

    links: tuple[TestLink, ...] = ()
    edges: tuple[DerivedEdge, ...] = ()
    gaps: tuple[DetectionGap, ...] = ()