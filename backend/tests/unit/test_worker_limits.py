"""Unit tests for worker execution timeouts and memory limits (Day 17)."""
import time
from unittest.mock import patch
import pytest

from reposcope.jobs.queue import ClaimedJob
from reposcope.jobs.worker import (
    WorkerServices, WorkerOutcome, JobDeadlineExceeded,
    WorkerMemoryExceededError, run_once,
)

SHA = "b" * 40


@pytest.fixture
def mock_services(tmp_path):
    job = ClaimedJob(
        id=42,
        repository_id=1,
        idempotency_key="limit-test",
        attempts=1,
        max_attempts=3,
        lease_token="lease-abc",
    )
    failed_calls = []

    def claim(repo_id, seconds):
        return job

    def renew(claimed, seconds):
        pass

    def fail(claimed, error_type, delay):
        failed_calls.append((claimed.id, error_type, delay))
        return "failed"

    def clone(url, destination, **kwargs):
        destination.mkdir(parents=True, exist_ok=True)
        return destination

    def prepare(path, *, check_cancelled):
        check_cancelled()
        return object()

    def publish(claimed, prepared, commit_sha):
        return None

    def read_commit(path):
        return SHA

    services = WorkerServices(
        claim=claim,
        renew=renew,
        fail=fail,
        repository_url=lambda j: "https://github.com/acme/repo.git",
        clone=clone,
        prepare=prepare,
        publish=publish,
        read_commit=read_commit,
    )
    return services, failed_calls


def test_worker_fails_when_job_deadline_exceeded(tmp_path, mock_services):
    services, failed_calls = mock_services

    with patch("time.monotonic", side_effect=[0.0, 0.0, 50.0, 100.0, 200.0]):
        outcome = run_once(
            services,
            tmp_path,
            max_job_seconds=10.0,
            clone_timeout_seconds=5.0,
        )

    assert outcome.status == "failed"
    assert outcome.error_type == "JobDeadlineExceeded"
    assert len(failed_calls) == 1
    assert failed_calls[0][1] == "JobDeadlineExceeded"


def test_worker_fails_when_memory_limit_exceeded(tmp_path, mock_services):
    services, failed_calls = mock_services

    with patch("reposcope.jobs.worker._get_current_memory_mb", return_value=1500.0):
        outcome = run_once(
            services,
            tmp_path,
            max_memory_mb=512.0,
        )

    assert outcome.status == "failed"
    assert outcome.error_type == "WorkerMemoryExceededError"
    assert len(failed_calls) == 1
    assert failed_calls[0][1] == "WorkerMemoryExceededError"
