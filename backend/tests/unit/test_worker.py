"""Offline worker lifecycle tests: no DB, Git process, clone, or real model."""
from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from reposcope.ingestion.publishing import PublishedIndex
from reposcope.jobs.queue import ClaimedJob, LeaseLostError
from reposcope.jobs.worker import (
    CommitIdentityError, LeaseHeartbeat, RepositoryURLRejected,
    WorkerServices, run_once, validate_repository_url,
)

SHA = "a" * 40


@pytest.fixture
def fixture(tmp_path):
    job = ClaimedJob(id=1, repository_id=9, idempotency_key="test", attempts=1,
                     max_attempts=3, lease_token="test-lease")
    calls = {"claims": [], "renew": [], "fail": [], "publish": [], "clone": []}
    prepared = object()
    def claim(repo_id, seconds):
        calls["claims"].append((repo_id, seconds))
        return job
    def renew(claimed, seconds):
        calls["renew"].append((claimed.id, seconds))
    def fail(claimed, error_type, delay):
        calls["fail"].append((claimed.id, error_type, delay))
        return "queued"
    def clone(url, destination, **kwargs):
        calls["clone"].append((url, destination, kwargs))
        destination.mkdir()
        (destination / "example.py").write_text("def example():\n    return 1\n", encoding="utf-8")
        return destination
    def prepare(path, *, check_cancelled):
        check_cancelled()
        return prepared
    def publish(claimed, value, sha):
        calls["publish"].append((claimed, value, sha))
        return PublishedIndex(snapshot_id=12, file_count=1, symbol_count=1,
            chunk_count=1, edge_count=0, skipped_non_symbol_edges=0, reused=False)
    services = WorkerServices(claim=claim, renew=renew, fail=fail,
        repository_url=lambda claimed: "https://github.com/example/project",
        clone=clone, prepare=prepare, publish=publish, read_commit=lambda path: SHA)
    return SimpleNamespace(root=tmp_path, services=services, calls=calls, job=job, prepared=prepared)


def test_success_connects_stages_and_cleans_workspace(fixture):
    result = run_once(fixture.services, fixture.root, repository_id=9)
    assert result.status == "succeeded" and result.cleanup_ok
    assert result.published.snapshot_id == 12
    assert fixture.calls["claims"] == [(9, 300)]
    assert fixture.calls["clone"][0][0] == "https://github.com/example/project.git"
    assert fixture.calls["clone"][0][2]["depth"] == 1
    assert fixture.calls["publish"][0][1] is fixture.prepared
    assert fixture.calls["publish"][0][2] == SHA
    assert len(fixture.calls["renew"]) >= 2
    assert not fixture.calls["fail"] and not list(fixture.root.iterdir())


def test_idle_does_not_create_workspace_contents(fixture):
    services = replace(fixture.services, claim=lambda *args: None)
    assert run_once(services, fixture.root).status == "idle"
    assert not fixture.calls["clone"] and not list(fixture.root.iterdir())


def test_stopped_worker_does_not_claim(fixture):
    stop = Event(); stop.set()
    assert run_once(fixture.services, fixture.root, stop_event=stop).status == "stopped"
    assert not fixture.calls["claims"]


def test_clone_failure_is_sanitized_and_retried(fixture):
    def fail_clone(*args, **kwargs):
        raise RuntimeError("password=do-not-log-this")
    services = replace(fixture.services, clone=fail_clone)
    result = run_once(services, fixture.root)
    assert result.status == "queued" and result.error_type == "RuntimeError"
    assert fixture.calls["fail"] == [(1, "RuntimeError", 30)]
    assert "do-not-log-this" not in repr(result)
    assert not fixture.calls["publish"] and not list(fixture.root.iterdir())


def test_prepare_failure_does_not_publish(fixture):
    def broken(*args, **kwargs):
        raise ValueError("bad source")
    result = run_once(replace(fixture.services, prepare=broken), fixture.root)
    assert result.status == "queued"
    assert fixture.calls["fail"][0][1] == "ValueError"
    assert not fixture.calls["publish"] and not list(fixture.root.iterdir())


def test_initial_lease_loss_stops_before_clone(fixture):
    def lost(*args):
        raise LeaseLostError("old token")
    result = run_once(replace(fixture.services, renew=lost), fixture.root)
    assert result.status == "lease_lost"
    assert not fixture.calls["clone"] and not fixture.calls["fail"]


def test_heartbeat_renews_while_preparation_runs(fixture):
    renewed = Event()
    count = []
    def renew(*args):
        count.append(1)
        if len(count) >= 2:
            renewed.set()
    def prepare(path, *, check_cancelled):
        assert renewed.wait(3), "Heartbeat did not run"
        check_cancelled()
        return fixture.prepared
    services = replace(fixture.services, renew=renew, prepare=prepare)
    result = run_once(services, fixture.root, heartbeat_interval=0.01)
    assert result.status == "succeeded" and len(count) >= 3


def test_background_lease_loss_prevents_publication(fixture):
    attempted = Event()
    count = []
    def renew(*args):
        count.append(1)
        if len(count) >= 2:
            attempted.set()
            raise LeaseLostError("expired")
    def prepare(path, *, check_cancelled):
        assert attempted.wait(3)
        # The worker checks the heartbeat after this function returns as well.
        return fixture.prepared
    result = run_once(replace(fixture.services, renew=renew, prepare=prepare),
                      fixture.root, heartbeat_interval=0.01)
    assert result.status == "lease_lost"
    assert not fixture.calls["publish"] and not fixture.calls["fail"]


def test_changed_head_is_rejected(fixture):
    values = iter([SHA, "b" * 40])
    services = replace(fixture.services, read_commit=lambda path: next(values))
    result = run_once(services, fixture.root)
    assert result.status == "queued" and result.error_type == "CommitIdentityError"
    assert not fixture.calls["publish"]


def test_publisher_failure_is_not_reported_as_success(fixture):
    def publish(*args):
        raise RuntimeError("rollback")
    result = run_once(replace(fixture.services, publish=publish), fixture.root)
    assert result.status == "queued" and fixture.calls["fail"]


def test_publisher_lease_loss_does_not_overwrite_job(fixture):
    def publish(*args):
        raise LeaseLostError("expired during transaction")
    result = run_once(replace(fixture.services, publish=publish), fixture.root)
    assert result.status == "lease_lost" and not fixture.calls["fail"]


def test_shutdown_at_checkpoint_requeues_without_publishing(fixture):
    stop = Event()
    def prepare(path, *, check_cancelled):
        stop.set()
        check_cancelled()
    result = run_once(replace(fixture.services, prepare=prepare), fixture.root, stop_event=stop)
    assert result.status == "interrupted"
    assert fixture.calls["fail"] == [(1, "WorkerStopped", 0)]
    assert not fixture.calls["publish"] and result.cleanup_ok


def test_terminal_queue_state_is_preserved(fixture):
    def broken(*args, **kwargs):
        raise RuntimeError()
    services = replace(fixture.services, prepare=broken, fail=lambda *args: "failed")
    assert run_once(services, fixture.root).status == "failed"


def test_failure_recording_error_is_explicit(fixture):
    def broken(*args, **kwargs):
        raise RuntimeError()
    services = replace(fixture.services, prepare=broken, fail=broken)
    assert run_once(services, fixture.root).status == "failure_recording_error"


@pytest.mark.parametrize("url", [
    "http://github.com/example/repo", "https://gitlab.com/example/repo",
    "file:///tmp/repo", "git@github.com:example/repo.git",
    "https://user:password@github.com/example/repo",
    "https://github.com/example/repo?token=secret",
    "https://github.com/example/repo#fragment",
    "https://github.com/example/repo/tree/main",
    "https://github.com/owner/..", "https://github.com:444/example/repo",
    "https://github.com/example/repo\n", "https://127.0.0.1/example/repo",
])
def test_rejects_unsupported_repository_urls(url):
    with pytest.raises(RepositoryURLRejected):
        validate_repository_url(url)


def test_normalizes_supported_url():
    assert validate_repository_url("https://github.com/example/repo/") == "https://github.com/example/repo.git"
    assert validate_repository_url("https://github.com/example/repo.git") == "https://github.com/example/repo.git"


def test_invalid_worker_options_do_not_claim(fixture):
    with pytest.raises(ValueError):
        run_once(fixture.services, fixture.root, lease_seconds=0)
    with pytest.raises(ValueError):
        run_once(fixture.services, fixture.root, heartbeat_interval=200)
    assert not fixture.calls["claims"]


def test_outside_clone_destination_is_rejected(fixture, tmp_path):
    outside = tmp_path.parent
    def clone(*args, **kwargs):
        return outside
    result = run_once(replace(fixture.services, clone=clone), fixture.root)
    assert result.status == "queued" and not fixture.calls["publish"]


def test_cleanup_failure_is_visible_without_changing_success(fixture, monkeypatch):
    import reposcope.jobs.worker as worker
    def unsafe(*args, **kwargs):
        raise OSError("cannot safely delete")
    monkeypatch.setattr(worker, "_cleanup_owned_destination", unsafe)
    result = run_once(fixture.services, fixture.root)
    assert result.status == "succeeded" and result.cleanup_ok is False
    assert not fixture.calls["fail"]
