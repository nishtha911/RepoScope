"""Opt-in PostgreSQL queue integration tests. Never run against production.

Creates a unique test Repository per test; commits queue transactions and
removes only that repository's jobs and repository during fixture teardown.
No network clones, embeddings, or LLM calls are performed.
"""
import os
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_STAGING_QUEUE_TESTS") != "1",
    reason="Set RUN_STAGING_QUEUE_TESTS=1 and STAGING_QUEUE_TEST_HOST explicitly",
)


@pytest.fixture
def queue_db():
    from reposcope.db import engine, SessionLocal
    expected = os.getenv("STAGING_QUEUE_TEST_HOST")
    assert expected, "Set STAGING_QUEUE_TEST_HOST to the verified staging hostname"
    assert engine.url.host == expected, "Refusing writes: database hostname does not match"
    name = "queue-test-" + uuid4().hex
    with SessionLocal.begin() as session:
        repo_id = session.execute(text("""
            INSERT INTO repositories (full_name, remote_url)
            VALUES (:name, :url) RETURNING id
        """), {"name": name, "url": "https://example.invalid/" + name}).scalar_one()
    try:
        yield SessionLocal, repo_id
    finally:
        with SessionLocal.begin() as session:
            session.execute(text("DELETE FROM ingestion_jobs WHERE repository_id = :id"), {"id": repo_id})
            session.execute(text("DELETE FROM repositories WHERE id = :id AND full_name = :name"),
                            {"id": repo_id, "name": name})


def state(factory, job_id):
    with factory.begin() as session:
        return dict(session.execute(text("SELECT * FROM ingestion_jobs WHERE id = :id"),
                                    {"id": job_id}).mappings().one())


def submit(factory, repo_id, key="test", max_attempts=3):
    from reposcope.jobs.queue import enqueue_job
    with factory.begin() as session:
        return enqueue_job(session, repo_id, key, max_attempts=max_attempts)


def claim(factory, repo_id, lease_seconds=300):
    from reposcope.jobs.queue import claim_next_job
    with factory.begin() as session:
        return claim_next_job(session, repository_id=repo_id, lease_seconds=lease_seconds)


def expire(factory, job_id):
    with factory.begin() as session:
        session.execute(text("""
            UPDATE ingestion_jobs SET leased_until = clock_timestamp() - interval '1 second'
            WHERE id = :id
        """), {"id": job_id})


def test_enqueue_is_idempotent(queue_db):
    factory, repo_id = queue_db
    first = submit(factory, repo_id)
    assert submit(factory, repo_id) == first
    assert state(factory, first)["attempts"] == 0


def test_success_clears_lease_and_is_not_reclaimed(queue_db):
    from reposcope.jobs.queue import mark_job_succeeded
    factory, repo_id = queue_db
    job_id = submit(factory, repo_id)
    job = claim(factory, repo_id)
    assert job.id == job_id and job.attempts == 1
    assert claim(factory, repo_id) is None
    with factory.begin() as session:
        mark_job_succeeded(session, job)
    row = state(factory, job_id)
    assert row["status"] == "succeeded"
    assert row["lease_token"] is None and row["leased_until"] is None
    assert row["finished_at"] is not None
    assert claim(factory, repo_id) is None


def test_wrong_token_cannot_complete(queue_db):
    from reposcope.jobs.queue import LeaseLostError, mark_job_succeeded
    factory, repo_id = queue_db
    submit(factory, repo_id)
    job = claim(factory, repo_id)
    with factory.begin() as session:
        with pytest.raises(LeaseLostError):
            mark_job_succeeded(session, replace(job, lease_token=str(uuid4())))
    assert state(factory, job.id)["status"] == "running"


def test_delayed_retry_is_not_immediately_claimed(queue_db):
    from reposcope.jobs.queue import mark_job_failed
    factory, repo_id = queue_db
    submit(factory, repo_id)
    job = claim(factory, repo_id)
    with factory.begin() as session:
        mark_job_failed(session, job, sanitized_error="test failure", retry_delay_seconds=3600)
    row = state(factory, job.id)
    assert row["status"] == "queued" and row["attempts"] == 1
    assert row["lease_token"] is None
    assert claim(factory, repo_id) is None


def test_final_failure_is_terminal(queue_db):
    from reposcope.jobs.queue import mark_job_failed
    factory, repo_id = queue_db
    submit(factory, repo_id, max_attempts=1)
    job = claim(factory, repo_id)
    with factory.begin() as session:
        mark_job_failed(session, job, sanitized_error="test failure", retry_delay_seconds=0)
    assert state(factory, job.id)["status"] == "failed"
    assert claim(factory, repo_id) is None


def test_expired_job_is_reclaimed_and_old_token_is_fenced(queue_db):
    from reposcope.jobs.queue import LeaseLostError, mark_job_succeeded
    factory, repo_id = queue_db
    submit(factory, repo_id)
    old = claim(factory, repo_id)
    expire(factory, old.id)
    new = claim(factory, repo_id)
    assert new.id == old.id and new.attempts == 2
    assert new.lease_token != old.lease_token
    with factory.begin() as session:
        with pytest.raises(LeaseLostError):
            mark_job_succeeded(session, old)
    with factory.begin() as session:
        mark_job_succeeded(session, new)


def test_expired_final_attempt_is_failed(queue_db):
    factory, repo_id = queue_db
    submit(factory, repo_id, max_attempts=1)
    job = claim(factory, repo_id)
    expire(factory, job.id)
    assert claim(factory, repo_id) is None
    row = state(factory, job.id)
    assert row["status"] == "failed" and row["lease_token"] is None


def test_heartbeat_extends_live_lease(queue_db):
    from reposcope.jobs.queue import renew_job_lease
    factory, repo_id = queue_db
    submit(factory, repo_id)
    job = claim(factory, repo_id, lease_seconds=60)
    before = state(factory, job.id)["leased_until"]
    with factory.begin() as session:
        renew_job_lease(session, job, lease_seconds=600)
    assert state(factory, job.id)["leased_until"] > before


def test_expired_worker_cannot_renew_or_complete(queue_db):
    from reposcope.jobs.queue import LeaseLostError, renew_job_lease, mark_job_succeeded
    factory, repo_id = queue_db
    submit(factory, repo_id)
    job = claim(factory, repo_id)
    expire(factory, job.id)
    for operation in (renew_job_lease, mark_job_succeeded):
        with factory.begin() as session:
            with pytest.raises(LeaseLostError):
                operation(session, job)


def test_second_transaction_skips_first_transactions_locked_job(queue_db):
    from reposcope.jobs.queue import claim_next_job
    factory, repo_id = queue_db
    first_id = submit(factory, repo_id, key="first")
    second_id = submit(factory, repo_id, key="second")
    with factory.begin() as session_a:
        a = claim_next_job(session_a, repository_id=repo_id)
        assert a.id == first_id
        with factory.begin() as session_b:
            session_b.execute(text("SET LOCAL lock_timeout = '2s'"))
            session_b.execute(text("SET LOCAL statement_timeout = '5s'"))
            b = claim_next_job(session_b, repository_id=repo_id)
            assert b.id == second_id and b.id != a.id
    assert state(factory, first_id)["status"] == "running"
    assert state(factory, second_id)["status"] == "running"


def test_rollback_discards_enqueue(queue_db):
    from reposcope.jobs.queue import enqueue_job
    factory, repo_id = queue_db
    with factory() as session:
        job_id = enqueue_job(session, repo_id, "rolled-back")
        session.rollback()
    with factory.begin() as session:
        assert session.execute(text("SELECT id FROM ingestion_jobs WHERE id = :id"),
                               {"id": job_id}).scalar_one_or_none() is None


def test_invalid_inputs_are_rejected(queue_db):
    from reposcope.jobs.queue import enqueue_job, claim_next_job
    factory, repo_id = queue_db
    with factory.begin() as session:
        with pytest.raises(ValueError):
            enqueue_job(session, repo_id, " ")
        with pytest.raises(ValueError):
            enqueue_job(session, repo_id, "key", max_attempts=0)
        with pytest.raises(ValueError):
            claim_next_job(session, lease_seconds=0)
