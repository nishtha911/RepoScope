"""Persist structured PR impact analyses and grounded executive summaries (Day 14 Track 1)."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from sqlalchemy import ForeignKey, JSON, DateTime, String, Float, Text, select, func
from sqlalchemy.orm import Mapped, mapped_column, Session

from reposcope.models.base import Base
from reposcope.contracts.pr_report import PRAnalysisReport


class PRAnalysisRecord(Base):
    """SQLAlchemy model for immutable persisted PR impact reports."""

    __tablename__ = 'pr_analyses'

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey('repositories.id', ondelete='CASCADE'), index=True
    )
    pr_number: Mapped[int | None] = mapped_column(nullable=True, index=True)
    pr_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    base_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    head_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    report_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


def save_pr_analysis(session: Session, report: PRAnalysisReport) -> PRAnalysisRecord:
    """Persist a validated PRAnalysisReport into the database."""
    record = PRAnalysisRecord(
        repository_id=report.repository_id,
        pr_number=report.pr_number,
        pr_url=str(report.pr_url) if report.pr_url else None,
        base_sha=report.base_revision,
        head_sha=report.head_revision,
        risk_level=report.risk_level,
        risk_score=report.risk_score,
        report_json=report.model_dump(mode='json'),
        summary=report.executive_summary,
    )
    session.add(record)
    session.flush()
    return record


def get_pr_analysis(
    session: Session,
    repository_id: int,
    *,
    pr_number: int | None = None,
    analysis_id: int | None = None,
) -> PRAnalysisRecord | None:
    """Retrieve persisted PR analysis by ID or PR number."""
    query = select(PRAnalysisRecord).where(
        PRAnalysisRecord.repository_id == repository_id
    )
    if analysis_id is not None:
        query = query.where(PRAnalysisRecord.id == analysis_id)
    elif pr_number is not None:
        query = query.where(PRAnalysisRecord.pr_number == pr_number).order_by(
            PRAnalysisRecord.id.desc()
        )
    return session.scalars(query).first()
