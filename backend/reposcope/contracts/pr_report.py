from pydantic import BaseModel, ConfigDict, Field


from reposcope.contracts.urls import GitHubPullRequestURL


class PRImpactReport(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    pr_url: GitHubPullRequestURL
    risk_level: str = Field(pattern=r"^(LOW|MEDIUM|HIGH|CRITICAL)$")
    risk_score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    files_changed_count: int = Field(ge=0)
    impacted_symbols_count: int = Field(ge=0)
    affected_endpoints_count: int = Field(ge=0)
    impacted_tests_count: int = Field(ge=0)
    summary: str = Field(default="")
