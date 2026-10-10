from sqlalchemy import select
from sqlalchemy.orm import Session
from reposcope.models.chunk import Chunk
from reposcope.retrieval.embeddings import embed_query

def search_chunks_by_vector(session: Session, repo_id: int, query: str, limit: int = 10) -> list[Chunk]:
    """Perform a vector similarity search filtered by repo_id."""
    query_vector = embed_query(query)
    
    stmt = (
        select(Chunk)
        .where(Chunk.repo_id == repo_id)
        # We must explicitly cast to string if SQLAlchemy doesn't support list directly, 
        # but pgvector.sqlalchemy Vector type handles python lists natively!
        .order_by(Chunk.embedding.cosine_distance(query_vector))
        .limit(limit)
    )
    
    return list(session.scalars(stmt))

def bulk_insert_chunks(session: Session, repo_id: int, chunk_drafts: list, symbol_key_to_id: dict[str, int]) -> None:
    """Embeds and bulk inserts chunks into the database."""
    from reposcope.retrieval.embeddings import embed_texts
    
    if not chunk_drafts:
        return
        
    texts = [draft.text for draft in chunk_drafts]
    embeddings = embed_texts(texts)
    
    db_chunks = []
    for draft, emb in zip(chunk_drafts, embeddings):
        symbol_id = symbol_key_to_id.get(draft.symbol_key)
        if symbol_id is None:
            continue
            
        db_chunks.append(
            Chunk(
                symbol_id=symbol_id,
                repo_id=repo_id,
                text=draft.text,
                embedding=emb
            )
        )
        
    session.add_all(db_chunks)
    session.commit()