"""Baseline B0: fixed-size chunks ranked by embedding similarity only."""

from __future__ import annotations

from dataclasses import dataclass
from math import fsum, sqrt
from os import PathLike
from typing import Callable, Iterable, Sequence


DEFAULT_CHUNK_SIZE = 512
Embedding = Sequence[float]
EmbedTexts = Callable[[list[str]], list[Embedding]]
EmbedQuery = Callable[[str], Embedding]


@dataclass(frozen=True)
class BaselineChunk:
    """A fixed-size source chunk with its vector."""

    chunk_id: int
    source: str
    start: int
    end: int
    text: str
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class BaselineHit:
    chunk: BaselineChunk
    score: float


@dataclass(frozen=True)
class BaselineIndex:
    chunks: tuple[BaselineChunk, ...]

    def search(self, query_embedding: Embedding, limit: int = 10) -> list[BaselineHit]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100")
        query = _normalise_vector(query_embedding)
        hits = [
            BaselineHit(chunk=chunk, score=_cosine_similarity(query, chunk.embedding))
            for chunk in self.chunks
        ]
        hits.sort(key=lambda hit: (-hit.score, hit.chunk.chunk_id))
        return hits[:limit]


def fixed_size_chunks(
    source: str,
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[tuple[int, int, str]]:
    """Split text into non-overlapping character ranges."""
    if not isinstance(source, str) or not source:
        raise ValueError("source must be a non-empty string")
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size < 1:
        raise ValueError("chunk_size must be a positive integer")
    return [
        (start, min(start + chunk_size, len(text)), text[start:start + chunk_size])
        for start in range(0, len(text), chunk_size)
    ]


def build_baseline_index(
    documents: Iterable[tuple[str | PathLike[str], str]],
    *,
    embed_texts: EmbedTexts | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> BaselineIndex:
    """Build B0 from ``(source, text)`` documents using embeddings only."""
    if embed_texts is None:
        from reposcope.retrieval.embeddings import embed_texts as default_embed_texts

        embed_texts = default_embed_texts

    chunks: list[tuple[str, int, int, str]] = []
    for source, text in documents:
        source_name = str(source)
        for start, end, chunk_text in fixed_size_chunks(
            source_name, text, chunk_size=chunk_size
        ):
            chunks.append((source_name, start, end, chunk_text))

    if not chunks:
        return BaselineIndex(chunks=())

    embeddings = embed_texts([chunk[3] for chunk in chunks])
    if len(embeddings) != len(chunks):
        raise ValueError("embed_texts must return one vector per chunk")

    indexed = []
    for chunk_id, ((source, start, end, text), embedding) in enumerate(
        zip(chunks, embeddings), start=1
    ):
        indexed.append(
            BaselineChunk(
                chunk_id=chunk_id,
                source=source,
                start=start,
                end=end,
                text=text,
                embedding=_normalise_vector(embedding),
            )
        )
    return BaselineIndex(chunks=tuple(indexed))


def search_baseline(
    index: BaselineIndex,
    query: str,
    *,
    embed_query: EmbedQuery | None = None,
    limit: int = 10,
) -> list[BaselineHit]:
    """Retrieve B0 results without lexical matching, fusion, or graph expansion."""
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    query = query.strip()
    if not query:
        return []
    if embed_query is None:
        from reposcope.retrieval.embeddings import embed_query as default_embed_query

        embed_query = default_embed_query
    return index.search(embed_query(query), limit=limit)


def recall_at_k(
    index: BaselineIndex,
    cases: Iterable[tuple[str, set[int]]],
    *,
    embed_query: EmbedQuery,
    k: int = 10,
) -> float:
    """Calculate mean chunk-id recall for labelled queries."""
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("k must be a positive integer")
    recalls = []
    for query, relevant_ids in cases:
        relevant = set(relevant_ids)
        if not relevant:
            continue
        returned = {hit.chunk.chunk_id for hit in index.search(embed_query(query), limit=k)}
        recalls.append(len(returned & relevant) / len(relevant))
    return fsum(recalls) / len(recalls) if recalls else 0.0


def _normalise_vector(vector: Embedding) -> tuple[float, ...]:
    values = tuple(float(value) for value in vector)
    if not values or sqrt(fsum(value * value for value in values)) == 0:
        raise ValueError("embedding vectors must be non-empty and non-zero")
    return values


def _cosine_similarity(left: Embedding, right: Embedding) -> float:
    if len(left) != len(right):
        raise ValueError("embedding vectors must have matching dimensions")
    left_norm = sqrt(fsum(value * value for value in left))
    right_norm = sqrt(fsum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("embedding vectors must be non-zero")
    return fsum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
