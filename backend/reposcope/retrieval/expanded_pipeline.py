"""Additive hybrid-search -> graph-expansion orchestration.

Existing search_chunks_hybrid and loader remain unchanged. Database queries and
retriever failures propagate. Use a clean, consistent read transaction when
indexing may run concurrently. No implicit commit, model downloads on import,
or environment configuration imports are introduced by this module.
"""
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from reposcope.retrieval.graph_expand import (
    ExpansionIntent, GraphExpansionResult, _integer, expand_graph,
)

if TYPE_CHECKING:
    from reposcope.retrieval.pipeline import HybridHit


@dataclass(frozen=True)
class ContextChunk:
    chunk_id: int
    symbol_id: int
    repo_id: int
    text: str
    is_seed: bool


@dataclass(frozen=True)
class ExpandedRetrievalResult:
    hybrid_hits: tuple["HybridHit", ...]
    expansion: GraphExpansionResult
    context_chunks: tuple[ContextChunk, ...]


def _hybrid_search(session, **kwargs):
    from reposcope.retrieval.pipeline import search_chunks_hybrid
    return search_chunks_hybrid(session, **kwargs)


def _load_graph(session, repository_id):
    from reposcope.graph.networkx_loader import load_repository_graph
    return load_repository_graph(session, repository_id)


def _fetch_chunks(session, repository_id, symbol_ids):
    if not symbol_ids:
        return []
    from sqlalchemy import bindparam, text
    statement = text("""
        SELECT c.id AS chunk_id, c.symbol_id, c.repo_id, c.text
        FROM chunks c JOIN symbols s ON s.id=c.symbol_id
        JOIN files f ON f.id=s.file_id
        WHERE c.repo_id=:repo_id AND f.repository_id=:repo_id
          AND c.symbol_id IN :symbol_ids
        ORDER BY c.symbol_id, c.id
    """).bindparams(bindparam("symbol_ids", expanding=True))
    return list(session.execute(statement, {"repo_id": repository_id,
                                           "symbol_ids": list(symbol_ids)}).mappings())


def search_chunks_hybrid_expanded(
    session, repo_id: int, query: str, limit: int = 20, *,
    intent: ExpansionIntent, candidate_limit: int = 30, k: int = 60,
    seed_limit: int = 8, max_depth: int = 2,
    max_neighbors_per_seed: int = 20, max_expanded_symbols: int = 80,
    max_expansions: int = 10_000, min_confidence: float = 0.0,
) -> ExpandedRetrievalResult:
    """Preserve original ranked hits and separately return expanded context.

    Intent is explicit. No heuristic query classifier is silently selected.
    Synthetic endpoint/module nodes may have no chunks: metadata is returned
    with an explicit gap rather than invented code. Endpoint route names remain
    declaration-local, as supplied by the framework detector.
    """
    _integer(repo_id, "repo_id")
    _integer(limit, "limit", maximum=100)
    _integer(candidate_limit, "candidate_limit", maximum=100)
    _integer(k, "k")
    if candidate_limit < limit:
        raise ValueError("candidate_limit must be at least limit")
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if len(query) > 4096:
        raise ValueError("query must contain at most 4096 characters")
    # Validate expansion options even on an empty query; no DB work needed.
    import networkx as nx
    empty = expand_graph(nx.MultiDiGraph(repository_id=repo_id), repo_id, (), intent=intent,
                         seed_limit=seed_limit, max_depth=max_depth,
                         max_neighbors_per_seed=max_neighbors_per_seed,
                         max_expanded_symbols=max_expanded_symbols,
                         max_expansions=max_expansions, min_confidence=min_confidence)
    query = query.strip()
    if not query:
        return ExpandedRetrievalResult((), empty, ())
    hits = tuple(_hybrid_search(session, repo_id=repo_id, query=query, limit=limit,
                                candidate_limit=candidate_limit, k=k))
    if not hits:
        return ExpandedRetrievalResult((), empty, ())
    graph = _load_graph(session, repo_id)
    expansion = expand_graph(graph, repo_id, hits, intent=intent, seed_limit=seed_limit,
                             max_depth=max_depth, max_neighbors_per_seed=max_neighbors_per_seed,
                             max_expanded_symbols=max_expanded_symbols,
                             max_expansions=max_expansions, min_confidence=min_confidence)
    selected = {seed.chunk_id: seed for seed in expansion.seeds}
    chunks = {hit.chunk_id: ContextChunk(hit.chunk_id, hit.symbol_id, hit.repo_id, hit.text, True)
              for hit in hits if hit.chunk_id in selected}
    neighbor_ids = tuple(symbol.symbol_id for symbol in expansion.symbols)
    found = set()
    for row in _fetch_chunks(session, repo_id, neighbor_ids):
        if row["repo_id"] != repo_id or row["symbol_id"] not in neighbor_ids:
            raise ValueError("Context hydration returned an out-of-scope chunk")
        chunk = ContextChunk(row["chunk_id"], row["symbol_id"], row["repo_id"], row["text"], False)
        if chunk.chunk_id in chunks and chunks[chunk.chunk_id] != chunk:
            raise ValueError("Conflicting context chunk metadata")
        chunks[chunk.chunk_id] = chunk
        found.add(chunk.symbol_id)
    gaps = set(expansion.gaps)
    for symbol_id in neighbor_ids:
        if symbol_id not in found:
            gaps.add(f"Expanded symbol {symbol_id} has no stored chunk; metadata only")
    expansion = replace(expansion, gaps=tuple(sorted(gaps)))
    symbol_order = {seed.symbol_id: i for i, seed in enumerate(expansion.seeds)}
    symbol_order.update({symbol.symbol_id: len(expansion.seeds) + i
                         for i, symbol in enumerate(expansion.symbols)})
    ordered_chunks = tuple(sorted(chunks.values(), key=lambda c: (symbol_order[c.symbol_id], c.chunk_id)))
    return ExpandedRetrievalResult(hits, expansion, ordered_chunks)
