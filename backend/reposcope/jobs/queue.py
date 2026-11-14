"""PostgreSQL ingestion queue.

Every function uses the caller's Session and NEVER commits. Use short
SessionLocal.begin() transactions; commit a claim before doing external work.
Delivery is at-least-once: lease fencing protects job state, not ingestion writes.
"""
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session


class LeaseLostError(RuntimeError):
    """The caller no longer has an unexpired lease for this running job."""


@dataclass(frozen=True)
class ClaimedJob:
    id: int
    repository_id: int
    idempotency_key: str
    attempts: int
    max_attempts: int
    lease_token: str


def _positive(value: int, name: str, maximum: int = 86400) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return value


def enqueue_job(session: Session, repository_id: int, idempotency_key: str, *, max_attempts: int = 3) -> int:
    _positive(repository_id, "repository_id", 2147483647)
    _positive(max_attempts, "max_attempts", 100)
    if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 255:
        raise ValueError("idempotency_key must be a nonblank string of at most 255 characters")
    params = dict(repository_id=repository_id, key=idempotency_key, max_attempts=max_attempts)
    job_id = session.execute(text("""
        INSERT INTO ingestion_jobs (repository_id, idempotency_key, max_attempts)
        VALUES (:repository_id, :key, :max_attempts)
        ON CONFLICT ON CONSTRAINT uq_ingestion_jobs_repository_key DO NOTHING
        RETURNING id
    """), params).scalar_one_or_none()
    if job_id is None:
        # A separate statement sees a concurrent committed insert under READ COMMITTED.
        job_id = session.execute(text("""
            SELECT id FROM ingestion_jobs
            WHERE repository_id = :repository_id AND idempotency_key = :key
        """), params).scalar_one()
    return job_id


def reap_exhausted_jobs(session: Session, *, repository_id: int | None = None, limit: int = 100) -> int:
    _positive(limit, "limit", 1000)
    if repository_id is not None:
        _positive(repository_id, "repository_id", 2147483647)
    rows = session.execute(text("""
        WITH exhausted AS (
            SELECT id FROM ingestion_jobs
            WHERE attempts >= max_attempts
              AND (status = 'queued' OR
                   (status = 'running' AND leased_until <= clock_timestamp()))
              AND (CAST(:repository_id AS integer) IS NULL OR repository_id = CAST(:repository_id AS integer))
            ORDER BY id
            LIMIT :limit
            FOR UPDATE SKIP LOCKED
        )
        UPDATE ingestion_jobs AS j
        SET status = 'failed', lease_token = NULL, leased_until = NULL,
            finished_at = clock_timestamp(), updated_at = clock_timestamp(),
            error_message = 'Attempt limit reached; no active worker lease'
        FROM exhausted AS e WHERE j.id = e.id
        RETURNING j.id
    """), {"repository_id": repository_id, "limit": limit}).all()
    return len(rows)


def claim_next_job(session: Session, *, lease_seconds: int = 300,
                   repository_id: int | None = None) -> ClaimedJob | None:
    _positive(lease_seconds, "lease_seconds")
    if repository_id is not None:
        _positive(repository_id, "repository_id", 2147483647)
    reap_exhausted_jobs(session, repository_id=repository_id)
    row = session.execute(text("""
        WITH candidate AS (
            SELECT id FROM ingestion_jobs
            WHERE attempts < max_attempts
              AND ((status = 'queued' AND available_at <= clock_timestamp()) OR
                   (status = 'running' AND leased_until <= clock_timestamp()))
              AND (CAST(:repository_id AS integer) IS NULL OR repository_id = CAST(:repository_id AS integer))
            ORDER BY available_at, id
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        )
        UPDATE ingestion_jobs AS j
        SET status = 'running', attempts = j.attempts + 1,
            lease_token = :token,
            leased_until = clock_timestamp() + make_interval(secs => :seconds),
            updated_at = clock_timestamp(), finished_at = NULL
        FROM candidate AS c WHERE j.id = c.id
        RETURNING j.id, j.repository_id, j.idempotency_key,
                  j.attempts, j.max_attempts, j.lease_token
    """), {"repository_id": repository_id, "seconds": lease_seconds,
             "token": str(uuid4())}).mappings().one_or_none()
    return ClaimedJob(**dict(row)) if row else None


def _owned_update(session: Session, statement: str, job: ClaimedJob, **params) -> None:
    changed = session.execute(text(statement),
        {"id": job.id, "token": job.lease_token, **params}).scalar_one_or_none()
    if changed is None:
        raise LeaseLostError(f"Job {job.id} has no matching active lease")


def renew_job_lease(session: Session, job: ClaimedJob, *, lease_seconds: int = 300) -> None:
    _positive(lease_seconds, "lease_seconds")
    _owned_update(session, """
        UPDATE ingestion_jobs
        SET leased_until = clock_timestamp() + make_interval(secs => :seconds),
            updated_at = clock_timestamp()
        WHERE id = :id AND status = 'running' AND lease_token = :token
          AND leased_until > clock_timestamp()
        RETURNING id
    """, job, seconds=lease_seconds)


def mark_job_succeeded(session: Session, job: ClaimedJob) -> None:
    _owned_update(session, """
        UPDATE ingestion_jobs
        SET status = 'succeeded', lease_token = NULL, leased_until = NULL,
            error_message = NULL, finished_at = clock_timestamp(),
            updated_at = clock_timestamp()
        WHERE id = :id AND status = 'running' AND lease_token = :token
          AND leased_until > clock_timestamp()
        RETURNING id
    """, job)


def mark_job_failed(session: Session, job: ClaimedJob, *, sanitized_error: str,
                    retry_delay_seconds: int = 30) -> None:
    """Retry or fail permanently. Pass a sanitized message, NEVER raw secrets/URLs."""
    if type(retry_delay_seconds) is not int or not 0 <= retry_delay_seconds <= 86400:
        raise ValueError("retry_delay_seconds must be an integer from 0 to 86400")
    if not isinstance(sanitized_error, str) or not sanitized_error.strip():
        raise ValueError("sanitized_error must be a nonblank string")
    _owned_update(session, """
        UPDATE ingestion_jobs
        SET status = CASE WHEN attempts >= max_attempts THEN 'failed' ELSE 'queued' END,
            available_at = clock_timestamp() + make_interval(secs => :delay),
            lease_token = NULL, leased_until = NULL, error_message = :error,
            finished_at = CASE WHEN attempts >= max_attempts THEN clock_timestamp() ELSE NULL END,
            updated_at = clock_timestamp()
        WHERE id = :id AND status = 'running' AND lease_token = :token
          AND leased_until > clock_timestamp()
        RETURNING id
    """, job, delay=retry_delay_seconds, error=sanitized_error[:2000])
