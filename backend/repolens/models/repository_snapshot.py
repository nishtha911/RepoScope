from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from repolens.models.base import Base


class RepositorySnapshot(Base):
    __tablename__ = "repository_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)

    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id"),
        index=True,
    )

    commit_sha: Mapped[str] = mapped_column(String(64))

    index_version: Mapped[str] = mapped_column(
        String(100),
        server_default="v1",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        server_default="pending",
    )

    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "commit_sha",
            "index_version",
            name="uq_snapshots_repository_commit_index",
        ),
        CheckConstraint(
            "status IN ('pending', 'indexing', 'ready', 'failed')",
            name="ck_snapshots_status",
        ),
    )