import json
import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session

from reposcope.graph.builder import (
    build_graph_plan, canonical_graph, persist_graph_plan, resolution_report,
)
from reposcope.models.base import Base
from reposcope.models.edge import Edge
from reposcope.models.file import File
from reposcope.models.repository import Repository
from reposcope.models.repository_snapshot import RepositorySnapshot
from reposcope.models.symbol import Symbol
from reposcope.parsing.python_parser import parse_python

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "graph_persistence"
TABLES = [Repository.__table__, RepositorySnapshot.__table__, File.__table__,
          Symbol.__table__, Edge.__table__]


def parsed_fixture():
    sources = json.loads((FIXTURE / "sources.json").read_text(encoding="utf-8"))
    return [parse_python(source.encode("utf-8"), file_path=path)
            for path, source in sources.items()]


@pytest.fixture(params=["sqlite", "postgresql"])
def session(request):
    if request.param == "postgresql":
        url = os.getenv("TEST_GRAPH_DATABASE_URL")
        if not url:
            pytest.skip("Set TEST_GRAPH_DATABASE_URL to a disposable PostgreSQL test database")
        engine = create_engine(url)
        if engine.dialect.name != "postgresql":
            engine.dispose()
            pytest.fail("TEST_GRAPH_DATABASE_URL must be PostgreSQL")
    else:
        engine = create_engine("sqlite:///:memory:")
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
    connection = engine.connect()
    transaction = connection.begin()
    if request.param == "postgresql":
        schema = "graph_test_" + uuid4().hex
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
    Base.metadata.create_all(connection, tables=TABLES)
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def repository(session, name="test/graph"):
    repo = Repository(full_name=name, remote_url="https://github.com/example/test")
    session.add(repo)
    session.flush()
    return repo


def test_generated_graph_exactly_matches_independent_golden(session):
    repo = repository(session)
    plan = build_graph_plan(parsed_fixture())
    result = persist_graph_plan(session, repo.id, plan)
    expected = json.loads((FIXTURE / "expected_graph.json").read_text(encoding="utf-8"))
    assert canonical_graph(session, repo.id) == expected
    assert len(result.node_ids) == 6
    assert result.edge_count == 4
    assert len(plan.gaps) == 1
    assert plan.gaps[0].reference.expression == "unknown()"


def test_deduplicated_edge_keeps_both_call_sites(session):
    repo = repository(session)
    plan = build_graph_plan(parsed_fixture())
    persist_graph_plan(session, repo.id, plan)
    repeated = [e for e in plan.edges if e.kind == "CALLS" and len(e.reference_keys) == 2]
    assert len(repeated) == 1
    report = resolution_report(plan)
    assert report["counts"]["UNRESOLVED"] == 1
    assert json.loads(json.dumps(report)) == report


def test_existing_graph_is_not_deleted_or_duplicated(session):
    repo = repository(session)
    plan = build_graph_plan(parsed_fixture())
    persist_graph_plan(session, repo.id, plan)
    before = canonical_graph(session, repo.id)
    with pytest.raises(ValueError, match="already has files"):
        persist_graph_plan(session, repo.id, plan)
    assert canonical_graph(session, repo.id) == before


def test_repository_isolation(session):
    first = repository(session)
    second = repository(session, "test/other")
    plan = build_graph_plan(parsed_fixture())
    a = persist_graph_plan(session, first.id, plan)
    b = persist_graph_plan(session, second.id, plan)
    assert not set(a.node_ids.values()) & set(b.node_ids.values())
    assert canonical_graph(session, first.id) == canonical_graph(session, second.id)


def test_missing_repository_leaves_no_graph(session):
    plan = build_graph_plan(parsed_fixture())
    with pytest.raises(ValueError, match="does not exist"):
        persist_graph_plan(session, 999999, plan)
    assert list(session.scalars(select(File))) == []


def test_dangling_edge_rejected_before_writes(session):
    repo = repository(session)
    plan = build_graph_plan(parsed_fixture())
    broken = replace(plan, edges=(replace(plan.edges[0], target_key="missing"),))
    with pytest.raises(ValueError, match="Dangling"):
        persist_graph_plan(session, repo.id, broken)
    assert list(session.scalars(select(File))) == []


def test_qualified_names_and_module_nodes_persist(session):
    repo = repository(session)
    plan = build_graph_plan(parsed_fixture())
    persist_graph_plan(session, repo.id, plan)
    symbols = list(session.scalars(select(Symbol)))
    assert sum(s.kind == "module" for s in symbols) == 2
    assert all(s.qualname for s in symbols)


def test_write_failure_rolls_back_graph_savepoint(session, monkeypatch):
    from reposcope.graph.store import GraphStore
    repo = repository(session)
    plan = build_graph_plan(parsed_fixture())
    def fail(*args, **kwargs):
        raise RuntimeError("injected edge-write failure")
    monkeypatch.setattr(GraphStore, "bulk_insert_edges", fail)
    with pytest.raises(RuntimeError, match="injected"):
        persist_graph_plan(session, repo.id, plan)
    assert list(session.scalars(select(File))) == []
    assert list(session.scalars(select(Symbol))) == []
    assert session.get(Repository, repo.id) is not None
