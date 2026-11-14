"""Adapt existing retrieval modes to the public search response.

No provider call or database configuration is performed at import time.
Search does not expand the graph or synthesize an answer.
"""
from sqlalchemy import select

from reposcope.contracts.api import SearchHit, SearchResponse
from reposcope.models import File, Repository, RepositorySnapshot, Symbol
from reposcope.retrieval import pipeline
from reposcope.retrieval.gemini_embeddings import INDEX_VERSION
from reposcope.retrieval.lexical import search_chunks_by_lexical
from reposcope.retrieval.vector import EmbeddingIndexMismatchError, search_chunks_by_vector


class SearchNotFoundError(RuntimeError):
    pass


class SearchNotReadyError(RuntimeError):
    pass


class SearchResultError(RuntimeError):
    pass


def run_repository_search(session, *, repo_id, query, mode="hybrid", limit=10):
    """Read-only search with explicit mode and snapshot/metadata checks.

    Hybrid scores are reciprocal-rank-fusion scores. Lexical scores come from
    PostgreSQL text rank. Vector-only scores are 1/(60+rank), because the
    existing vector retriever exposes ordered chunks, not cosine distances.
    None is a probability; scores are not comparable between modes.
    """
    query = pipeline.validate_search_inputs(repo_id, query, limit)
    if mode not in {"hybrid", "lexical", "vector"}:
        raise ValueError("Unsupported search mode")
    if session.get(Repository, repo_id) is None:
        raise SearchNotFoundError("Repository was not found")
    snapshot = session.scalar(select(RepositorySnapshot)
        .where(RepositorySnapshot.repository_id == repo_id)
        .order_by(RepositorySnapshot.created_at.desc(), RepositorySnapshot.id.desc()).limit(1))
    if snapshot is None or snapshot.status != "ready":
        raise SearchNotReadyError("Repository index is not ready")
    if mode != "lexical" and snapshot.index_version != INDEX_VERSION:
        raise EmbeddingIndexMismatchError(
            "This index uses another embedding policy; use lexical search or explicitly migrate it")
    if not query:
        return SearchResponse(query=query, hits=[])
    if mode == "hybrid":
        hits = pipeline.search_chunks_hybrid(session, repo_id=repo_id, query=query,
                                            limit=limit, candidate_limit=max(30, limit))
        ranked = [(hit.symbol_id, hit.repo_id, hit.text, float(hit.score)) for hit in hits]
    elif mode == "lexical":
        hits = search_chunks_by_lexical(session, repo_id=repo_id, query=query, limit=limit)
        ranked = [(hit.symbol_id, hit.repo_id, hit.text, float(hit.score)) for hit in hits]
    else:
        hits = search_chunks_by_vector(session, repo_id=repo_id, query=query, limit=limit)
        ranked = [(hit.symbol_id, hit.repo_id, hit.text, 1.0 / (60 + rank))
                  for rank, hit in enumerate(hits, start=1)]
    if not ranked:
        return SearchResponse(query=query, hits=[])
    if len(ranked) > limit or any(candidate_repo != repo_id for _, candidate_repo, _, _ in ranked):
        raise SearchResultError("Retrieval returned invalid repository scope or result count")
    symbol_ids = {symbol_id for symbol_id, _, _, _ in ranked}
    rows = session.execute(select(Symbol, File.path).join(File, Symbol.file_id == File.id)
        .where(File.repository_id == repo_id, File.snapshot_id == snapshot.id,
               Symbol.id.in_(symbol_ids))).all()
    metadata = {symbol.id: (symbol, path) for symbol, path in rows}
    if set(metadata) != symbol_ids or len(rows) != len(metadata):
        raise SearchResultError("Indexed search metadata is inconsistent with its snapshot")
    response_hits = []
    for symbol_id, _, text, score in ranked:
        symbol, path = metadata[symbol_id]
        response_hits.append(SearchHit(symbol_id=symbol_id, name=symbol.qualname or symbol.name,
            score=score, file_path=path, snippet=text[:600]))
    return SearchResponse(query=query, hits=response_hits)
