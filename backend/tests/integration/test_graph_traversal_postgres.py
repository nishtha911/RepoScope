"""Real CTE vs loaded NetworkX parity in an isolated PostgreSQL schema."""
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from reposcope.graph.networkx_loader import load_repository_graph, reverse_reachability_networkx
from reposcope.graph.traversal import reverse_reachability_sql
from reposcope.graph.traversal_types import TraversalBudgetExceeded


@pytest.fixture
def db():
    url = os.getenv("TEST_GRAPH_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_GRAPH_DATABASE_URL to a disposable PostgreSQL database")
    engine = create_engine(url)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("TEST_GRAPH_DATABASE_URL must be PostgreSQL")
    connection = engine.connect()
    outer = connection.begin()
    session = None
    try:
        schema = "traversal_test_" + uuid4().hex
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        statements = [
            "CREATE TABLE repositories(id integer PRIMARY KEY)",
            "CREATE TABLE files(id integer PRIMARY KEY, repository_id integer REFERENCES repositories(id), path text)",
            "CREATE TABLE symbols(id integer PRIMARY KEY, file_id integer REFERENCES files(id), name text, qualname text, kind text)",
            "CREATE TABLE edges(id integer PRIMARY KEY, source_symbol_id integer REFERENCES symbols(id), target_symbol_id integer REFERENCES symbols(id), kind text, confidence double precision)",
            "CREATE INDEX ix_traversal_test_target ON edges(target_symbol_id)",
            "INSERT INTO repositories VALUES(1),(2)",
            "INSERT INTO files VALUES(1,1,'app.py'),(2,2,'other.py')",
        ]
        for statement in statements:
            connection.execute(text(statement))
        for node in range(1, 13):
            connection.execute(text("INSERT INTO symbols VALUES(:id,1,:name,:name,'function')"),
                               {"id": node, "name": f"f{node}"})
        connection.execute(text("INSERT INTO symbols VALUES(99,2,'foreign','foreign','function')"))
        edges = [
            (1,2,1,"CALLS",.2), (2,3,1,"CALLS",1), (3,2,3,"CALLS",1),
            (4,4,2,"CALLS",.5), (5,5,4,"CALLS",1), (6,6,5,"CALLS",1),
            (7,7,6,"CALLS",1), (8,1,3,"CALLS",1), (9,3,1,"INHERITS",.5),
            (10,99,1,"CALLS",1), (11,8,1,"CALLS",None), (12,9,1,"CALLS",1.5),
            (13,10,1,"CALLS",0), (14,1,11,"CALLS",1), (15,11,1,"IMPORTS",1),
        ]
        for edge_id, source, target, kind, confidence in edges:
            connection.execute(text("INSERT INTO edges VALUES(:id,:source,:target,:kind,:confidence)"),
                               dict(id=edge_id,source=source,target=target,kind=kind,confidence=confidence))
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        yield session
    finally:
        if session is not None:
            session.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
        engine.dispose()


def assert_same(sql, python):
    assert sql.repository_id == python.repository_id
    assert sql.root_symbol_id == python.root_symbol_id
    assert sql.skipped_confidence_edges == python.skipped_confidence_edges
    assert [h.symbol_id for h in sql.hits] == [h.symbol_id for h in python.hits]
    for left, right in zip(sql.hits, python.hits):
        assert left.score == pytest.approx(right.score, abs=1e-12)
        assert left.depth == right.depth
        assert left.min_depth == right.min_depth
        assert left.symbol_path == right.symbol_path
        assert left.edge_path == right.edge_path
        assert (left.name, left.qualname, left.kind, left.file_path) == (right.name, right.qualname, right.kind, right.file_path)


@pytest.mark.parametrize("depth", [1,2,3,4])
def test_postgres_networkx_parity(db, depth):
    graph = load_repository_graph(db, 1)
    sql = reverse_reachability_sql(db, 1, 1, max_depth=depth)
    python = reverse_reachability_networkx(graph, 1, 1, max_depth=depth)
    assert_same(sql, python)
    assert 99 not in graph
    assert all(h.symbol_id not in {1,8,9,11} for h in sql.hits)
    assert sql.skipped_confidence_edges == 2


def test_best_score_and_shortest_depth_are_distinct(db):
    found = {h.symbol_id:h for h in reverse_reachability_sql(db,1,1).hits}
    assert found[2].score == pytest.approx(.8)
    assert found[2].depth == 2 and found[2].min_depth == 1
    assert found[6].score == pytest.approx(.0512)
    assert 7 not in found


def test_filtered_kinds_match(db):
    graph = load_repository_graph(db,1)
    sql = reverse_reachability_sql(db,1,1,kinds=("IMPORTS",))
    python = reverse_reachability_networkx(graph,1,1,kinds=("IMPORTS",))
    assert_same(sql,python)
    assert [h.symbol_id for h in sql.hits] == [11]


def test_foreign_or_missing_root_rejected(db):
    for root in (99,999):
        with pytest.raises(ValueError):
            reverse_reachability_sql(db,1,root)
    assert db.scalar(text("SELECT 1")) == 1


def test_empty_neighborhood_and_timeout_setting_restored(db):
    previous = db.scalar(text("SELECT current_setting('statement_timeout')"))
    result = reverse_reachability_sql(db,1,12,timeout_ms=1000)
    assert result.hits == ()
    assert db.scalar(text("SELECT current_setting('statement_timeout')")) == previous


def test_result_budget_leaves_session_usable(db):
    previous = db.scalar(text("SELECT current_setting('statement_timeout')"))
    with pytest.raises(TraversalBudgetExceeded):
        reverse_reachability_sql(db,1,1,max_results=1)
    assert db.scalar(text("SELECT current_setting('statement_timeout')")) == previous
    assert db.scalar(text("SELECT 1")) == 1


def test_loader_size_budgets(db):
    with pytest.raises(TraversalBudgetExceeded):
        load_repository_graph(db,1,max_nodes=1)
    with pytest.raises(TraversalBudgetExceeded):
        load_repository_graph(db,1,max_edges=1)
