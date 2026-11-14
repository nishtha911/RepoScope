"""Repository, search, graph, and analysis API endpoints."""
import re
import hashlib
from typing import Annotated, Literal
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import aliased

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
from reposcope.ingestion.index_preparation import INDEX_VERSION
from reposcope.jobs.queue import enqueue_job
from reposcope.models import (
    Edge,
    File,
    PRImpactFeedback,
    Repository as RepositoryRecord,
    RepositorySnapshot,
    Symbol,
)

from reposcope.retrieval.search_service import (
    run_repository_search, SearchNotFoundError, SearchNotReadyError, SearchResultError,
)
from reposcope.retrieval.vector import EmbeddingIndexMismatchError
from reposcope.retrieval.gemini_embeddings import (
    EmbeddingAuthenticationError, EmbeddingConfigurationError, EmbeddingQuotaError,
    EmbeddingTransportError, GeminiEmbeddingError,
)

from reposcope.rag.qa_service import (
    answer_question, QuestionInputError, QuestionNotFoundError,
    QuestionNotReadyError, QuestionContextError,
)
from reposcope.rag.validator import CitationValidationError
from reposcope.integrations.llm import (
    LLMConfigurationError, LLMUnavailable, LLMOutputError, LLMError,
)

router = APIRouter(tags=["repositories"])
PathID = Annotated[int, Path(gt=0)]


@router.post("/repos", status_code=status.HTTP_202_ACCEPTED, response_model=RegisterRepoResponse)
def register_repo(payload: RegisterRepoRequest) -> RegisterRepoResponse:
    # Request validation already restricts URLs to credential-free github.com HTTPS.
    parts = str(payload.url).rstrip("/").split("/")[-2:]
    owner, repository_name = parts
    if repository_name.endswith(".git"):
        repository_name = repository_name[:-4]
    if (len(owner) > 39 or not 1 <= len(repository_name) <= 100
            or repository_name in {".", ".."}):
        raise HTTPException(status_code=422, detail="Unsupported GitHub repository name")
    full_name = f"{owner}/{repository_name}".lower()
    canonical_url = f"https://github.com/{full_name}"
    lock_key = int.from_bytes(hashlib.sha256(full_name.encode()).digest()[:8],
                              byteorder="big", signed=True)

    with SessionLocal.begin() as session:
        # PostgreSQL-only registration: serialize canonical URL variants across
        # API replicas. The transaction releases this advisory lock automatically.
        session.execute(text("SET LOCAL lock_timeout = '5s'"))
        session.execute(text("SET LOCAL statement_timeout = '15s'"))
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        matches = session.scalars(select(RepositoryRecord).where(or_(
            func.lower(RepositoryRecord.full_name) == full_name,
            func.lower(func.rtrim(RepositoryRecord.remote_url, "/")).in_(
                [canonical_url, canonical_url + ".git"]),
        )).with_for_update()).all()
        if len(matches) > 1:
            raise HTTPException(status_code=409, detail="Duplicate repository records require review")
        if matches:
            record = matches[0]
            existing_url = record.remote_url.rstrip("/")
            if existing_url.endswith(".git"):
                existing_url = existing_url[:-4]
            if existing_url.lower() != canonical_url:
                raise HTTPException(status_code=409, detail="Existing repository URL requires review")
        else:
            record = RepositoryRecord(full_name=full_name, remote_url=canonical_url)
            session.add(record)
            session.flush()

        ready = session.scalar(select(RepositorySnapshot.id).where(
            RepositorySnapshot.repository_id == record.id,
            RepositorySnapshot.status == "ready").limit(1))
        if ready is not None:
            return RegisterRepoResponse(repo_id=record.id, status="pending",
                message="Repository is already indexed; fetch repository details for its current state")

        file_count = session.scalar(select(func.count(File.id)).where(File.repository_id == record.id))
        if file_count:
            raise HTTPException(status_code=409,
                detail="Repository has existing files without a ready index; review before ingestion")
        active = session.execute(text("""
            SELECT id, status FROM ingestion_jobs
            WHERE repository_id=:repo AND status IN ('queued', 'running')
            ORDER BY id LIMIT 1
        """), {"repo": record.id}).mappings().one_or_none()
        if active is not None:
            return RegisterRepoResponse(repo_id=record.id, status="pending",
                message=f"Ingestion job {active['id']} is {active['status']}; fetch repository details for progress")

        job_id = enqueue_job(session, record.id, f"register:{INDEX_VERSION}", max_attempts=3)
        job_status = session.execute(text("SELECT status FROM ingestion_jobs WHERE id=:id"),
                                     {"id": job_id}).scalar_one()
        if job_status not in {"queued", "running"}:
            raise HTTPException(status_code=409,
                detail="Previous ingestion job is terminal; review it before requesting a retry")
        return RegisterRepoResponse(repo_id=record.id, status="pending",
            message=f"Repository registered; ingestion job {job_id} is {job_status}")


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
            symbol_count=(symbol_count or 0) if snapshot else None,
            file_count=(file_count or 0) if snapshot else None,
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
    try:
        with SessionLocal() as session:
            return run_repository_search(session, repo_id=repo_id,
                query=payload.q, mode=payload.mode, limit=10)
    except SearchNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except (SearchNotReadyError, EmbeddingIndexMismatchError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except EmbeddingQuotaError:
        raise HTTPException(status_code=503,
            detail="Embedding provider quota is unavailable; try again later or use lexical search") from None
    except (EmbeddingAuthenticationError, EmbeddingConfigurationError):
        raise HTTPException(status_code=503,
            detail="Embedding provider is not configured or accessible") from None
    except EmbeddingTransportError:
        raise HTTPException(status_code=503,
            detail="Embedding provider is temporarily unreachable; try again later or use lexical search") from None
    except GeminiEmbeddingError:
        raise HTTPException(status_code=502,
            detail="Embedding provider returned an unusable response") from None
    except SearchResultError:
        raise HTTPException(status_code=500,
            detail="Indexed search metadata is inconsistent") from None


@router.post("/repos/{repo_id}/ask", response_model=AskResponse)
async def ask_repo(repo_id: PathID, payload: AskRequest) -> AskResponse:
    try:
        result = await answer_question(SessionLocal, repo_id, payload.question)
        return result.response
    except QuestionInputError:
        raise HTTPException(status_code=422,
            detail="Question must contain 1..4096 characters") from None
    except QuestionNotFoundError:
        raise HTTPException(status_code=404, detail="Repository was not found") from None
    except QuestionNotReadyError:
        raise HTTPException(status_code=409, detail="Repository index is not ready") from None
    except EmbeddingIndexMismatchError:
        raise HTTPException(status_code=409,
            detail="Q&A requires a compatible Gemini index; explicit migration is required") from None
    except QuestionContextError:
        raise HTTPException(status_code=409,
            detail="Verified source context could not be assembled for this snapshot") from None
    except EmbeddingQuotaError:
        raise HTTPException(status_code=503,
            detail="Embedding provider quota is unavailable; try again later") from None
    except EmbeddingTransportError:
        raise HTTPException(status_code=503,
            detail="Embedding provider is temporarily unreachable") from None
    except (EmbeddingAuthenticationError, EmbeddingConfigurationError, LLMConfigurationError):
        raise HTTPException(status_code=503,
            detail="Q&A provider configuration is unavailable") from None
    except LLMUnavailable:
        raise HTTPException(status_code=503,
            detail="Answer-generation provider is temporarily unavailable") from None
    except (CitationValidationError, LLMOutputError):
        raise HTTPException(status_code=502,
            detail="Generated answer failed evidence or output validation; no answer was returned") from None
    except GeminiEmbeddingError:
        raise HTTPException(status_code=502,
            detail="Embedding provider returned an unusable response") from None
    except LLMError:
        raise HTTPException(status_code=502,
            detail="Answer-generation request failed") from None


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
    allowed = tuple(get_args(EdgeKind))
    selected = [part.strip() for part in types.split(",")] if types else []
    if any(kind not in allowed for kind in selected):
        raise HTTPException(status_code=422, detail="types must be comma-separated allowed edge kinds")
    requested = tuple(selected) if selected else allowed
    anchor = aliased(Symbol)
    anchor_file = aliased(File)
    neighbor_file = aliased(File)
    anchor_id = Edge.source_symbol_id if direction == "out" else Edge.target_symbol_id
    neighbor_id = Edge.target_symbol_id if direction == "out" else Edge.source_symbol_id
    with SessionLocal() as session:
        statement = (
            select(Edge, Symbol)
            .join(Symbol, Symbol.id == neighbor_id)
            .join(anchor, anchor.id == anchor_id)
            .join(anchor_file, anchor_file.id == anchor.file_id)
            .join(neighbor_file, neighbor_file.id == Symbol.file_id)
            .where(anchor.id == symbol_id,
                   anchor_file.repository_id == neighbor_file.repository_id,
                   Edge.kind.in_(requested))
            .order_by(Edge.id, Symbol.id)
        )
        rows = session.execute(statement).all()
        return NeighborsResponse(neighbors=[
            Neighbor(symbol_id=s.id, name=s.qualname or s.name,
                relationship_type=edge.kind, confidence=edge.confidence,
                direction=direction)
            # Also enforce the public vocabulary at serialization. CONTAINS
            # remains stored internally; it is not renamed to another relation.
            for edge, s in rows if edge.kind in requested
        ])


@router.post("/recs/{rec_id}/feedback", response_model=FeedbackResponse)
def submit_feedback(rec_id: PathID, payload: FeedbackRequest) -> FeedbackResponse:
    return FeedbackResponse(status="ok", id=rec_id, action=payload.action)
