from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from reposcope.contracts.evidence import Evidence
from reposcope.contracts.finding import Finding
from reposcope.contracts.repository import Repository
from reposcope.contracts.symbol import Symbol
from reposcope.contracts.urls import GitHubPullRequestURL, GitHubRepositoryURL
from reposcope.contracts.vocabulary import Direction, EdgeKind, FeedbackAction, SearchMode

PositiveID = Annotated[int, Field(gt=0)]
Confidence = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class RegisterRepoRequest(APIModel):
    url: GitHubRepositoryURL


class SearchRequest(APIModel):
    q: str = Field(min_length=1, max_length=2000)
    mode: SearchMode = "hybrid"


class AskRequest(APIModel):
    question: str = Field(min_length=1, max_length=10000)


class PRImpactRequest(APIModel):
    pr_url: GitHubPullRequestURL


class FeedbackRequest(APIModel):
    action: FeedbackAction


class RegisterRepoResponse(APIModel):
    repo_id: PositiveID
    status: Literal["pending"]
    message: str = Field(min_length=1)


class RepositoryResponse(Repository):
    id: PositiveID
    snapshot_id: PositiveID | None
    file_count: int | None = Field(ge=0)
    symbol_count: int | None = Field(ge=0)

    @model_validator(mode="after")
    def validate_snapshot_context(self) -> Self:
        if self.snapshot_id is None:
            if self.head_sha is not None or self.file_count is not None or self.symbol_count is not None:
                raise ValueError("SHA and counts require an explicit snapshot_id")
        elif self.head_sha is None:
            raise ValueError("An explicit snapshot requires head_sha")
        return self


class SymbolListItem(Symbol):
    id: PositiveID
    qualname: str = Field(min_length=1)
    file_path: str = Field(min_length=1)


class SymbolDetailResponse(SymbolListItem):
    signature: str | None = None
    docstring: str | None = None
    cyclomatic_complexity: int | None = Field(default=None, ge=1)


class SymbolListResponse(APIModel):
    symbols: list[SymbolListItem]


class SearchHit(APIModel):
    symbol_id: PositiveID
    name: str = Field(min_length=1)
    score: float = Field(allow_inf_nan=False)
    file_path: str = Field(min_length=1)
    snippet: str


class SearchResponse(APIModel):
    query: str = Field(min_length=1)
    hits: list[SearchHit]


class AskResponse(APIModel):
    answer: str = Field(min_length=1)
    evidence: list[Evidence]
    gaps: list[str]

    @model_validator(mode="after")
    def validate_evidence_ids(self) -> Self:
        ids = [item.evidence_id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence_id values must be unique within an answer")
        return self


class RecommendationItem(Finding):
    id: PositiveID


class RecommendationsResponse(APIModel):
    recommendations: list[RecommendationItem]


class Neighbor(APIModel):
    symbol_id: PositiveID
    name: str = Field(min_length=1)
    relationship_type: EdgeKind
    confidence: Confidence | None = None
    direction: Direction


class NeighborsResponse(APIModel):
    neighbors: list[Neighbor]


class FeedbackResponse(APIModel):
    status: Literal["ok"]
    id: PositiveID
    action: FeedbackAction


class HealthResponse(APIModel):
    status: Literal["ok"]
    v: str = Field(min_length=1)


class ErrorDetail(APIModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)
    status: int = Field(ge=400, le=599)


class ErrorResponse(APIModel):
    error: ErrorDetail
