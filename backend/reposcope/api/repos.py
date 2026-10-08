"""Typed mock endpoints; these do not clone, query the database, or run an LLM."""
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query, status

from reposcope.contracts.api import (
    AskRequest, AskResponse, FeedbackRequest, FeedbackResponse,
    Neighbor, NeighborsResponse, PRImpactRequest, RecommendationItem,
    RecommendationsResponse, RegisterRepoRequest, RegisterRepoResponse,
    RepositoryResponse, SearchHit, SearchRequest, SearchResponse,
    SymbolDetailResponse, SymbolListItem, SymbolListResponse,
)
from reposcope.contracts.evidence import Evidence
from reposcope.contracts.pr_report import PRImpactReport
from reposcope.contracts.vocabulary import Direction, EdgeKind, SymbolKind
from typing import get_args

router = APIRouter(tags=["mock"])
PathID = Annotated[int, Path(gt=0)]
MOCK_SHA = "611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60"


def mock_symbol() -> SymbolListItem:
    return SymbolListItem(
        id=101, file_id=12, name="resolve_calls",
        qualname="SymbolResolver.resolve_calls", kind="method",
        file_path="backend/reposcope/parsing/resolver.py", start_line=142, end_line=180,
    )


@router.post("/repos", status_code=status.HTTP_202_ACCEPTED, response_model=RegisterRepoResponse)
def register_repo(payload: RegisterRepoRequest) -> RegisterRepoResponse:
    return RegisterRepoResponse(repo_id=1, status="pending", message="Repository ingestion enqueued")


@router.get("/repos/{repo_id}", response_model=RepositoryResponse)
def get_repo(repo_id: PathID) -> RepositoryResponse:
    return RepositoryResponse(
        id=repo_id, url="https://github.com/nishtha911/RepoScope", name="nishtha911/RepoScope",
        default_branch="main", status="ready", head_sha=MOCK_SHA, snapshot_id=1,
        symbol_count=3412, file_count=142,
    )


@router.get("/repos/{repo_id}/symbols", response_model=SymbolListResponse)
def get_symbols(
    repo_id: PathID,
    q: Annotated[str, Query(max_length=2000)] = "",
    kind: Annotated[SymbolKind | Literal[""], Query()] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SymbolListResponse:
    item = mock_symbol()
    matches = (not kind or item.kind == kind) and q.strip().lower() in item.qualname.lower()
    return SymbolListResponse(symbols=([item] if matches else [])[:limit])


@router.post("/repos/{repo_id}/search", response_model=SearchResponse)
def search_repo(repo_id: PathID, payload: SearchRequest) -> SearchResponse:
    return SearchResponse(query=payload.q, hits=[SearchHit(
        symbol_id=101, name="SymbolResolver.resolve_calls", score=0.032,
        file_path="backend/reposcope/parsing/resolver.py",
        snippet="def resolve_calls(self, ast_tree):",
    )])


@router.post("/repos/{repo_id}/ask", response_model=AskResponse)
def ask_repo(repo_id: PathID, payload: AskRequest) -> AskResponse:
    return AskResponse(
        answer=f"Analysis for query: '{payload.question}'. Scope resolver resolves function calls against the symbol table [E1].",
        evidence=[Evidence(
            evidence_id="E1", snapshot_id=1, file_id=12,
            file_path="backend/reposcope/parsing/resolver.py", symbol_id=101, chunk_id=5,
            start_line=142, end_line=160, text="def resolve_calls(self, ast_tree): ...",
        )], gaps=[],
    )


@router.post("/repos/{repo_id}/pr-impact", response_model=PRImpactReport)
def pr_impact(repo_id: PathID, payload: PRImpactRequest) -> PRImpactReport:
    return PRImpactReport(
        pr_url=payload.pr_url, risk_level="LOW", risk_score=0.04,
        files_changed_count=3, impacted_symbols_count=14,
        affected_endpoints_count=0, impacted_tests_count=2,
        summary="Modifies internal helper methods in resolver.py without API signature breaking changes.",
    )


@router.get("/repos/{repo_id}/recommendations", response_model=RecommendationsResponse)
def get_recommendations(
    repo_id: PathID, k: Annotated[int, Query(ge=1, le=100)] = 10,
) -> RecommendationsResponse:
    items = [RecommendationItem(
        id=1, snapshot_id=1, symbol_id=101, category="UNTESTED_HOTSPOT",
        title="Add unit test for SymbolResolver.resolve_calls",
        description="High fan-in symbol lacks direct unit test coverage.", score=0.94, confidence=0.9,
    )]
    return RecommendationsResponse(recommendations=items[:k])


@router.get("/symbols/{symbol_id}", response_model=SymbolDetailResponse)
def get_symbol_detail(symbol_id: PathID) -> SymbolDetailResponse:
    return SymbolDetailResponse(
        **{**mock_symbol().model_dump(), "id": symbol_id},
        signature="def resolve_calls(self, ast_tree) -> list[Edge]:",
        docstring="Resolves call expressions to candidate symbol IDs.", cyclomatic_complexity=4,
    )


@router.get("/symbols/{symbol_id}/neighbors", response_model=NeighborsResponse)
def get_symbol_neighbors(
    symbol_id: PathID,
    direction: Annotated[Direction, Query(alias="dir")] = "out",
    types: Annotated[str, Query(max_length=200)] = "",
) -> NeighborsResponse:
    selected = [part.strip() for part in types.split(",")] if types else []
    if any(kind not in get_args(EdgeKind) for kind in selected):
        raise HTTPException(status_code=422, detail="types must be comma-separated allowed edge kinds")
    neighbors = []
    if not selected or "CALLS" in selected:
        neighbors.append(Neighbor(
            symbol_id=204, name="SymbolScanner.scan", relationship_type="CALLS",
            confidence=1.0, direction=direction,
        ))
    return NeighborsResponse(neighbors=neighbors)


@router.post("/recs/{rec_id}/feedback", response_model=FeedbackResponse)
def submit_feedback(rec_id: PathID, payload: FeedbackRequest) -> FeedbackResponse:
    return FeedbackResponse(status="ok", id=rec_id, action=payload.action)
