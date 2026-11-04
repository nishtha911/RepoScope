import json
import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session

from reposcope.graph.builder import (
    build_graph_plan,
    canonical_graph,
    persist_graph_plan,
    resolution_report,
)
from reposcope.models.base import Base
from reposcope.models.edge import Edge
from reposcope.models.file import File
from reposcope.models.repository import Repository
from reposcope.models.repository_snapshot import RepositorySnapshot
from reposcope.models.symbol import Symbol
from reposcope.parsing.python_parser import parse_python


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "graph_persistence"
)

TABLES = [
    Repository.__table__,
    RepositorySnapshot.__table__,
    File.__table__,
    Symbol.__table__,
    Edge.__table__,
]


def parsed_fixture():
    sources = json.loads(
        (FIXTURE / "sources.json").read_text(encoding="utf-8")
    )

    return [
        parse_python(
            source.encode("utf-8"),
            file_path=path,
        )
        for path, source in sources.items()
    ]


@pytest.fixture(params=["sqlite", "postgresql"])
def session(request):
    if request.param == "postgresql":
        project_root = Path(__file__).resolve().parents[3]
        load_dotenv(project_root / ".env", override=False)
        url = os.getenv("DATABASE_URL")

        if not url:
            pytest.fail("DATABASE_URL is missing; check your root .env")

        engine = create_engine(url)

        if engine.dialect.name != "postgresql":
            engine.dispose()
            pytest.fail("DATABASE_URL must point to PostgreSQL")

    else:
        engine = create_engine("sqlite:///:memory:")

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

    connection = engine.connect()
    transaction = connection.begin()

    if request.param == "postgresql":
        schema = "graph_test_" + uuid4().hex

        connection.execute(
            text(f'CREATE SCHEMA "{schema}"')
        )
        connection.execute(
            text(f'SET LOCAL search_path TO "{schema}"')
        )

    Base.metadata.create_all(
        connection,
        tables=TABLES,
    )

    db = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def repository(session, name="test/graph"):
    repo = Repository(
        full_name=name,
        remote_url="https://github.com/example/test",
    )

    session.add(repo)
    session.flush()

    return repo


def test_generated_graph_exactly_matches_independent_golden(session):
    repo = repository(session)
    plan = build_graph_plan(parsed_fixture())
    result = persist_graph_plan(session, repo.id, plan)

    expected = json.loads(
        (FIXTURE / "expected_graph.json").read_text(
            encoding="utf-8"
        )
    )

    assert canonical_graph(session, repo.id) == expected
    assert len(result.node_ids) == 6
    assert result.edge_count == 4
    assert len(plan.gaps) == 1
    assert plan.gaps[0].reference.expression == "unknown()"


def test_deduplicated_edge_keeps_both_call_sites(session):
    repo = repository(session)
    plan = build_graph_plan(parsed_fixture())

    persist_graph_plan(session, repo.id, plan)

    repeated = [
        edge
        for edge in plan.edges
        if edge.kind == "CALLS"
        and len(edge.reference_keys) == 2
    ]

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

    first_result = persist_graph_plan(
        session,
        first.id,
        plan,
    )
    second_result = persist_graph_plan(
        session,
        second.id,
        plan,
    )

    assert not (
        set(first_result.node_ids.values())
        & set(second_result.node_ids.values())
    )

    assert (
        canonical_graph(session, first.id)
        == canonical_graph(session, second.id)
    )


def test_missing_repository_leaves_no_graph(session):
    plan = build_graph_plan(parsed_fixture())

    with pytest.raises(ValueError, match="does not exist"):
        persist_graph_plan(session, 999999, plan)

    assert list(session.scalars(select(File))) == []


def test_dangling_edge_rejected_before_writes(session):
    repo = repository(session)
    plan = build_graph_plan(parsed_fixture())

    broken = replace(
        plan,
        edges=(
            replace(
                plan.edges[0],
                target_key="missing",
            ),
        ),
    )

    with pytest.raises(ValueError, match="Dangling"):
        persist_graph_plan(session, repo.id, broken)

    assert list(session.scalars(select(File))) == []


def test_qualified_names_and_module_nodes_persist(session):
    repo = repository(session)
    plan = build_graph_plan(parsed_fixture())

    persist_graph_plan(session, repo.id, plan)

    symbols = list(session.scalars(select(Symbol)))

    assert sum(
        symbol.kind == "module"
        for symbol in symbols
    ) == 2
    assert all(symbol.qualname for symbol in symbols)


def test_write_failure_rolls_back_graph_savepoint(
    session,
    monkeypatch,
):
    from reposcope.graph.store import GraphStore

    repo = repository(session)
    plan = build_graph_plan(parsed_fixture())

    def fail(*args, **kwargs):
        raise RuntimeError("injected edge-write failure")

    monkeypatch.setattr(
        GraphStore,
        "bulk_insert_edges",
        fail,
    )

    with pytest.raises(RuntimeError, match="injected"):
        persist_graph_plan(session, repo.id, plan)

    assert list(session.scalars(select(File))) == []
    assert list(session.scalars(select(Symbol))) == []
    assert session.get(Repository, repo.id) is not None


def framework_plan():
    sources = {
        "models.py": (
            'from sqlmodel import SQLModel\n'
            'class User(SQLModel, table=True):\n'
            '    id: int\n'
        ),
        "api.py": (
            'from fastapi import FastAPI\n'
            'from models import User as Account\n'
            'app = FastAPI()\n'
            '@app.post("/users")\n'
            'def create_user():\n'
            '    return Account()\n'
        ),
    }

    parsed_files = [
        parse_python(
            source.encode("utf-8"),
            file_path=path,
        )
        for path, source in sources.items()
    ]

    return build_graph_plan(parsed_files)


def framework_node(plan, *, kind, name):
    matches = [
        node
        for node in plan.nodes
        if node.kind == kind and node.name == name
    ]

    assert len(matches) == 1

    return matches[0]


def test_framework_nodes_and_edges_persist_and_reload(session):
    repo = repository(
        session,
        "test/framework-roundtrip",
    )
    plan = framework_plan()

    endpoint = framework_node(
        plan,
        kind="endpoint",
        name="POST /users",
    )
    handler = framework_node(
        plan,
        kind="function",
        name="create_user",
    )
    model = framework_node(
        plan,
        kind="class",
        name="User",
    )
    module = next(
        node
        for node in plan.nodes
        if node.kind == "module"
        and node.path == "api.py"
    )

    persisted = persist_graph_plan(
        session,
        repo.id,
        plan,
    )
    repository_id = repo.id

    assert persisted.edge_count == len(plan.edges)
    assert len(persisted.node_ids) == len(plan.nodes)

    session.flush()
    session.expunge_all()

    stored_files = list(
        session.scalars(
            select(File).where(
                File.repository_id == repository_id
            )
        )
    )
    file_ids = {
        file.id
        for file in stored_files
    }

    stored_symbols = list(
        session.scalars(
            select(Symbol).where(
                Symbol.file_id.in_(file_ids)
            )
        )
    )
    symbol_ids = {
        symbol.id
        for symbol in stored_symbols
    }

    stored_edges = list(
        session.scalars(
            select(Edge).where(
                Edge.source_symbol_id.in_(symbol_ids)
            )
        )
    )

    stored_endpoint = next(
        symbol
        for symbol in stored_symbols
        if symbol.id == persisted.node_ids[endpoint.key]
    )

    assert stored_endpoint.kind == "endpoint"
    assert stored_endpoint.name == "POST /users"
    assert stored_endpoint.qualname == endpoint.qualname
    assert stored_endpoint.start_line == endpoint.start_line
    assert stored_endpoint.end_line == endpoint.end_line

    relationships = {
        (
            edge.source_symbol_id,
            edge.target_symbol_id,
            edge.kind,
        )
        for edge in stored_edges
    }

    assert (
        persisted.node_ids[module.key],
        persisted.node_ids[endpoint.key],
        "EXPOSES",
    ) in relationships

    assert (
        persisted.node_ids[endpoint.key],
        persisted.node_ids[handler.key],
        "CALLS",
    ) in relationships

    assert (
        persisted.node_ids[handler.key],
        persisted.node_ids[model.key],
        "USES",
    ) in relationships

    assert all(
        edge.target_symbol_id in symbol_ids
        for edge in stored_edges
    )

    assert len(stored_symbols) == len(plan.nodes)
    assert len(stored_edges) == len(plan.edges)

    assert sorted(
        edge.confidence
        for edge in stored_edges
    ) == sorted(
        edge.confidence
        for edge in plan.edges
    )

    exported = canonical_graph(
        session,
        repository_id,
    )

    assert len(exported["nodes"]) == len(plan.nodes)
    assert len(exported["edges"]) == len(plan.edges)


def test_framework_graph_rejects_replacement_without_changes(session):
    repo = repository(
        session,
        "test/framework-no-replacement",
    )
    plan = framework_plan()

    persist_graph_plan(session, repo.id, plan)

    before = canonical_graph(session, repo.id)

    with pytest.raises(ValueError, match="already has files"):
        persist_graph_plan(session, repo.id, plan)

    assert canonical_graph(session, repo.id) == before


def test_framework_graphs_are_isolated_between_repositories(session):
    first_repo = repository(
        session,
        "test/framework-first",
    )
    second_repo = repository(
        session,
        "test/framework-second",
    )
    plan = framework_plan()

    first = persist_graph_plan(
        session,
        first_repo.id,
        plan,
    )
    second = persist_graph_plan(
        session,
        second_repo.id,
        plan,
    )

    assert not (
        set(first.node_ids.values())
        & set(second.node_ids.values())
    )

    assert (
        canonical_graph(session, first_repo.id)
        == canonical_graph(session, second_repo.id)
    )


def test_framework_edge_write_failure_rolls_back_nodes(
    session,
    monkeypatch,
):
    from reposcope.graph.store import GraphStore

    repo = repository(
        session,
        "test/framework-rollback",
    )
    plan = framework_plan()

    assert any(
        node.kind == "endpoint"
        for node in plan.nodes
    )

    def fail(*args, **kwargs):
        raise RuntimeError(
            "injected framework edge-write failure"
        )

    monkeypatch.setattr(
        GraphStore,
        "bulk_insert_edges",
        fail,
    )

    with pytest.raises(
        RuntimeError,
        match="injected framework",
    ):
        persist_graph_plan(session, repo.id, plan)

    assert list(session.scalars(select(File))) == []
    assert list(session.scalars(select(Symbol))) == []
    assert list(session.scalars(select(Edge))) == []
    assert session.get(Repository, repo.id) is not None
