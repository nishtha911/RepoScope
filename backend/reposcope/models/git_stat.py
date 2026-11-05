"""Latest per-path Git churn measurement for each repository."""
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from reposcope.models.base import Base


class GitStat(Base):
    __tablename__ = "git_stats"
    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(Text)
    commit_count_90d: Mapped[int] = mapped_column(Integer, nullable=False)
    distinct_authors_90d: Mapped[int] = mapped_column(Integer, nullable=False)
    last_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bugfix_commit_count_90d: Mapped[int] = mapped_column(Integer, nullable=False)
    bugfix_frequency_90d: Mapped[float] = mapped_column(Float, nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    head_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    bugfix_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (
        UniqueConstraint("repository_id", "path", name="uq_git_stats_repository_path"),
        CheckConstraint("commit_count_90d >= 0", name="ck_git_stats_commits"),
        CheckConstraint("distinct_authors_90d >= 0 AND distinct_authors_90d <= commit_count_90d", name="ck_git_stats_authors"),
        CheckConstraint("bugfix_commit_count_90d >= 0 AND bugfix_commit_count_90d <= commit_count_90d", name="ck_git_stats_bugfixes"),
        CheckConstraint("bugfix_frequency_90d >= 0 AND bugfix_frequency_90d <= 1", name="ck_git_stats_frequency"),
        CheckConstraint("window_start <= window_end", name="ck_git_stats_window"),
    )
