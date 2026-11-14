"""Run the neighbors query against local SQLite fixture tables.

Tests real SELECT/join/filter behavior, not PostgreSQL constraints or production
access control. No provider calls, network, or configured application DB access.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from reposcope.api import repos


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE files (id INTEGER PRIMARY KEY, repository_id INTEGER, snapshot_id INTEGER, path TEXT, language TEXT)")
        connection.exec_driver_sql("CREATE TABLE symbols (id INTEGER PRIMARY KEY, file_id INTEGER, name TEXT, qualname TEXT, kind TEXT, start_line INTEGER, end_line INTEGER)")
        connection.exec_driver_sql("CREATE TABLE edges (id INTEGER PRIMARY KEY, source_symbol_id INTEGER, target_symbol_id INTEGER, kind TEXT, confidence FLOAT)")
        connection.execute(text("INSERT INTO files VALUES (:id,:repo,9,:path,'python')"), [
            {"id": 1, "repo": 33, "path": "sample/core.py"},
            {"id": 2, "repo": 24, "path": "backend/other.py"}])
        connection.execute(text("INSERT INTO symbols VALUES (:id,:file,:name,:name,:kind,1,3)"), [
            {"id": 75, "file": 1, "name": "get_hmm", "kind": "function"},
            {"id": 76, "file": 1, "name": "hmm", "kind": "function"},
            {"id": 77, "file": 1, "name": "get_answer", "kind": "function"},
            {"id": 78, "file": 1, "name": "AdvancedTestSuite", "kind": "class"},
            {"id": 79, "file": 1, "name": "test_thoughts", "kind": "method"},
            {"id": 200, "file": 2, "name": "other_repo", "kind": "function"},
        ])
        connection.execute(text("INSERT INTO edges VALUES (:id,:src,:dst,:kind,:confidence)"), [
            {"id": 1, "src": 76, "dst": 75, "kind": "CALLS", "confidence": 0.9},
            {"id": 2, "src": 76, "dst": 77, "kind": "CALLS", "confidence": None},
            {"id": 3, "src": 78, "dst": 79, "kind": "CONTAINS", "confidence": None},
            {"id": 4, "src": 200, "dst": 75, "kind": "CALLS", "confidence": 0.9},
            {"id": 5, "src": 76, "dst": 200, "kind": "CALLS", "confidence": 0.9},
            {"id": 6, "src": 76, "dst": 75, "kind": "USES", "confidence": 0.5},
        ])
    monkeypatch.setattr(repos, "SessionLocal", lambda: Session(engine))
    yield engine
    engine.dispose()


def test_outgoing_returns_targets_not_inspected_symbol(db):
    result = repos.get_symbol_neighbors(76, direction="out", types="")
    assert [(n.symbol_id, n.relationship_type) for n in result.neighbors] == [(75, "CALLS"), (77, "CALLS"), (75, "USES")]
    assert all(n.direction == "out" for n in result.neighbors)


def test_incoming_returns_sources_not_inspected_symbol(db):
    result = repos.get_symbol_neighbors(75, direction="in", types="")
    assert [(n.symbol_id, n.relationship_type) for n in result.neighbors] == [(76, "CALLS"), (76, "USES")]
    assert all(n.direction == "in" for n in result.neighbors)


@pytest.mark.parametrize("symbol_id,direction", [(78, "out"), (79, "in")])
def test_internal_contains_does_not_break_public_response(db, symbol_id, direction):
    assert repos.get_symbol_neighbors(symbol_id, direction=direction, types="").neighbors == []
    with Session(db) as session:
        assert session.execute(text("SELECT count(*) FROM edges WHERE kind='CONTAINS'")).scalar_one() == 1


def test_explicit_filter_returns_only_selected_public_kind(db):
    result = repos.get_symbol_neighbors(76, direction="out", types="USES")
    assert [(n.symbol_id, n.relationship_type) for n in result.neighbors] == [(75, "USES")]


def test_multiple_filters_keep_parallel_kinds(db):
    result = repos.get_symbol_neighbors(75, direction="in", types="CALLS, USES")
    assert [n.relationship_type for n in result.neighbors] == ["CALLS", "USES"]


def test_unknown_confidence_is_preserved_as_null(db):
    result = repos.get_symbol_neighbors(76, direction="out", types="CALLS")
    assert next(n for n in result.neighbors if n.symbol_id == 77).confidence is None


@pytest.mark.parametrize("types", ["CONTAINS", "UNKNOWN", "calls", "CALLS,"])
def test_unsupported_requested_types_are_rejected(db, types):
    with pytest.raises(HTTPException) as error:
        repos.get_symbol_neighbors(76, direction="out", types=types)
    assert error.value.status_code == 422


@pytest.mark.parametrize("symbol_id,direction", [(75, "in"), (76, "out")])
def test_cross_repository_edges_are_excluded(db, symbol_id, direction):
    assert all(n.symbol_id != 200 for n in repos.get_symbol_neighbors(symbol_id, direction=direction, types="").neighbors)


def test_no_outgoing_edges_returns_empty(db):
    assert repos.get_symbol_neighbors(75, direction="out", types="").neighbors == []
