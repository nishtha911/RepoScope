"""Opt-in registration HTTP + PostgreSQL tests; no worker or model calls.

Uses a minimal FastAPI app mounting the actual repository router. This does
not test the production app's auth/middleware. A live worker must NOT consume
these generated fixture jobs while this suite runs.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from reposcope.api import repos

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_STAGING_REGISTRATION_TESTS") != "1",
    reason="Registration tests require explicit staging opt-in",
)


@pytest.fixture
def fixture():
    from reposcope.db import engine, SessionLocal
    host = os.getenv("STAGING_REGISTRATION_TEST_HOST")
    assert host and engine.url.host == host, "Refusing writes: staging host is not verified"
    name = "registration-tests/repo-" + uuid4().hex
    app = FastAPI()
    app.include_router(repos.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        try:
            yield client, app, SessionLocal, name
        finally:
            with SessionLocal.begin() as session:
                ids = session.execute(text("SELECT id FROM repositories WHERE lower(full_name)=:name"),
                                      {"name": name}).scalars().all()
                for repo_id in ids:
                    params = {"id": repo_id}
                    # These tests create files/snapshots only, never symbols/chunks.
                    session.execute(text("DELETE FROM ingestion_jobs WHERE repository_id=:id"), params)
                    session.execute(text("DELETE FROM files WHERE repository_id=:id"), params)
                    session.execute(text("DELETE FROM repository_snapshots WHERE repository_id=:id"), params)
                    session.execute(text("DELETE FROM repositories WHERE id=:id"), params)


def post(client, name, suffix=""):
    return client.post("/repos", json={"url": f"https://github.com/{name}{suffix}"})


def jobs(factory, repo_id):
    with factory.begin() as session:
        return session.execute(text("SELECT id,status FROM ingestion_jobs WHERE repository_id=:id ORDER BY id"),
                               {"id": repo_id}).mappings().all()


def test_new_registration_enqueues_one_job(fixture):
    client, app, factory, name = fixture
    response = post(client, name)
    assert response.status_code == 202, response.text
    body = response.json()
    assert set(body) == {"repo_id", "status", "message"}
    assert body["status"] == "pending" and "ingestion job" in body["message"]
    rows = jobs(factory, body["repo_id"])
    assert len(rows) == 1 and rows[0]["status"] == "queued"


def test_url_variants_reuse_repository_and_job(fixture):
    client, app, factory, name = fixture
    first = post(client, name)
    assert first.status_code == 202
    repo_id = first.json()["repo_id"]
    for variant in (name.upper(), name + "/", name + ".git", name + ".git/"):
        response = post(client, variant)
        assert response.status_code == 202, response.text
        assert response.json()["repo_id"] == repo_id
    assert len(jobs(factory, repo_id)) == 1


def test_pending_repository_polling_satisfies_response_contract(fixture):
    client, app, factory, name = fixture
    registered = post(client, name)
    assert registered.status_code == 202
    response = client.get(f"/repos/{registered.json()['repo_id']}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["snapshot_id"] is None and body["head_sha"] is None
    assert body["file_count"] is None and body["symbol_count"] is None


def test_enqueue_failure_rolls_back_repository_insert(fixture, monkeypatch):
    client, app, factory, name = fixture
    def fail(*args, **kwargs):
        raise RuntimeError("injected enqueue failure")
    monkeypatch.setattr(repos, "enqueue_job", fail)
    assert post(client, name).status_code == 500
    with factory.begin() as session:
        assert session.execute(text("SELECT count(*) FROM repositories WHERE full_name=:name"),
                               {"name": name}).scalar_one() == 0


def test_ready_repository_is_not_enqueued_again(fixture):
    client, app, factory, name = fixture
    first = post(client, name)
    assert first.status_code == 202
    repo_id = first.json()["repo_id"]
    with factory.begin() as session:
        session.execute(text("UPDATE ingestion_jobs SET status='succeeded' WHERE repository_id=:id"), {"id": repo_id})
        session.execute(text("""
            INSERT INTO repository_snapshots(repository_id,commit_sha,index_version,status,indexed_at)
            VALUES(:id,:sha,'registration-test','ready',clock_timestamp())
        """), {"id": repo_id, "sha": "a" * 40})
    response = post(client, name)
    assert response.status_code == 202
    assert "already indexed" in response.json()["message"]
    assert len(jobs(factory, repo_id)) == 1
    details = client.get(f"/repos/{repo_id}")
    assert details.status_code == 200, details.text
    assert details.json()["status"] == "ready"
    assert details.json()["file_count"] == 0


def test_terminal_failed_job_requires_explicit_review(fixture):
    client, app, factory, name = fixture
    first = post(client, name)
    assert first.status_code == 202
    repo_id = first.json()["repo_id"]
    with factory.begin() as session:
        session.execute(text("UPDATE ingestion_jobs SET status='failed' WHERE repository_id=:id"), {"id": repo_id})
    response = post(client, name)
    assert response.status_code == 409, response.text
    assert len(jobs(factory, repo_id)) == 1


def test_existing_legacy_files_are_not_scheduled_for_replacement(fixture):
    client, app, factory, name = fixture
    first = post(client, name)
    assert first.status_code == 202
    repo_id = first.json()["repo_id"]
    with factory.begin() as session:
        session.execute(text("INSERT INTO files(repository_id,path,language) VALUES(:id,'legacy.py','python')"),
                        {"id": repo_id})
    response = post(client, name)
    assert response.status_code == 409
    assert len(jobs(factory, repo_id)) == 1


def test_parallel_requests_do_not_duplicate_repository_or_job(fixture):
    client, app, factory, name = fixture
    def request():
        with TestClient(app, raise_server_exceptions=False) as other:
            response = post(other, name)
            assert response.status_code == 202, response.text
            return response.json()["repo_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: request(), range(2)))
    assert ids[0] == ids[1]
    assert len(jobs(factory, ids[0])) == 1


def test_invalid_provider_is_rejected_before_registration(fixture):
    client, app, factory, name = fixture
    response = client.post("/repos", json={"url": f"https://example.invalid/{name}"})
    assert response.status_code == 422
    with factory.begin() as session:
        assert session.execute(text("SELECT count(*) FROM repositories WHERE full_name=:name"),
                               {"name": name}).scalar_one() == 0
