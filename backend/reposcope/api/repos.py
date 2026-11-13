"""Repository, search, graph, and analysis API endpoints."""
import re
import hashlib
from typing import Annotated, Literal
from sqlalchemy import func, or_, select

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
from reposcope.db.session import SessionLocal
from reposcope.models import (
    Edge,
    File,
    PRImpactFeedback,
    Repository as RepositoryRecord,
    RepositorySnapshot,
    Symbol,
)

router = APIRouter(tags=["repositories"])
PathID = Annotated[int, Path(gt=0)]


@router.post("/repos", status_code=status.HTTP_202_ACCEPTED, response_model=RegisterRepoResponse)
def register_repo(payload: RegisterRepoRequest) -> RegisterRepoResponse:
    with SessionLocal.begin() as session:
        existing = session.scalar(
            select(RepositoryRecord).where(RepositoryRecord.remote_url == str(payload.url))
        )
        if existing:
            return RegisterRepoResponse(repo_id=existing.id, status="pending", message="Repository is already registered")
        name = str(payload.url).rstrip("/").split("/")[-2:]
        record = RepositoryRecord(full_name="/".join(name), remote_url=str(payload.url))
        session.add(record)
        session.flush()
        return RegisterRepoResponse(repo_id=record.id, status="pending", message="Repository registered")


@router.get("/repos/{repo_id}", response_model=RepositoryResponse)
def get_repo(repo_id: PathID) -> RepositoryResponse:
    with SessionLocal() as session:
        record = session.get(RepositoryRecord, repo_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Repository was not found")
        snapshot = session.scalar(
            select(RepositorySnapshot)
            .where(RepositorySnapshot.repository_id == repo_id)
            .order_by(RepositorySnapshot.created_at.desc())
        )
        file_count = session.scalar(select(func.count(File.id)).where(File.repository_id == repo_id))
        symbol_count = session.scalar(
            select(func.count(Symbol.id)).join(File, Symbol.file_id == File.id)
            .where(File.repository_id == repo_id)
        )
        return RepositoryResponse(
            id=record.id, url=record.remote_url, name=record.full_name,
            default_branch="main", status=snapshot.status if snapshot else "pending",
            head_sha=snapshot.commit_sha if snapshot else None,
            snapshot_id=snapshot.id if snapshot else None,
            symbol_count=symbol_count or 0, file_count=file_count or 0,
        )


@router.get("/repos/{repo_id}/symbols", response_model=SymbolListResponse)
def get_symbols(
    repo_id: PathID,
    q: Annotated[str, Query(max_length=2000)] = "",
    kind: Annotated[SymbolKind | Literal[""], Query()] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SymbolListResponse:
    with SessionLocal() as session:
        statement = select(Symbol, File.path).join(File, Symbol.file_id == File.id).where(File.repository_id == repo_id)
        if q.strip():
            pattern = f"%{q.strip()}%"
            statement = statement.where(or_(Symbol.name.ilike(pattern), Symbol.qualname.ilike(pattern), File.path.ilike(pattern)))
        if kind:
            statement = statement.where(Symbol.kind == kind)
        rows = session.execute(statement.limit(limit)).all()
        return SymbolListResponse(symbols=[
            SymbolListItem(id=s.id, file_id=s.file_id, name=s.name,
                qualname=s.qualname or s.name, kind=s.kind, file_path=path,
                start_line=s.start_line, end_line=s.end_line)
            for s, path in rows
        ])


@router.post("/repos/{repo_id}/search", response_model=SearchResponse)
def search_repo(repo_id: PathID, payload: SearchRequest) -> SearchResponse:
    with SessionLocal() as session:
        pattern = f"%{payload.q.strip()}%"
        rows = session.execute(
            select(Symbol, File.path).join(File, Symbol.file_id == File.id)
            .where(File.repository_id == repo_id)
            .where(or_(Symbol.name.ilike(pattern), Symbol.qualname.ilike(pattern), File.path.ilike(pattern)))
            .limit(100)
        ).all()
        return SearchResponse(query=payload.q, hits=[
            SearchHit(symbol_id=s.id, name=s.qualname or s.name, score=1.0,
                file_path=path, snippet=f"{s.name} ({s.kind})")
            for s, path in rows
        ])


@router.post("/repos/{repo_id}/ask", response_model=AskResponse)
def ask_repo(repo_id: PathID, payload: AskRequest) -> AskResponse:
    raise HTTPException(
        status_code=501,
        detail="Repository Q&A is unavailable until retrieval and synthesis services are configured.",
    )


@router.post("/repos/{repo_id}/pr-impact", response_model=PRImpactReport)
def pr_impact(repo_id: PathID, payload: PRImpactRequest) -> PRImpactReport:
    if payload.patch and not payload.pr_url:
        line_count = len(payload.patch.splitlines())
        changed_paths = re.findall(
            r"^\+\+\+ b/(.+)$", payload.patch, flags=re.MULTILINE
        )
        changed_paths = [path for path in changed_paths if path != "/dev/null"]
        analysis_key = _pr_analysis_key(payload)
        with SessionLocal() as session:
            repository = session.get(RepositoryRecord, repo_id)
            if repository is None:
                raise HTTPException(status_code=404, detail="Repository was not found")

            changed_symbols = session.execute(
                select(Symbol, File.path)
                .join(File, Symbol.file_id == File.id)
                .where(File.repository_id == repo_id)
                .where(File.path.in_(changed_paths))
            ).all() if changed_paths else []
            changed_ids = [symbol.id for symbol, _ in changed_symbols]

            tested_rows = session.execute(
                select(Edge, Symbol, File.path)
                .join(Symbol, Symbol.id == Edge.target_symbol_id)
                .join(File, File.id == Symbol.file_id)
                .where(Edge.source_symbol_id.in_(changed_ids))
                .where(Edge.kind == "TESTED_BY")
            ).all() if changed_ids else []
            tested_ids = {edge.source_symbol_id for edge, _, _ in tested_rows}

            impacted_tests = [
                {
                    "id": str(test_symbol.id),
                    "test_name": test_symbol.qualname or test_symbol.name,
                    "file_path": test_path,
                    "confidence": edge.confidence if edge.confidence is not None else 0.0,
                }
                for edge, test_symbol, test_path in tested_rows
            ]
            missing_tests = [
                {
                    "symbol_id": symbol.id,
                    "symbol_name": symbol.qualname or symbol.name,
                    "file_path": path,
                    "reason": "No TESTED_BY edge exists in the indexed graph.",
                }
                for symbol, path in changed_symbols
                if symbol.id not in tested_ids and symbol.kind in ("function", "method", "class")
            ]

            endpoint_rows = session.execute(
                select(Symbol, File.path, Edge.confidence)
                .join(File, Symbol.file_id == File.id)
                .join(
                    Edge,
                    Edge.target_symbol_id == Symbol.id,
                )
                .where(File.repository_id == repo_id)
                .where(Edge.kind == "EXPOSES")
                .where(Edge.source_symbol_id.in_(changed_ids))
            ).all()
            direct_endpoint_rows = session.execute(
                select(Symbol, File.path)
                .join(File, Symbol.file_id == File.id)
                .where(File.repository_id == repo_id)
                .where(Symbol.id.in_(changed_ids))
                .where(Symbol.kind == "endpoint")
            ).all() if changed_ids else []
            impacted_endpoints = [
                {
                    "method": _endpoint_method(symbol.name),
                    "route": symbol.name,
                    "handler_name": symbol.qualname or symbol.name,
                    "file_path": path,
                    "confidence": confidence if confidence is not None else 0.0,
                }
                for symbol, path, confidence in endpoint_rows
            ]
            impacted_endpoints.extend(
                {
                    "method": _endpoint_method(symbol.name),
                    "route": symbol.name,
                    "handler_name": symbol.qualname or symbol.name,
                    "file_path": path,
                    "confidence": 1.0,
                }
                for symbol, path in direct_endpoint_rows
            )
            feedback = session.scalar(
                select(PRImpactFeedback.action)
                .where(PRImpactFeedback.repository_id == repo_id)
                .where(PRImpactFeedback.analysis_key == analysis_key)
                .order_by(PRImpactFeedback.id.desc())
            ) or "pending"

        return PRImpactReport(
            pr_url=None,
            patch_name="Pasted Git Patch",
            risk_level="MEDIUM" if line_count > 50 else "LOW",
            risk_score=min(round(0.02 + line_count * 0.003, 2), 0.75),
            files_changed_count=len(changed_paths),
            impacted_symbols_count=len(changed_symbols),
            affected_endpoints_count=len(impacted_endpoints),
            impacted_tests_count=len(impacted_tests),
            summary=f"Analyzed {line_count} changed lines against the indexed repository graph.",
            impacted_tests=impacted_tests,
            missing_tests=missing_tests,
            impacted_endpoints=impacted_endpoints,
            feedback=feedback,
        )

    raise HTTPException(
        status_code=501,
        detail="PR URL analysis is unavailable; submit the patch produced by the repository provider.",
    )


def _pr_analysis_key(payload: PRImpactRequest) -> str:
    if payload.pr_url:
        return str(payload.pr_url)
    digest = hashlib.sha256((payload.patch or "").encode("utf-8")).hexdigest()
    return f"patch:{digest}"


def _endpoint_method(name: str) -> str:
    method = name.split(" ", 1)[0].upper()
    return method if method in {"GET", "POST", "PUT", "DELETE", "PATCH"} else "UNKNOWN"


@router.post("/repos/{repo_id}/pr-impact/feedback", response_model=FeedbackResponse)
def submit_pr_impact_feedback(
    repo_id: PathID,
    payload: FeedbackRequest,
    analysis_key: Annotated[str, Query(min_length=1, max_length=512)],
) -> FeedbackResponse:
    with SessionLocal.begin() as session:
        if session.get(RepositoryRecord, repo_id) is None:
            raise HTTPException(status_code=404, detail="Repository was not found")
        record = PRImpactFeedback(
            repository_id=repo_id,
            analysis_key=analysis_key,
            action=payload.action,
        )
        session.add(record)
        session.flush()
        return FeedbackResponse(status="ok", id=record.id, action=payload.action)




@router.get("/symbols/{symbol_id}", response_model=SymbolDetailResponse)
def get_symbol_detail(symbol_id: PathID) -> SymbolDetailResponse:
    with SessionLocal() as session:
        row = session.execute(
            select(Symbol, File.path).join(File, Symbol.file_id == File.id)
            .where(Symbol.id == symbol_id)
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Symbol was not found")
        symbol, path = row
        return SymbolDetailResponse(id=symbol.id, file_id=symbol.file_id,
            name=symbol.name, qualname=symbol.qualname or symbol.name,
            kind=symbol.kind, file_path=path, start_line=symbol.start_line,
            end_line=symbol.end_line, signature=None, docstring=None,
            cyclomatic_complexity=None)


@router.get("/symbols/{symbol_id}/neighbors", response_model=NeighborsResponse)
def get_symbol_neighbors(
    symbol_id: PathID,
    direction: Annotated[Direction, Query(alias="dir")] = "out",
    types: Annotated[str, Query(max_length=200)] = "",
) -> NeighborsResponse:
    selected = [part.strip() for part in types.split(",")] if types else []
    if any(kind not in get_args(EdgeKind) for kind in selected):
        raise HTTPException(status_code=422, detail="types must be comma-separated allowed edge kinds")
    with SessionLocal() as session:
        statement = (
            select(Edge, Symbol)
            .join(Symbol, Symbol.id == (Edge.target_symbol_id if direction == "in" else Edge.source_symbol_id))
            .where((Edge.target_symbol_id if direction == "in" else Edge.source_symbol_id) == symbol_id)
        )
        if selected:
            statement = statement.where(Edge.kind.in_(selected))
        rows = session.execute(statement).all()
        return NeighborsResponse(neighbors=[
            Neighbor(symbol_id=s.id, name=s.qualname or s.name,
                relationship_type=edge.kind, confidence=edge.confidence,
                direction=direction)
            for edge, s in rows
        ])


@router.post("/recs/{rec_id}/feedback", response_model=FeedbackResponse)
def submit_feedback(rec_id: PathID, payload: FeedbackRequest) -> FeedbackResponse:
    return FeedbackResponse(status="ok", id=rec_id, action=payload.action)
