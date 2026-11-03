"""Exact-symbol search and hybrid reciprocal rank fusion.

No database configuration imports, implicit commits, or model downloads
at module import time.

Hybrid retrieval requires the real lexical and vector retrievers.
Retriever failures propagate rather than silently falling back to
fixture data or incomplete results.
"""

from dataclasses import dataclass

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from reposcope.models.chunk import Chunk
from reposcope.models.file import File
from reposcope.models.symbol import Symbol
from reposcope.retrieval.fusion import reciprocal_rank_fusion
from reposcope.retrieval.lexical import search_chunks_by_lexical


@dataclass(frozen=True)
class HybridHit:
    """A chunk with its fused rank score, not a probability."""

    chunk_id: int
    symbol_id: int
    repo_id: int
    text: str
    score: float


def validate_search_inputs(
    repo_id: int,
    query: str,
    limit: int,
) -> str:
    """Validate inputs and return a trimmed query."""
    if (
        isinstance(repo_id, bool)
        or not isinstance(repo_id, int)
        or repo_id < 1
    ):
        raise ValueError("repo_id must be a positive integer")

    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= 100
    ):
        raise ValueError("limit must be an integer from 1 to 100")

    if not isinstance(query, str):
        raise TypeError("query must be a string")

    if len(query) > 4096:
        raise ValueError("query must contain at most 4096 characters")

    return query.strip()


def search_chunks_by_exact(
    session: Session,
    repo_id: int,
    query: str,
    limit: int = 10,
) -> list[Chunk]:
    """Return chunks whose symbol name or qualname matches exactly.

    Matching is case-sensitive and does not perform substring,
    prefix, fuzzy, or identifier-token matching.

    Qualified-name matches rank before simple-name-only matches.
    Chunk ID provides deterministic ordering within either group.

    Both chunk scope and the owning file's repository are checked.
    """
    query = validate_search_inputs(repo_id, query, limit)

    if not query:
        return []

    statement = (
        select(Chunk)
        .join(Symbol, Symbol.id == Chunk.symbol_id)
        .join(File, File.id == Symbol.file_id)
        .where(
            Chunk.repo_id == repo_id,
            File.repository_id == repo_id,
            or_(
                Symbol.name == query,
                Symbol.qualname == query,
            ),
        )
        .order_by(
            case(
                (Symbol.qualname == query, 0),
                else_=1,
            ),
            Chunk.id.asc(),
        )
        .limit(limit)
    )

    return list(session.scalars(statement))


def _search_vector_chunks(
    session: Session,
    repo_id: int,
    query: str,
    limit: int,
) -> list[Chunk]:
    """Import vector retrieval only when it is requested."""
    from reposcope.retrieval.vector import search_chunks_by_vector

    return search_chunks_by_vector(
        session,
        repo_id=repo_id,
        query=query,
        limit=limit,
    )


def search_chunks_hybrid(
    session: Session,
    repo_id: int,
    query: str,
    limit: int = 10,
    *,
    candidate_limit: int = 30,
    k: int = 60,
) -> list[HybridHit]:
    """Fuse exact, lexical, and vector chunk rankings.

    Each input ranking must be ordered best-first and use chunk IDs
    from the same repository.

    candidate_limit controls candidates fetched per retriever.
    limit controls the number of final fused hits.

    RRF uses rank positions, not raw retriever scores.

    This function does not commit, expand the graph, generate an
    answer, or suppress retriever failures.
    """
    query = validate_search_inputs(repo_id, query, limit)

    validate_search_inputs(repo_id, query, candidate_limit)

    if candidate_limit < limit:
        raise ValueError("candidate_limit must be at least limit")

    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("k must be a positive integer")

    if not query:
        return []

    exact_hits = search_chunks_by_exact(
        session,
        repo_id=repo_id,
        query=query,
        limit=candidate_limit,
    )

    lexical_hits = search_chunks_by_lexical(
        session,
        repo_id=repo_id,
        query=query,
        limit=candidate_limit,
    )

    vector_hits = _search_vector_chunks(
        session,
        repo_id=repo_id,
        query=query,
        limit=candidate_limit,
    )

    candidates: dict[int, tuple[int, int, str]] = {}

    def remember(
        chunk_id: int,
        symbol_id: int,
        candidate_repo_id: int,
        text: str,
    ) -> None:
        if candidate_repo_id != repo_id:
            raise ValueError(
                "retriever returned a chunk from another repository"
            )

        payload = (symbol_id, candidate_repo_id, text)

        if (
            chunk_id in candidates
            and candidates[chunk_id] != payload
        ):
            raise ValueError(
                "retrievers returned inconsistent metadata for a chunk"
            )

        candidates[chunk_id] = payload

    for chunk in exact_hits:
        remember(
            chunk.id,
            chunk.symbol_id,
            chunk.repo_id,
            chunk.text,
        )

    for hit in lexical_hits:
        remember(
            hit.chunk_id,
            hit.symbol_id,
            hit.repo_id,
            hit.text,
        )

    for chunk in vector_hits:
        remember(
            chunk.id,
            chunk.symbol_id,
            chunk.repo_id,
            chunk.text,
        )

    fused_hits = reciprocal_rank_fusion(
        [
            [chunk.id for chunk in exact_hits],
            [hit.chunk_id for hit in lexical_hits],
            [chunk.id for chunk in vector_hits],
        ],
        k=k,
        limit=limit,
    )

    results: list[HybridHit] = []

    for hit in fused_hits:
        symbol_id, candidate_repo_id, text = candidates[hit.chunk_id]

        results.append(
            HybridHit(
                chunk_id=hit.chunk_id,
                symbol_id=symbol_id,
                repo_id=candidate_repo_id,
                text=text,
                score=hit.score,
            )
        )

    return results