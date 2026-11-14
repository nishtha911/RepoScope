"""Version-fenced vector retrieval and legacy chunk persistence."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from reposcope.models.chunk import Chunk
from reposcope.models.file import File
from reposcope.models.symbol import Symbol
from reposcope.models import RepositorySnapshot
from reposcope.retrieval.gemini_embeddings import INDEX_VERSION


class EmbeddingIndexMismatchError(RuntimeError):
    """Indexed files are not a single ready snapshot for this embedding policy."""


def _compatible_snapshot_id(session: Session, repo_id: int) -> int | None:
    # Check actual file ownership rather than merely selecting the latest
    # snapshot: old, mixed, or snapshot-less file data must fail closed.
    statement = (
        select(File.snapshot_id, RepositorySnapshot.index_version, RepositorySnapshot.status)
        .select_from(File)
        .outerjoin(RepositorySnapshot,
            (RepositorySnapshot.id == File.snapshot_id)
            & (RepositorySnapshot.repository_id == File.repository_id))
        .where(File.repository_id == repo_id)
        .distinct()
    )
    rows = session.execute(statement).all()
    if not rows:
        return None
    if len(rows) != 1:
        raise EmbeddingIndexMismatchError("Repository has mixed snapshot data; explicit migration is required")
    snapshot_id, version, state = rows[0]
    if (type(snapshot_id) is not int or snapshot_id <= 0
            or version != INDEX_VERSION or state != "ready"):
        raise EmbeddingIndexMismatchError(
            "Repository index is incompatible with Gemini embeddings; explicit migration is required")
    return snapshot_id


def search_chunks_by_vector(session: Session, repo_id: int, query: str,
                            limit: int = 10) -> list[Chunk]:
    """Validate snapshot identity before provider use; never commit or hide errors."""
    if isinstance(repo_id, bool) or not isinstance(repo_id, int) or repo_id < 1:
        raise ValueError("repo_id must be a positive integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer from 1 to 100")
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if len(query) > 4096:
        raise ValueError("query must contain at most 4096 characters")
    query = query.strip()
    if not query:
        return []
    if session.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Vector retrieval requires PostgreSQL")
    snapshot_id = _compatible_snapshot_id(session, repo_id)
    if snapshot_id is None:
        return []
    from reposcope.retrieval.embeddings import embed_query
    query_vector = embed_query(query)
    statement = (
        select(Chunk)
        .join(Symbol, Symbol.id == Chunk.symbol_id)
        .join(File, File.id == Symbol.file_id)
        .where(Chunk.repo_id == repo_id, File.repository_id == repo_id,
               File.snapshot_id == snapshot_id, Chunk.embedding.is_not(None))
        .order_by(Chunk.embedding.cosine_distance(query_vector), Chunk.id.asc())
        .limit(limit)
    )
    return list(session.scalars(statement))


def bulk_insert_chunks(session: Session, repo_id: int, chunk_drafts: list,
                       symbol_key_to_id: dict[str, int]) -> None:
    """Legacy writer, fenced against incompatible or missing snapshot identity.

    New ingestion must use publish_prepared_index for atomic, leased writes.
    Retains the legacy commit behavior only for a compatible ready snapshot;
    empty input remains a no-op. Never append Gemini vectors to a BGE index.
    """
    if not chunk_drafts:
        return
    if _compatible_snapshot_id(session, repo_id) is None:
        raise EmbeddingIndexMismatchError("Use the atomic publisher to create a new Gemini snapshot")
    from reposcope.retrieval.embeddings import embed_texts
    texts = [draft.text for draft in chunk_drafts]
    embeddings = embed_texts(texts)
    db_chunks = []
    for draft, embedding in zip(chunk_drafts, embeddings):
        symbol_id = symbol_key_to_id.get(draft.symbol_key)
        if symbol_id is None:
            continue
        db_chunks.append(Chunk(symbol_id=symbol_id, repo_id=repo_id,
                               text=draft.text, embedding=embedding))
    session.add_all(db_chunks)
    session.commit()
