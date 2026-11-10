from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from reposcope.contracts.urls import GitHubPullRequestURL


class PRImpactReport(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    pr_url: GitHubPullRequestURL | None = None
    patch_name: str | None = None
    risk_level: str = Field(pattern=r"^(LOW|MEDIUM|HIGH|CRITICAL)$")
    risk_score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    files_changed_count: int = Field(ge=0)
    impacted_symbols_count: int = Field(ge=0)
    affected_endpoints_count: int = Field(ge=0)
    impacted_tests_count: int = Field(ge=0)
    summary: str = Field(default="")


class PRReportMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    files_changed_count: int = Field(ge=0)
    changed_lines_count: int = Field(ge=0)
    modified_symbols_count: int = Field(ge=0)
    impacted_symbols_count: int = Field(ge=0)
    affected_endpoints_count: int = Field(ge=0)
    impacted_tests_count: int = Field(ge=0)
    untested_modified_symbols_count: int = Field(ge=0)


class SummaryMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["llm_grounded", "deterministic"]
    degraded_reason: str | None = None
    citations: dict[str, Any] = Field(default_factory=dict)


class PRAnalysisReport(BaseModel):
    """Structured, immutable PR analysis report with grounded executive review summary."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    report_version: Literal["pr-analysis-v1"] = "pr-analysis-v1"
    repository_id: int = Field(gt=0)
    pr_url: GitHubPullRequestURL | None = None
    pr_number: int | None = Field(default=None, gt=0)
    patch_name: str | None = None
    base_revision: str | None = None
    head_revision: str | None = None

    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL", "INCOMPLETE"]
    risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    risk_status: Literal["COMPLETE", "INCOMPLETE"]
    score_bounds: tuple[float, float] | None = None

    features: dict[str, float | None] = Field(default_factory=dict)
    feature_contributions: dict[str, float] = Field(default_factory=dict)

    metrics: PRReportMetrics
    impacted_endpoints: list[dict[str, Any]] = Field(default_factory=list)
    untested_modified_symbols: list[dict[str, Any]] = Field(default_factory=list)
    contract_changes: int = Field(ge=0)
    maximum_complexity_increase: int | None = Field(default=None, ge=0)
    gaps: list[str] = Field(default_factory=list)

    executive_summary: str = Field(min_length=1)
    summary_metadata: SummaryMetadata
    created_at: str = Field(min_length=1)
