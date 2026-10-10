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