"""Persist immutable, snapshot-scoped recommendation publications."""
from datetime import datetime
from sqlalchemy import ForeignKey, JSON, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from reposcope.models.base import Base


class RecommendationRun(Base):
    __tablename__='recommendation_runs'
    id: Mapped[int]=mapped_column(primary_key=True)
    repo_id: Mapped[int]=mapped_column(ForeignKey('repositories.id',ondelete='CASCADE'),index=True)
    snapshot_id: Mapped[int]=mapped_column(ForeignKey('repository_snapshots.id',ondelete='CASCADE'),index=True)
    digest: Mapped[str]=mapped_column(String(64))
    gaps: Mapped[list]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    __table_args__=(UniqueConstraint('repo_id','snapshot_id','digest',name='uq_recommendation_run_digest'),)


class RecommendationRecord(Base):
    __tablename__='recommendation_items'
    id: Mapped[int]=mapped_column(primary_key=True)
    run_id: Mapped[int]=mapped_column(ForeignKey('recommendation_runs.id',ondelete='CASCADE'),index=True)
    rank: Mapped[int]=mapped_column()
    finding: Mapped[dict]=mapped_column(JSON)
    features: Mapped[dict]=mapped_column(JSON)
    facts: Mapped[dict]=mapped_column(JSON)
    evidence: Mapped[dict]=mapped_column(JSON)
    round_digits: Mapped[int]=mapped_column()
    __table_args__=(UniqueConstraint('run_id','rank',name='uq_recommendation_item_rank'),)
