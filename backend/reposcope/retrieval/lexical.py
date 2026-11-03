"""Identifier-aware PostgreSQL full-text retrieval over existing code chunks.

No embeddings, LLM calls, implicit commits, or database configuration imports.
Requires the lexical Alembic migration. Query and document normalization both
use the same PostgreSQL function; the Python helper supports tests/tooling.
"""
import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session


def normalize_identifier_text(value: str) -> str:
    """Split ASCII snake/camel/Pascal/acronym/digit boundaries."""
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    value = re.sub(r"([A-Za-z])([0-9])", r"\1 \2", value)
    value = re.sub(r"([0-9])([A-Za-z])", r"\1 \2", value)
    value = re.sub(r"[^A-Za-z0-9]+", " ", value)
    return value.lower().strip()


@dataclass(frozen=True)
class LexicalHit:
    chunk_id: int
    symbol_id: int
    repo_id: int
    text: str
    name: str
    qualname: str | None
    file_path: str
    start_line: int
    end_line: int
    score: float


_SEARCH_SQL = text("""
WITH query AS (
    SELECT plainto_tsquery(
        'pg_catalog.simple'::regconfig,
        reposcope_identifier_text(:query)
    ) AS value
)
SELECT c.id AS chunk_id, c.symbol_id, c.repo_id, c.text,
       s.name, s.qualname, f.path AS file_path,
       s.start_line, s.end_line,
       ts_rank_cd(c.search_vector, query.value, 32) AS score
FROM chunks AS c
JOIN symbols AS s ON s.id = c.symbol_id
JOIN files AS f ON f.id = s.file_id
CROSS JOIN query
WHERE c.repo_id = :repo_id
  AND f.repository_id = :repo_id
  AND c.search_vector @@ query.value
ORDER BY score DESC, c.id ASC
LIMIT :limit
""")


def search_chunks_by_lexical(
    session: Session, repo_id: int, query: str, limit: int = 10,
) -> list[LexicalHit]:
    """AND-token search. Ranked scores are not probabilities.

    No prefix/fuzzy matching or SQL-query operators are accepted. Repository
    scope is checked on both the chunk and its symbol's owning file.
    """
    if isinstance(repo_id, bool) or not isinstance(repo_id, int) or repo_id < 1:
        raise ValueError("repo_id must be a positive integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer from 1 to 100")
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if len(query) > 4096:
        raise ValueError("query must contain at most 4096 characters")
    if not normalize_identifier_text(query):
        return []
    if session.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Lexical retrieval requires PostgreSQL; SQLite is not an FTS substitute")
    rows = session.execute(_SEARCH_SQL, {
        "repo_id": repo_id, "query": query, "limit": limit,
    }).mappings().all()
    return [LexicalHit(**dict(row)) for row in rows]
