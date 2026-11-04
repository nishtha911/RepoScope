"""Real graph loading/context hydration; hybrid ranking is stubbed explicitly.

Uses minimal schema-compatible tables, not full Alembic or embedding execution.
Only use a development/test database: this fixture creates a temporary schema.
"""
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from reposcope.graph.networkx_loader import load_repository_graph
from reposcope.retrieval.graph_expand import expand_graph
from reposcope.retrieval import expanded_pipeline


def hit(symbol_id, chunk_id=None):
    return SimpleNamespace(
        symbol_id=symbol_id,
        chunk_id=chunk_id or symbol_id,
        repo_id=1,
        score=1.0,
        text=f"seed code {symbol_id}",
    )


@pytest.fixture
def db():
    project_root = Path(__file__).resolve().parents[3]
    load_dotenv(project_root / ".env", override=False)

    url = (
        os.getenv("TEST_GRAPH_EXPANSION_DATABASE_URL")
        or os.getenv("DATABASE_URL")
    )
    if not url:
        pytest.skip(
            "Set TEST_GRAPH_EXPANSION_DATABASE_URL or DATABASE_URL "
            "to a development/test PostgreSQL database"
        )

    engine = create_engine(url)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("Expected PostgreSQL")
    connection = engine.connect()
    transaction = connection.begin()
    session = None
    try:
        schema = "expansion_test_" + uuid4().hex
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        for ddl in (
            "CREATE TABLE repositories(id integer PRIMARY KEY)",
            "CREATE TABLE files(id integer PRIMARY KEY,repository_id integer REFERENCES repositories(id),path text)",
            "CREATE TABLE symbols(id integer PRIMARY KEY,file_id integer REFERENCES files(id),name text,qualname text,kind text)",
            "CREATE TABLE edges(id integer PRIMARY KEY,source_symbol_id integer REFERENCES symbols(id),target_symbol_id integer REFERENCES symbols(id),kind text,confidence double precision)",
            "CREATE TABLE chunks(id integer PRIMARY KEY,symbol_id integer REFERENCES symbols(id),repo_id integer REFERENCES repositories(id),text text)",
            "INSERT INTO repositories VALUES(1),(2)",
            "INSERT INTO files VALUES(1,1,'app.py'),(2,2,'foreign.py')",
        ):
            connection.execute(text(ddl))
        nodes = [
            (1, "app", "module"),
            (2, "GET /users", "endpoint"),
            (3, "handler", "function"),
            (4, "service", "function"),
            (5, "helper", "function"),
            (6, "Base", "class"),
            (7, "Child", "class"),
            (8, "UserModel", "class"),
        ]
        for node, name, kind in nodes:
            connection.execute(
                text("INSERT INTO symbols VALUES(:id,1,:name,:name,:kind)"),
                dict(id=node, name=name, kind=kind),
            )
        connection.execute(
            text("INSERT INTO symbols VALUES(99,2,'foreign','foreign','function')")
        )
        edges = [
            (1, 1, 2, "EXPOSES"),
            (2, 2, 3, "CALLS"),
            (3, 3, 4, "CALLS"),
            (4, 4, 5, "CALLS"),
            (5, 7, 6, "INHERITS"),
            (6, 4, 8, "USES"),
            (7, 99, 4, "CALLS"),
        ]
        for edge_id, source, target, kind in edges:
            connection.execute(
                text("INSERT INTO edges VALUES(:id,:source,:target,:kind,1.0)"),
                dict(id=edge_id, source=source, target=target, kind=kind),
            )
        for symbol in (3, 4, 5, 8):
            connection.execute(
                text("INSERT INTO chunks VALUES(:id,:symbol,1,:body)"),
                dict(id=symbol * 10, symbol=symbol, body=f"stored body {symbol}"),
            )
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        yield session
    finally:
        if session is not None:
            session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.mark.parametrize("seed,expected", [(4, {2, 3}), (3, {1, 2}), (1, {2, 3})])
def test_endpoint_expansion_from_loaded_graph(db, seed, expected):
    graph = load_repository_graph(db, 1)
    result = expand_graph(graph, 1, [hit(seed)], intent="endpoints")
    assert {symbol.symbol_id for symbol in result.symbols} == expected
    assert all(symbol.depth <= 2 for symbol in result.symbols)
    assert not result.gaps
    assert 99 not in graph


def test_incoming_outgoing_and_model_relationships(db):
    graph = load_repository_graph(db, 1)
    callers = expand_graph(graph, 1, [hit(4)], intent="callers")
    dependencies = expand_graph(graph, 1, [hit(4)], intent="implementation")
    assert {s.symbol_id for s in callers.symbols} == {2, 3}
    assert {s.symbol_id for s in dependencies.symbols} == {5, 8}


def test_parent_class_expansion(db):
    graph = load_repository_graph(db, 1)
    result = expand_graph(graph, 1, [hit(7)], intent="inheritance")
    assert [s.symbol_id for s in result.symbols] == [6]
    assert result.symbols[0].paths[0].edge_ids == (5,)


def test_wrapper_uses_real_loader_and_context_queries(db, monkeypatch):
    original = [hit(4, 40)]
    monkeypatch.setattr(
        expanded_pipeline, "_hybrid_search", lambda *args, **kwargs: original
    )
    result = expanded_pipeline.search_chunks_hybrid_expanded(
        db, 1, "users", intent="endpoints"
    )
    assert result.hybrid_hits == tuple(original)
    assert [(c.symbol_id, c.is_seed) for c in result.context_chunks] == [
        (4, True), (3, False)
    ]
    assert result.context_chunks[1].text == "stored body 3"
    assert any(
        "symbol 2" in gap and "metadata only" in gap
        for gap in result.expansion.gaps
    )


def test_context_query_rejects_corrupt_chunk_repository(db, monkeypatch):
    db.execute(text("UPDATE chunks SET repo_id=2 WHERE symbol_id=5"))
    monkeypatch.setattr(
        expanded_pipeline, "_hybrid_search", lambda *args, **kwargs: [hit(4, 40)]
    )
    result = expanded_pipeline.search_chunks_hybrid_expanded(
        db, 1, "users", intent="implementation"
    )
    assert {c.symbol_id for c in result.context_chunks} == {4, 8}
    assert any("symbol 5" in gap for gap in result.expansion.gaps)


def test_bad_confidence_is_not_assumed_exact(db):
    db.execute(text("UPDATE edges SET confidence=NULL WHERE id=3"))
    result = expand_graph(load_repository_graph(db, 1), 1, [hit(4)], intent="callers")
    assert not result.symbols
    assert any("Edge 3" in gap for gap in result.gaps)
