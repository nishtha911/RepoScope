"""Deterministic policy scores, not calibrated probabilities of failure."""
from typing import Literal
from decimal import Decimal
from types import MappingProxyType
from pydantic import BaseModel, ConfigDict, Field

FEATURE_WEIGHTS = MappingProxyType({
    "blast_radius": Decimal("0.30"), "sensitivity": Decimal("0.20"),
    "test_gap": Decimal("0.20"), "contract_changes": Decimal("0.15"),
    "complexity_delta": Decimal("0.10"), "size": Decimal("0.05"),
})


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class RiskFeatures(Record):
    blast_radius: float | None = Field(default=None, ge=0, le=1)
    sensitivity: float | None = Field(default=None, ge=0, le=1)
    test_gap: float | None = Field(default=None, ge=0, le=1)
    contract_changes: float | None = Field(default=None, ge=0, le=1)
    complexity_delta: float | None = Field(default=None, ge=0, le=1)
    size: float | None = Field(default=None, ge=0, le=1)


class RiskPolicy(Record):
    version: Literal["risk_v1"] = "risk_v1"
    blast_mass_cap: float = Field(default=50, gt=0)
    complexity_increase_cap: int = Field(default=10, gt=0, strict=True)
    changed_lines_cap: int = Field(default=500, gt=0, strict=True)


class RiskComponent(Record):
    name: str
    value: float | None
    weight: float
    contribution: float | None


class RiskScore(Record):
    policy_version: str
    status: Literal["COMPLETE", "INCOMPLETE"]
    score: float | None
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] | None
    lower_bound: float
    upper_bound: float
    components: tuple[RiskComponent, ...]
    missing_features: tuple[str, ...]
    warnings: tuple[str, ...]


def score_risk(features: RiskFeatures) -> RiskScore:
    """Do not renormalize around unknown features; expose the full score interval."""
    features = RiskFeatures.model_validate(features.model_dump())
    lower = Decimal(0)
    missing_weight = Decimal(0)
    components, missing = [], []
    for name, weight in FEATURE_WEIGHTS.items():
        value = getattr(features, name)
        contribution = None if value is None else Decimal(str(value)) * weight
        if contribution is None:
            missing.append(name)
            missing_weight += weight
        else:
            lower += contribution
        components.append(RiskComponent(name=name, value=value, weight=float(weight),
            contribution=None if contribution is None else float(contribution)))
    score = None if missing else float(lower)
    level = None if missing else (
        "LOW" if lower < Decimal("0.25") else "MEDIUM" if lower < Decimal("0.50")
        else "HIGH" if lower < Decimal("0.75") else "CRITICAL")
    return RiskScore(policy_version="risk_v1", status="INCOMPLETE" if missing else "COMPLETE",
        score=score, risk_level=level, lower_bound=float(lower),
        upper_bound=float(lower + missing_weight), components=tuple(components),
        missing_features=tuple(missing),
        warnings=("Policy score is not a probability of failure.",
                  "Static test links are not runtime coverage."))
