"""Typed mock endpoints; these do not clone, query the database, or run an LLM."""
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query, status

from reposcope.contracts.api import (
    AskRequest, AskResponse, AskTimings, FeedbackRequest, FeedbackResponse,
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
# Verified historical RepoScope commit; other fixture values are synthetic.
MOCK_SHA = "d631c3f98581ab3ebdb0c8daa28cc8bf122f749a"


def mock_symbol() -> SymbolListItem:
    return SymbolListItem(
        id=101, file_id=12, name="resolve_calls",
        qualname="SymbolResolver.resolve_calls", kind="method",
        file_path="backend/reposcope/parsing/resolver.py", start_line=142, end_line=180,
    )


@router.post("/repos", status_code=status.HTTP_202_ACCEPTED, response_model=RegisterRepoResponse)
def register_repo(payload: RegisterRepoRequest) -> RegisterRepoResponse:
    return RegisterRepoResponse(repo_id=1, status="pending", message="Mock registration accepted; no ingestion job was enqueued")


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


def mock_search_hits() -> list[SearchHit]:
    return [
        SearchHit(
            symbol_id=101,
            name="SymbolResolver.resolve_calls",
            score=0.092,
            file_path="backend/reposcope/parsing/resolver.py",
            snippet="def resolve_calls(self, ast_tree) -> list[Edge]:\n    # Resolves call expressions to candidate symbol IDs",
        ),
        SearchHit(
            symbol_id=204,
            name="SymbolScanner.scan",
            score=0.078,
            file_path="backend/reposcope/ingestion/scanner.py",
            snippet="def scan(self, directory: Path) -> ScanResult:\n    # Scans directory and collects source files",
        ),
        SearchHit(
            symbol_id=301,
            name="POST /api/repos/{id}/search",
            score=0.065,
            file_path="backend/reposcope/api/repos.py",
            snippet='@router.post("/repos/{repo_id}/search", response_model=SearchResponse)\ndef search_repo(repo_id: PathID, payload: SearchRequest):',
        ),
        SearchHit(
            symbol_id=302,
            name="GET /api/symbols/{id}/neighbors",
            score=0.054,
            file_path="backend/reposcope/api/repos.py",
            snippet='@router.get("/symbols/{symbol_id}/neighbors", response_model=NeighborsResponse)\ndef get_symbol_neighbors(symbol_id: PathID):',
        ),
        SearchHit(
            symbol_id=401,
            name="Hybrid Search & Graph Traversal Architecture",
            score=0.049,
            file_path="docs/architecture.md",
            snippet="# Architecture Overview: Hybrid RRF Search with Reciprocal Rank Fusion",
        ),
        SearchHit(
            symbol_id=402,
            name="API Contract & Endpoints Specification",
            score=0.038,
            file_path="docs/api-contract.md",
            snippet="### 4. Search & GraphRAG Q&A: POST /api/repos/{id}/search",
        ),
    ]


@router.post("/repos/{repo_id}/search", response_model=SearchResponse)
def search_repo(repo_id: PathID, payload: SearchRequest) -> SearchResponse:
    query = payload.q.strip().lower()
    all_hits = mock_search_hits()
    matching = [h for h in all_hits if query in h.name.lower() or query in h.file_path.lower() or query in h.snippet.lower()]
    return SearchResponse(query=payload.q, hits=matching if matching else all_hits)


@router.post("/repos/{repo_id}/ask", response_model=AskResponse)
def ask_repo(repo_id: PathID, payload: AskRequest) -> AskResponse:
    return AskResponse(
        answer=f"Analysis for query: '{payload.question}'. Scope resolver resolves function calls against the symbol table [E1].",
        evidence=[Evidence(
            evidence_id="E1", snapshot_id=1, file_id=12,
            file_path="backend/reposcope/parsing/resolver.py", symbol_id=101, chunk_id=5,
            start_line=142, end_line=160, text="def resolve_calls(self, ast_tree): ...",
        )],
        gaps=[],
        timings=AskTimings(retrieval_ms=38, expansion_ms=14, synthesis_ms=112),
    )


@router.post("/repos/{repo_id}/pr-impact", response_model=PRImpactReport)
def pr_impact(repo_id: PathID, payload: PRImpactRequest) -> PRImpactReport:
    if payload.patch and not payload.pr_url:
        line_count = len(payload.patch.splitlines())
        return PRImpactReport(
            pr_url=None,
            patch_name="Pasted Git Patch",
            risk_level="MEDIUM" if line_count > 50 else "LOW",
            risk_score=min(round(0.02 + line_count * 0.003, 2), 0.75),
            files_changed_count=max(payload.patch.count("diff --git"), 1),
            impacted_symbols_count=max(payload.patch.count("def ") + payload.patch.count("class "), 4),
            affected_endpoints_count=payload.patch.count("@router") + payload.patch.count("@app"),
            impacted_tests_count=1 if "test" in payload.patch.lower() else 0,
            summary=f"Analysis of raw patch ({line_count} lines): modifications scanned across local AST graph.",
        )

    return PRImpactReport(
        pr_url=payload.pr_url,
        patch_name=None,
        risk_level="LOW",
        risk_score=0.04,
        files_changed_count=3,
        impacted_symbols_count=14,
        affected_endpoints_count=0,
        impacted_tests_count=2,
        summary="Modifies internal helper methods in resolver.py without API signature breaking changes.",
    )




@router.get("/symbols/{symbol_id}", response_model=SymbolDetailResponse)
def get_symbol_detail(symbol_id: PathID) -> SymbolDetailResponse:
    if symbol_id == 204:
        return SymbolDetailResponse(
            id=204, file_id=11, name="scan",
            qualname="SymbolScanner.scan", kind="method",
            file_path="backend/reposcope/ingestion/scanner.py", start_line=55, end_line=98,
            signature="def scan(self, directory: Path) -> ScanResult:",
            docstring="Scans a repository filesystem tree and collects source files.", cyclomatic_complexity=6,
        )
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
        if symbol_id == 101:
            if direction == "in":
                neighbors.append(Neighbor(
                    symbol_id=204, name="SymbolScanner.scan", relationship_type="CALLS",
                    confidence=1.0, direction="in",
                ))
            else:
                neighbors.append(Neighbor(
                    symbol_id=305, name="ReferenceResolver.resolve", relationship_type="CALLS",
                    confidence=0.92, direction="out",
                ))
        elif symbol_id == 204:
            if direction == "out":
                neighbors.append(Neighbor(
                    symbol_id=101, name="SymbolResolver.resolve_calls", relationship_type="CALLS",
                    confidence=1.0, direction="out",
                ))
            else:
                neighbors.append(Neighbor(
                    symbol_id=501, name="main.run_scan", relationship_type="CALLS",
                    confidence=0.88, direction="in",
                ))
        else:
            neighbors.append(Neighbor(
                symbol_id=101, name="SymbolResolver.resolve_calls", relationship_type="CALLS",
                confidence=0.95, direction=direction,
            ))
    return NeighborsResponse(neighbors=neighbors)


@router.post("/recs/{rec_id}/feedback", response_model=FeedbackResponse)
def submit_feedback(rec_id: PathID, payload: FeedbackRequest) -> FeedbackResponse:
    return FeedbackResponse(status="ok", id=rec_id, action=payload.action)
