"""Vector retrieval and chunk embedding persistence."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from reposcope.models.chunk import Chunk
from reposcope.models.file import File
from reposcope.models.symbol import Symbol


def search_chunks_by_vector(
    session: Session,
    repo_id: int,
    query: str,
    limit: int = 10,
) -> list[Chunk]:
    """Retrieve embedded chunks by ascending cosine distance.

    Repository scope is checked on both the chunk and its owning file.

    Chunks without embeddings are excluded. Chunk ID provides a
    deterministic tie-breaker for equal distances.

    This function does not commit or silently suppress failures.
    """
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

    query = query.strip()

    if not query:
        return []

    if session.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Vector retrieval requires PostgreSQL")

    # Keep embedding imports out of module-level initialization.
    from reposcope.retrieval.embeddings import embed_query

    query_vector = embed_query(query)

    statement = (
        select(Chunk)
        .join(Symbol, Symbol.id == Chunk.symbol_id)
        .join(File, File.id == Symbol.file_id)
        .where(
            Chunk.repo_id == repo_id,
            File.repository_id == repo_id,
            Chunk.embedding.is_not(None),
        )
        .order_by(
            Chunk.embedding.cosine_distance(query_vector),
            Chunk.id.asc(),
        )
        .limit(limit)
    )

    return list(session.scalars(statement))


def bulk_insert_chunks(
    session: Session,
    repo_id: int,
    chunk_drafts: list,
    symbol_key_to_id: dict[str, int],
) -> None:
    """Embed and insert chunk drafts.

    Preserves the existing insertion behavior:
    - Empty input returns without embedding.
    - Drafts without a mapped symbol ID are skipped.
    - The session is committed after insertion.
    """
    if not chunk_drafts:
        return

    from reposcope.retrieval.embeddings import embed_texts

    texts = [draft.text for draft in chunk_drafts]
    embeddings = embed_texts(texts)

    db_chunks = []

    for draft, embedding in zip(chunk_drafts, embeddings):
        symbol_id = symbol_key_to_id.get(draft.symbol_key)

        if symbol_id is None:
            continue

        db_chunks.append(
            Chunk(
                symbol_id=symbol_id,
                repo_id=repo_id,
                text=draft.text,
                embedding=embedding,
            )
        )

    session.add_all(db_chunks)
    session.commit()