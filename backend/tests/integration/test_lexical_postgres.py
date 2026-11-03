"""Real PostgreSQL migration/FTS tests in a transaction-scoped random schema."""
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from reposcope.retrieval.lexical import normalize_identifier_text, search_chunks_by_lexical

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "d5e2a6b7c801_add_lexical_search.py"


@pytest.fixture
def db():
    url = os.getenv("TEST_LEXICAL_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_LEXICAL_DATABASE_URL to a disposable PostgreSQL database")
    engine = create_engine(url)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("TEST_LEXICAL_DATABASE_URL must use PostgreSQL")
    connection = engine.connect()
    outer = connection.begin()
    session = None
    try:
        schema = "lexical_test_" + uuid4().hex
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        ddl = [
            "CREATE TABLE repositories (id integer PRIMARY KEY)",
            "CREATE TABLE files (id integer PRIMARY KEY, repository_id integer REFERENCES repositories(id), path text NOT NULL)",
            "CREATE TABLE symbols (id integer PRIMARY KEY, file_id integer REFERENCES files(id), name text NOT NULL, qualname text, start_line integer NOT NULL, end_line integer NOT NULL)",
            "CREATE TABLE chunks (id integer PRIMARY KEY, symbol_id integer UNIQUE REFERENCES symbols(id), repo_id integer REFERENCES repositories(id), text text NOT NULL)",
            "INSERT INTO repositories VALUES (1), (2)",
            "INSERT INTO files VALUES (1, 1, 'app.py'), (2, 2, 'other.py')",
            "INSERT INTO symbols VALUES (1,1,'calculateTotal','calculateTotal',1,2), (2,1,'process','process',3,4), (3,2,'calculateTotal','calculateTotal',1,2)",
            "INSERT INTO chunks VALUES (1,1,1,'return sum(items)'), (2,2,1,'calculate_total = 1'), (3,3,2,'return sum(items)')",
        ]
        for statement in ddl:
            connection.execute(text(statement))
        spec = importlib.util.spec_from_file_location("lexical_migration_under_test", MIGRATION)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        yield session
    finally:
        if session is not None:
            session.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
        engine.dispose()


def test_backfill_search_and_repository_isolation(db):
    hits = search_chunks_by_lexical(db, 1, "calculate_total")
    assert {h.chunk_id for h in hits} == {1, 2}
    assert all(h.repo_id == 1 for h in hits)
    assert [h.chunk_id for h in search_chunks_by_lexical(db, 2, "calculateTotal")] == [3]


def test_symbol_name_weight_outweighs_body_match(db):
    hits = search_chunks_by_lexical(db, 1, "calculate total")
    assert [h.chunk_id for h in hits] == [1, 2]
    assert hits[0].score > hits[1].score > 0


def test_new_chunks_are_indexed_automatically(db):
    db.execute(text("INSERT INTO symbols VALUES (4,1,'HTTPServerError','HTTPServerError',5,6)"))
    db.execute(text("INSERT INTO chunks (id,symbol_id,repo_id,text) VALUES (4,4,1,'raise error')"))
    assert [h.chunk_id for h in search_chunks_by_lexical(db, 1, "http_server_error")] == [4]


def test_chunk_text_update_refreshes_vector(db):
    db.execute(text("UPDATE chunks SET text='uniqueBodyToken' WHERE id=2"))
    assert [h.chunk_id for h in search_chunks_by_lexical(db, 1, "unique body token")] == [2]
    assert [h.chunk_id for h in search_chunks_by_lexical(db, 1, "calculate total")] == [1]


def test_symbol_rename_refreshes_vector(db):
    db.execute(text("UPDATE symbols SET name='grandTotal', qualname='grandTotal' WHERE id=1"))
    assert [h.chunk_id for h in search_chunks_by_lexical(db, 1, "grand_total")] == [1]
    assert [h.chunk_id for h in search_chunks_by_lexical(db, 1, "calculate total")] == [2]


def test_corrupt_chunk_repository_does_not_leak_results(db):
    db.execute(text("UPDATE chunks SET repo_id=2 WHERE id=1"))
    assert [h.chunk_id for h in search_chunks_by_lexical(db, 2, "calculate total")] == [3]


def test_unsafe_query_is_data_not_sql(db):
    assert search_chunks_by_lexical(db, 1, "x'); DROP TABLE symbols; --") == []
    assert db.scalar(text("SELECT count(*) FROM symbols")) == 3


def test_database_and_python_normalizers_agree(db):
    for value in ("HTTPServerError", "parseJSON2Value", "get_user_id", "UserService.run", "!@#", ""):
        actual = db.scalar(text("SELECT reposcope_identifier_text(:value)"), {"value": value})
        assert actual == normalize_identifier_text(value)


def test_gin_index_and_limit(db):
    index = db.scalar(text("SELECT indexdef FROM pg_indexes WHERE schemaname=current_schema() AND indexname='ix_chunks_search_vector_gin'"))
    assert "USING gin" in index
    assert len(search_chunks_by_lexical(db, 1, "calculate total", limit=1)) == 1
