"""PostgreSQL recursive-CTE bounded reverse reachability."""
from sqlalchemy import bindparam, text
from sqlalchemy.exc import DBAPIError

from reposcope.graph.traversal_types import (
    DEFAULT_KINDS, ImpactHit, ReachabilityResult, TraversalBudgetExceeded,
    positive_int, validate_options,
)

_ROOT = text("""SELECT s.id FROM symbols s JOIN files f ON f.id=s.file_id
WHERE s.id=:root_id AND f.repository_id=:repo_id""")

_SCOPED_EDGES = """
SELECT e.id, e.source_symbol_id, e.target_symbol_id, e.kind, e.confidence
FROM edges e
JOIN symbols src ON src.id=e.source_symbol_id
JOIN files sf ON sf.id=src.file_id
JOIN symbols dst ON dst.id=e.target_symbol_id
JOIN files tf ON tf.id=dst.file_id
WHERE sf.repository_id=:repo_id AND tf.repository_id=:repo_id
  AND e.kind IN :kinds
"""
_SKIPPED = text("SELECT count(*) FROM (" + _SCOPED_EDGES + """
) e WHERE e.confidence IS NULL OR NOT (e.confidence BETWEEN 0 AND 1)
""").bindparams(bindparam("kinds", expanding=True))

_CTE = text("""
WITH RECURSIVE repo_symbols AS NOT MATERIALIZED (
    SELECT s.id AS symbol_id, s.name, s.qualname, s.kind, f.path AS file_path
    FROM symbols s JOIN files f ON f.id=s.file_id
    WHERE f.repository_id=:repo_id
), scoped_edges AS NOT MATERIALIZED (
""" + _SCOPED_EDGES + """
), walk(symbol_id, depth, score, symbol_path, edge_path) AS (
    SELECT s.symbol_id, 0, CAST(1.0 AS numeric),
           ARRAY[s.symbol_id]::bigint[], ARRAY[]::bigint[]
    FROM repo_symbols s WHERE s.symbol_id=:root_id
    UNION ALL
    SELECT e.source_symbol_id, w.depth+1,
           w.score * CAST(e.confidence AS numeric)
             * CASE WHEN w.depth=0 THEN CAST(1.0 AS numeric) ELSE CAST(0.8 AS numeric) END,
           w.symbol_path || CAST(e.source_symbol_id AS bigint),
           w.edge_path || CAST(e.id AS bigint)
    FROM walk w JOIN scoped_edges e ON e.target_symbol_id=w.symbol_id
    WHERE w.depth < :max_depth
      AND e.confidence BETWEEN 0 AND 1
      AND NOT (e.source_symbol_id = ANY(w.symbol_path))
), paths AS (
    SELECT *, min(depth) OVER (PARTITION BY symbol_id) AS min_depth
    FROM walk WHERE depth > 0
), best AS (
    SELECT DISTINCT ON (symbol_id) * FROM paths
    ORDER BY symbol_id, score DESC, depth ASC, symbol_path ASC, edge_path ASC
)
SELECT b.symbol_id, s.name, s.qualname, s.kind, s.file_path,
       b.depth, b.min_depth, b.score, b.symbol_path, b.edge_path
FROM best b JOIN repo_symbols s ON s.symbol_id=b.symbol_id
ORDER BY b.score DESC, b.depth ASC, b.symbol_id ASC, b.symbol_path ASC, b.edge_path ASC
LIMIT :cap
""").bindparams(bindparam("kinds", expanding=True))


def reverse_reachability_sql(
    session, repository_id, root_symbol_id, *, max_depth=4,
    kinds=DEFAULT_KINDS, max_results=10000, timeout_ms=3000,
):
    """Read-only traversal; no commit and no silent partial-success response.

    A savepoint scopes statement_timeout and rolls back cancelled statements.
    Session.begin_nested() can flush pre-existing pending ORM writes; use a clean
    read session. Use REPEATABLE READ for one snapshot across metadata/CTE reads.
    """
    kinds = validate_options(repository_id, root_symbol_id, max_depth, kinds, max_results)
    positive_int(timeout_ms, "timeout_ms", 60000)
    if session.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Recursive SQL traversal requires PostgreSQL")
    params = {"repo_id": repository_id, "root_id": root_symbol_id,
              "max_depth": max_depth, "kinds": kinds, "cap": max_results + 1}
    try:
        with session.begin_nested():
            previous = session.scalar(text("SELECT current_setting('statement_timeout')"))
            session.execute(text("SELECT set_config('statement_timeout', :value, true)"),
                            {"value": f"{timeout_ms}ms"})
            if session.scalar(_ROOT, params) is None:
                raise ValueError("Root symbol does not belong to the repository")
            skipped = int(session.scalar(_SKIPPED, params))
            rows = session.execute(_CTE, params).mappings().all()
            if len(rows) > max_results:
                raise TraversalBudgetExceeded("Reverse traversal exceeds max_results")
            hits = tuple(ImpactHit(
                symbol_id=r["symbol_id"], name=r["name"], qualname=r["qualname"],
                kind=r["kind"], file_path=r["file_path"], depth=r["depth"],
                min_depth=r["min_depth"], score=float(r["score"]),
                symbol_path=tuple(r["symbol_path"]), edge_path=tuple(r["edge_path"]),
            ) for r in rows)
            session.execute(text("SELECT set_config('statement_timeout', :value, true)"),
                            {"value": previous})
        return ReachabilityResult(repository_id, root_symbol_id, max_depth, hits, skipped)
    except DBAPIError as exc:
        code = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
        if code == "57014":
            raise TraversalBudgetExceeded("SQL traversal cancelled or exceeded statement timeout") from exc
        raise
