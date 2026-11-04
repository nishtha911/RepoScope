"""Real Day 7 loader/hydration -> Evidence Pack -> prompt integration.

Hybrid ranking is stubbed; no embedding/model calls. Uses DATABASE_URL from root
.env and temporary transactional schema in that same PostgreSQL database.
"""
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from reposcope.rag.pipeline import SOURCE_SEPARATOR, assemble_evidence_pack
from reposcope.rag.evidence_pack import citation_map
from reposcope.rag.prompts import build_spotlighted_messages
from reposcope.retrieval import expanded_pipeline


def raw(symbol):
    return json.dumps(dict(file_path="app.py",qualname=f"f{symbol}",kind="function",
                           signature=f"def f{symbol}():",docstring=None)) + SOURCE_SEPARATOR + f"def f{symbol}():\n    return {symbol}\n"


@pytest.fixture
def db():
    load_dotenv(Path(__file__).resolve().parents[3] / ".env",override=False)
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.fail("DATABASE_URL is missing; check root .env")
    engine = create_engine(url)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("DATABASE_URL must point to PostgreSQL")
    connection = engine.connect()
    transaction = connection.begin()
    session = None
    try:
        schema = "evidence_test_" + uuid4().hex
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        for ddl in (
            "CREATE TABLE repositories(id integer PRIMARY KEY)",
            "CREATE TABLE repository_snapshots(id integer PRIMARY KEY,repository_id integer REFERENCES repositories(id),commit_sha text,status text)",
            "CREATE TABLE files(id integer PRIMARY KEY,repository_id integer REFERENCES repositories(id),snapshot_id integer REFERENCES repository_snapshots(id),path text)",
            "CREATE TABLE symbols(id integer PRIMARY KEY,file_id integer REFERENCES files(id),name text,qualname text,kind text,start_line integer,end_line integer)",
            "CREATE TABLE chunks(id integer PRIMARY KEY,symbol_id integer UNIQUE REFERENCES symbols(id),repo_id integer REFERENCES repositories(id),text text)",
            "CREATE TABLE edges(id integer PRIMARY KEY,source_symbol_id integer REFERENCES symbols(id),target_symbol_id integer REFERENCES symbols(id),kind text,confidence double precision)",
            "INSERT INTO repositories VALUES(1)",
            "INSERT INTO files VALUES(3,1,NULL,'app.py')",
            "INSERT INTO symbols VALUES(1,3,'f1','f1','function',10,11),(2,3,'f2','f2','function',20,21),(3,3,'GET /users','GET /users','endpoint',8,11),(4,3,'app','app','module',1,21)",
            "INSERT INTO edges VALUES(1,1,2,'CALLS',0.9),(2,3,1,'CALLS',0.95),(3,4,3,'EXPOSES',0.95)",
        ):
            connection.execute(text(ddl))
        connection.execute(text("INSERT INTO repository_snapshots VALUES(42,1,:sha,'ready'),(43,1,:other,'ready')"),
                           dict(sha="a"*40,other="b"*40))
        connection.execute(text("UPDATE files SET snapshot_id=42"))
        for symbol in (1,2):
            connection.execute(text("INSERT INTO chunks VALUES(:id,:id,1,:body)"),dict(id=symbol,body=raw(symbol)))
        session = Session(bind=connection,join_transaction_mode="create_savepoint")
        yield session
    finally:
        if session is not None:
            session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.fixture
def retrieve(db,monkeypatch):
    monkeypatch.setattr(expanded_pipeline,"_hybrid_search",lambda *args,**kwargs:[
        NS(chunk_id=1,symbol_id=1,repo_id=1,text=raw(1),score=.1)])
    def run(intent="implementation"):
        return expanded_pipeline.search_chunks_hybrid_expanded(db,1,"Explain f1",intent=intent)
    return run


def test_real_day7_to_pack_to_prompt(db,retrieve):
    pack = assemble_evidence_pack(db,retrieve(),snapshot_id=42)
    assert list(citation_map(pack)) == ["E1","E2"]
    assert [entry.source.start_line for entry in pack.entries] == [10,20]
    assert pack.entries[1].paths[0].edge_ids == (1,)
    assert pack.entries[0].signature == "def f1():"
    assert "Allowed IDs: [E1], [E2]." in build_spotlighted_messages("Explain",pack)[0]["content"]


def test_endpoint_metadata_is_not_fabricated_code(db,retrieve):
    pack = assemble_evidence_pack(db,retrieve("endpoints"),snapshot_id=42)
    assert list(citation_map(pack)) == ["E1"]
    assert {node.kind for node in pack.context_symbols} == {"function","endpoint","module"}
    assert any("metadata only" in gap for gap in pack.gaps)


def test_null_snapshot_is_explicit_gap(db,retrieve):
    db.execute(text("UPDATE files SET snapshot_id=NULL"))
    pack = assemble_evidence_pack(db,retrieve(),snapshot_id=42)
    assert not pack.entries
    assert any("no verified snapshot" in gap for gap in pack.gaps)


def test_snapshot_mismatch_rejected(db,retrieve):
    db.execute(text("UPDATE files SET snapshot_id=43"))
    with pytest.raises(ValueError,match="different snapshot"):
        assemble_evidence_pack(db,retrieve(),snapshot_id=42)


def test_changed_source_after_retrieval_rejected(db,retrieve):
    result = retrieve()
    db.execute(text("UPDATE chunks SET text='changed' WHERE id=1"))
    with pytest.raises(ValueError,match="rerun retrieval"):
        assemble_evidence_pack(db,result,snapshot_id=42)
