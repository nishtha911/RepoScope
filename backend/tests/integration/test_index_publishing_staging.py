"""Opt-in staging publisher tests. Creates and cleans only unique test repos.

Real PostgreSQL writes and parser/resolver/chunker; fake embeddings.
No Git clones, model downloads, or LLM calls. No external network services
other than the explicitly selected staging PostgreSQL endpoint.
"""
import os
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import text

from reposcope.ingestion.index_preparation import prepare_python_index
from reposcope.ingestion import publishing
from reposcope.ingestion.publishing import PublicationConflictError, publish_prepared_index
from reposcope.jobs.queue import LeaseLostError, claim_next_job, enqueue_job

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_STAGING_PUBLISH_TESTS") != "1",
    reason="Publisher integration tests require explicit staging opt-in",
)
SHA = "a" * 40


def fake_embeddings(texts):
    return [[1.0] + [0.0] * 383 for _ in texts]


@pytest.fixture
def db(tmp_path):
    from reposcope.db import engine, SessionLocal
    host = os.getenv("STAGING_PUBLISH_TEST_HOST")
    assert host and engine.url.host == host, "Refusing writes: staging hostname not verified"
    name = "publisher-test-" + uuid4().hex
    with SessionLocal.begin() as session:
        repo_id = session.execute(text("""
            INSERT INTO repositories (full_name, remote_url)
            VALUES (:name, :url) RETURNING id
        """), {"name": name, "url": "https://example.invalid/" + name}).scalar_one()
    (tmp_path / "example.py").write_text(
        "def helper():\n    return 1\n\ndef run():\n    return helper()\n", encoding="utf-8")
    try:
        prepared = prepare_python_index(tmp_path, embedder=fake_embeddings)
        yield SessionLocal, repo_id, prepared
    finally:
        with SessionLocal.begin() as session:
            params = {"repo": repo_id, "name": name}
            session.execute(text("""
                DELETE FROM edges WHERE source_symbol_id IN (
                  SELECT s.id FROM symbols s JOIN files f ON f.id=s.file_id WHERE f.repository_id=:repo
                ) OR target_symbol_id IN (
                  SELECT s.id FROM symbols s JOIN files f ON f.id=s.file_id WHERE f.repository_id=:repo
                )
            """), params)
            session.execute(text("DELETE FROM chunks WHERE repo_id=:repo"), params)
            session.execute(text("DELETE FROM symbols WHERE file_id IN (SELECT id FROM files WHERE repository_id=:repo)"), params)
            session.execute(text("DELETE FROM files WHERE repository_id=:repo"), params)
            session.execute(text("DELETE FROM repository_snapshots WHERE repository_id=:repo"), params)
            session.execute(text("DELETE FROM ingestion_jobs WHERE repository_id=:repo"), params)
            session.execute(text("DELETE FROM repositories WHERE id=:repo AND full_name=:name"), params)


def new_job(factory, repo_id, key=None):
    with factory.begin() as session:
        job_id = enqueue_job(session, repo_id, key or uuid4().hex)
    with factory.begin() as session:
        job = claim_next_job(session, repository_id=repo_id, lease_seconds=300)
    assert job and job.id == job_id
    return job


def counts(factory, repo_id):
    with factory.begin() as session:
        result = {}
        for table, condition in (
            ("files", "repository_id=:repo"),
            ("symbols", "file_id IN (SELECT id FROM files WHERE repository_id=:repo)"),
            ("chunks", "repo_id=:repo"),
            ("edges", "source_symbol_id IN (SELECT s.id FROM symbols s JOIN files f ON f.id=s.file_id WHERE f.repository_id=:repo)"),
            ("repository_snapshots", "repository_id=:repo"),
        ):
            result[table] = session.execute(text(f"SELECT count(*) FROM {table} WHERE {condition}"),
                                            {"repo": repo_id}).scalar_one()
        return result


def job_state(factory, job):
    with factory.begin() as session:
        return session.execute(text("SELECT status FROM ingestion_jobs WHERE id=:id"),
                               {"id": job.id}).scalar_one()


def publish(factory, job, prepared, sha=SHA):
    return publish_prepared_index(job, prepared, commit_sha=sha, session_factory=factory)


def test_publishes_data_snapshot_and_job_together(db):
    factory, repo, prepared = db
    job = new_job(factory, repo)
    result = publish(factory, job, prepared)
    assert not result.reused
    assert (result.file_count, result.symbol_count, result.chunk_count) == (1, 2, 2)
    assert result.edge_count >= 1
    assert job_state(factory, job) == "succeeded"
    assert counts(factory, repo) == {"files": 1, "symbols": 2, "chunks": 2,
                                   "edges": result.edge_count, "repository_snapshots": 1}
    with factory.begin() as session:
        row = session.execute(text("SELECT status, indexed_at FROM repository_snapshots WHERE id=:id"),
                              {"id": result.snapshot_id}).one()
        assert row.status == "ready" and row.indexed_at is not None
        assert session.execute(text("SELECT count(*) FROM chunks WHERE repo_id=:repo AND search_vector IS NULL"),
                               {"repo": repo}).scalar_one() == 0


def test_exact_replay_reuses_snapshot_without_duplicates(db):
    factory, repo, prepared = db
    first = publish(factory, new_job(factory, repo), prepared)
    before = counts(factory, repo)
    second_job = new_job(factory, repo)
    second = publish(factory, second_job, prepared)
    assert second.reused and second.snapshot_id == first.snapshot_id
    assert counts(factory, repo) == before
    assert job_state(factory, second_job) == "succeeded"


def test_failed_final_status_update_rolls_back_every_index_write(db, monkeypatch):
    factory, repo, prepared = db
    job = new_job(factory, repo)
    def fail(session, claimed):
        raise RuntimeError("injected final-write failure")
    monkeypatch.setattr(publishing, "mark_job_succeeded", fail)
    with pytest.raises(RuntimeError, match="injected"):
        publish(factory, job, prepared)
    assert all(value == 0 for value in counts(factory, repo).values())
    assert job_state(factory, job) == "running"


def test_wrong_token_cannot_publish(db):
    factory, repo, prepared = db
    job = new_job(factory, repo)
    with pytest.raises(LeaseLostError):
        publish(factory, replace(job, lease_token=str(uuid4())), prepared)
    assert all(value == 0 for value in counts(factory, repo).values())
    assert job_state(factory, job) == "running"


def test_expired_lease_cannot_publish(db):
    factory, repo, prepared = db
    job = new_job(factory, repo)
    with factory.begin() as session:
        session.execute(text("UPDATE ingestion_jobs SET leased_until=clock_timestamp()-interval '1 second' WHERE id=:id"),
                        {"id": job.id})
    with pytest.raises(LeaseLostError):
        publish(factory, job, prepared)
    assert all(value == 0 for value in counts(factory, repo).values())


def test_completed_job_cannot_publish_again(db):
    factory, repo, prepared = db
    job = new_job(factory, repo)
    publish(factory, job, prepared)
    before = counts(factory, repo)
    with pytest.raises(LeaseLostError):
        publish(factory, job, prepared)
    assert counts(factory, repo) == before


def test_different_commit_refused_without_modifying_existing_index(db):
    factory, repo, prepared = db
    publish(factory, new_job(factory, repo), prepared)
    before = counts(factory, repo)
    job = new_job(factory, repo)
    with pytest.raises(PublicationConflictError, match="replacement"):
        publish(factory, job, prepared, sha="b" * 40)
    assert counts(factory, repo) == before
    assert job_state(factory, job) == "running"


def test_legacy_files_are_not_overwritten(db):
    factory, repo, prepared = db
    with factory.begin() as session:
        session.execute(text("INSERT INTO files(repository_id,path,language) VALUES(:repo,'legacy.py','python')"),
                        {"repo": repo})
    before = counts(factory, repo)
    job = new_job(factory, repo)
    with pytest.raises(PublicationConflictError, match="replacement"):
        publish(factory, job, prepared)
    assert counts(factory, repo) == before


def test_replay_detects_stored_chunk_drift(db):
    factory, repo, prepared = db
    publish(factory, new_job(factory, repo), prepared)
    with factory.begin() as session:
        session.execute(text("UPDATE chunks SET text=text || E'\\n# changed' WHERE repo_id=:repo"), {"repo": repo})
    job = new_job(factory, repo)
    with pytest.raises(PublicationConflictError, match="chunks"):
        publish(factory, job, prepared)
    assert job_state(factory, job) == "running"


def test_invalid_embedding_is_rejected_without_writes(db):
    factory, repo, prepared = db
    job = new_job(factory, repo)
    invalid = replace(prepared, embeddings=((1.0,),) * len(prepared.chunks))
    with pytest.raises(ValueError, match="embedding"):
        publish(factory, job, invalid)
    assert all(value == 0 for value in counts(factory, repo).values())


def test_invalid_commit_id_is_rejected(db):
    factory, repo, prepared = db
    job = new_job(factory, repo)
    with pytest.raises(ValueError, match="commit_sha"):
        publish(factory, job, prepared, sha="main")
    assert all(value == 0 for value in counts(factory, repo).values())
