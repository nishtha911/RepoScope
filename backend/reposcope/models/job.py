"""Durable ingestion job state; execution is handled by the jobs package."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from reposcope.models.base import Base


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="queued")
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    progress_stage: Mapped[str] = mapped_column(String(40), nullable=False, server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("repository_id", "idempotency_key", name="uq_ingestion_jobs_repository_key"),
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name='ck_ingestion_jobs_status'),
        CheckConstraint("progress_percent >= 0 AND progress_percent <= 100", name='ck_ingestion_jobs_progress'),
        CheckConstraint('attempts >= 0 AND max_attempts > 0 AND attempts <= max_attempts', name='ck_ingestion_jobs_attempts'),
        CheckConstraint("(status = 'running' AND lease_token IS NOT NULL AND leased_until IS NOT NULL) OR (status <> 'running' AND lease_token IS NULL AND leased_until IS NULL)", name='ck_ingestion_jobs_lease'),
        Index("ix_ingestion_jobs_repository_id", "repository_id"),
        Index("ix_ingestion_jobs_ready", "status", "available_at", "id"),
        Index("ix_ingestion_jobs_leased_until", "leased_until"),
    )
