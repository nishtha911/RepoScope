"""Single-job-at-a-time PostgreSQL worker for initial Python indexing.

Requires a private, pre-existing workspace and an explicitly verified DB host.
Only credential-free HTTPS github.com owner/repo URLs are accepted. Git and
its environment/configuration still require a trusted service environment;
this module is NOT a network sandbox. Never executes repository Python code.
"""
import argparse
from dataclasses import asdict, dataclass, replace
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
from threading import Event, Thread
import time
from typing import Callable
from urllib.parse import urlsplit

from reposcope.ingestion.clone import (
    clone_repository, _cleanup_owned_destination, _directory_identity,
    _reject_linked_components,
)
from reposcope.ingestion.index_preparation import prepare_python_index
from reposcope.ingestion.publishing import PublishedIndex, publish_prepared_index
from reposcope.jobs.queue import (
    LeaseLostError, claim_next_job, mark_job_failed, renew_job_lease,
)


class WorkerStopped(RuntimeError):
    pass


class JobDeadlineExceeded(RuntimeError):
    pass


class RepositoryURLRejected(ValueError):
    pass


class CommitIdentityError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkerServices:
    claim: Callable
    renew: Callable
    fail: Callable
    repository_url: Callable
    clone: Callable
    prepare: Callable
    publish: Callable
    read_commit: Callable


@dataclass(frozen=True)
class WorkerOutcome:
    status: str
    job_id: int | None = None
    error_type: str | None = None
    published: PublishedIndex | None = None
    cleanup_ok: bool = True


def validate_repository_url(value: str) -> str:
    try:
        if not isinstance(value, str) or any(ord(c) <= 32 or ord(c) >= 127 for c in value):
            raise ValueError()
        url = urlsplit(value)
        if (url.scheme != "https" or url.hostname != "github.com"
                or url.port not in (None, 443) or url.username is not None
                or url.password is not None or url.query or url.fragment):
            raise ValueError()
        parts = url.path.strip("/").split("/")
        if len(parts) != 2:
            raise ValueError()
        owner, repo = parts
        if repo.endswith(".git"):
            repo = repo[:-4]
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", owner)
                or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", repo)
                or repo in {".", ".."}):
            raise ValueError()
        return f"https://github.com/{owner}/{repo}.git"
    except (ValueError, TypeError, AttributeError) as exc:
        raise RepositoryURLRejected("Only public-style HTTPS GitHub repository URLs are accepted") from None


def read_git_commit(repository: Path) -> str:
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        environment.pop(key, None)
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(repository),
         "rev-parse", "--verify", "HEAD^{commit}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=15, shell=False, env=environment,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value):
        raise CommitIdentityError("Could not establish clone commit identity")
    return value


def _workspace(value) -> Path:
    path = Path(value)
    if ".." in path.parts:
        raise ValueError("Workspace traversal is not allowed")
    _reject_linked_components(path.absolute())
    path = path.resolve(strict=True)
    if not path.is_dir():
        raise ValueError("Workspace must be an existing private directory")
    return path


class LeaseHeartbeat:
    """Fail closed on any renewal error; never share a Session across threads."""
    def __init__(self, renew: Callable, interval: float):
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("Heartbeat interval must be positive and finite")
        self._renew = renew
        self._interval = interval
        self._stop = Event()
        self._lost = Event()
        self._thread = None

    def start(self):
        try:
            self._renew()
        except Exception:
            self._lost.set()
            raise LeaseLostError("Initial lease renewal failed") from None
        self._thread = Thread(target=self._run, daemon=True, name="reposcope-lease-heartbeat")
        self._thread.start()

    def _run(self):
        while not self._stop.wait(self._interval):
            try:
                self._renew()
            except Exception:
                self._lost.set()
                return

    def check(self):
        if self._lost.is_set():
            raise LeaseLostError("Worker can no longer establish job ownership")

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=7)
            if self._thread.is_alive():
                self._lost.set()


def build_services(session_factory) -> WorkerServices:
    def claim(repository_id, lease_seconds):
        with session_factory.begin() as session:
            return claim_next_job(session, repository_id=repository_id, lease_seconds=lease_seconds)

    def renew(job, lease_seconds):
        from sqlalchemy import text
        with session_factory.begin() as session:
            session.execute(text("SET LOCAL lock_timeout = '2s'"))
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            renew_job_lease(session, job, lease_seconds=lease_seconds)

    def fail(job, error_type, retry_delay_seconds):
        from sqlalchemy import text
        with session_factory.begin() as session:
            session.execute(text("SET LOCAL lock_timeout = '2s'"))
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            mark_job_failed(session, job, sanitized_error=error_type,
                            retry_delay_seconds=retry_delay_seconds)
            return session.execute(text("SELECT status FROM ingestion_jobs WHERE id=:id"),
                                   {"id": job.id}).scalar_one()

    def repository_url(job):
        from reposcope.models import Repository
        with session_factory() as session:
            repository = session.get(Repository, job.repository_id)
            if repository is None:
                raise ValueError("Repository no longer exists")
            return repository.remote_url

    def publish(job, prepared, commit_sha):
        return publish_prepared_index(job, prepared, commit_sha=commit_sha,
                                      session_factory=session_factory)

    return WorkerServices(claim=claim, renew=renew, fail=fail,
        repository_url=repository_url, clone=clone_repository,
        prepare=prepare_python_index, publish=publish, read_commit=read_git_commit)


def run_once(services: WorkerServices, workspace, *, repository_id=None,
             lease_seconds=300, heartbeat_interval=None, clone_timeout_seconds=120,
             max_job_seconds=1800, stop_event=None) -> WorkerOutcome:
    """Consume at most one job. Source processing must remain cooperative.

    Shutdown/deadline checks run between stages and embedding batches, not inside
    blocking Git/model calls. A forced kill relies on lease expiry and recovery.
    The heartbeat stops before publication, followed by a final renewal; the
    publisher fences its transaction and rolls back if that lease expires.
    """
    if type(lease_seconds) is not int or not 30 <= lease_seconds <= 86400:
        raise ValueError("lease_seconds must be an integer from 30 to 86400")
    if repository_id is not None and (type(repository_id) is not int or repository_id <= 0):
        raise ValueError("repository_id must be a positive integer")
    for name, value in (("clone_timeout_seconds", clone_timeout_seconds),
                        ("max_job_seconds", max_job_seconds)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be positive and finite")
    interval = lease_seconds / 3 if heartbeat_interval is None else heartbeat_interval
    if (isinstance(interval, bool) or not isinstance(interval, (int, float))
            or not math.isfinite(interval) or not 0 < interval < lease_seconds / 2):
        raise ValueError("Heartbeat interval must be positive and less than half the lease")
    root = _workspace(workspace)
    root_identity = _directory_identity(root)
    stop = stop_event if stop_event is not None else Event()
    if stop.is_set():
        return WorkerOutcome(status="stopped")
    job = services.claim(repository_id, lease_seconds)
    if job is None:
        return WorkerOutcome(status="idle")
    heartbeat = LeaseHeartbeat(lambda: services.renew(job, lease_seconds), interval)
    started = time.monotonic()
    attempt = None
    attempt_identity = None
    outcome = WorkerOutcome(status="failed", job_id=job.id)

    def checkpoint():
        heartbeat.check()
        if stop.is_set():
            raise WorkerStopped()
        if time.monotonic() - started > max_job_seconds:
            raise JobDeadlineExceeded()

    try:
        heartbeat.start()
        checkpoint()
        url = validate_repository_url(services.repository_url(job))
        attempt = Path(tempfile.mkdtemp(prefix=f"job-{job.id}-", dir=root))
        _reject_linked_components(attempt)
        attempt_identity = _directory_identity(attempt)
        destination = attempt / "repository"
        cloned = Path(services.clone(url, destination, depth=1,
            workspace_root=attempt, timeout_seconds=clone_timeout_seconds))
        _reject_linked_components(cloned)
        if cloned.resolve(strict=True) != destination:
            raise ValueError("Clone returned an unexpected destination")
        checkpoint()
        commit_sha = services.read_commit(cloned)
        prepared = services.prepare(cloned, check_cancelled=checkpoint)
        checkpoint()
        if services.read_commit(cloned) != commit_sha:
            raise CommitIdentityError("Clone HEAD changed during preparation")
        heartbeat.stop()
        checkpoint()
        services.renew(job, lease_seconds)
        checkpoint()
        published = services.publish(job, prepared, commit_sha)
        outcome = WorkerOutcome(status="succeeded", job_id=job.id, published=published)
    except LeaseLostError:
        outcome = WorkerOutcome(status="lease_lost", job_id=job.id, error_type="LeaseLostError")
    except Exception as exc:
        heartbeat.stop()
        # Never persist or log raw exception messages, source text, Git stderr,
        # repository URLs, connection URLs, or exception chains.
        error_type = type(exc).__name__
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,99}", error_type):
            error_type = "WorkerError"
        try:
            heartbeat.check()
            delay = 0 if isinstance(exc, WorkerStopped) else min(30 * 2 ** (job.attempts - 1), 900)
            state = services.fail(job, error_type, delay)
            status = "interrupted" if isinstance(exc, WorkerStopped) else state
            outcome = WorkerOutcome(status=status, job_id=job.id, error_type=error_type)
        except LeaseLostError:
            outcome = WorkerOutcome(status="lease_lost", job_id=job.id, error_type="LeaseLostError")
        except Exception:
            outcome = WorkerOutcome(status="failure_recording_error", job_id=job.id, error_type=error_type)
    finally:
        heartbeat.stop()
        if attempt is not None:
            try:
                if attempt_identity is None:
                    raise ValueError("Attempt ownership was not established")
                _cleanup_owned_destination(attempt, root, root_identity, attempt_identity)
            except Exception:
                outcome = replace(outcome, cleanup_ok=False)
    return outcome


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=os.getenv("REPOSCOPE_WORKSPACE"))
    parser.add_argument("--expected-db-host", default=os.getenv("REPOSCOPE_EXPECTED_DB_HOST"))
    parser.add_argument("--repo-id", type=int)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--lease-seconds", type=int, default=300)
    parser.add_argument("--clone-timeout-seconds", type=float, default=120)
    parser.add_argument("--max-job-seconds", type=float, default=1800)
    args = parser.parse_args(argv)
    if not args.workspace or not args.expected_db_host:
        parser.error("Specify a private workspace and the verified database hostname")
    if not math.isfinite(args.poll_seconds) or args.poll_seconds <= 0:
        parser.error("poll-seconds must be positive and finite")
    if not 30 <= args.lease_seconds <= 86400:
        parser.error("lease-seconds must be between 30 and 86400")
    if args.repo_id is not None and args.repo_id <= 0:
        parser.error("repo-id must be positive")
    for value in (args.clone_timeout_seconds, args.max_job_seconds):
        if not math.isfinite(value) or value <= 0:
            parser.error("timeouts must be positive and finite")
    if shutil.which("git") is None:
        parser.error("Git executable was not found")
    if any(os.getenv(key) for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")):
        parser.error("Unset Git repository-location overrides before starting the worker")
    try:
        workspace = _workspace(args.workspace)
    except Exception:
        parser.error("Workspace must be an existing, unlinked private directory")
    os.environ.setdefault("PGCONNECT_TIMEOUT", "10")
    from reposcope.db import engine, SessionLocal
    if engine.url.host != args.expected_db_host:
        parser.error("Configured database hostname does not match expected-db-host")
    services = build_services(SessionLocal)
    stop = Event()
    def request_stop(signum, frame):
        stop.set()
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        while not stop.is_set():
            try:
                result = run_once(services, workspace, repository_id=args.repo_id,
                    lease_seconds=args.lease_seconds, clone_timeout_seconds=args.clone_timeout_seconds,
                    max_job_seconds=args.max_job_seconds, stop_event=stop)
                print(json.dumps(asdict(result)), flush=True)
                if not result.cleanup_ok:
                    return 3  # Do not accumulate clones after unsafe/failed cleanup.
                if args.once:
                    return 0 if result.status in {"succeeded", "idle", "stopped"} else 1
            except Exception as exc:
                print(json.dumps({"status": "infrastructure_error", "error_type": type(exc).__name__}), flush=True)
                if args.once:
                    return 2
                result = None
            if result is None or result.status != "succeeded":
                stop.wait(args.poll_seconds)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
