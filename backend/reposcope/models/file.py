from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from reposcope.models.base import Base


class File(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True)

    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id"),
        index=True,
    )

    snapshot_id: Mapped[int | None] = mapped_column(
    ForeignKey(
        "repository_snapshots.id",
        name="fk_files_snapshot_id",
    ),
    nullable=True,
    index=True,
)

    path: Mapped[str] = mapped_column(Text)

    language: Mapped[str | None] = mapped_column(String(50))

    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "path",
            name="uq_files_repository_path",
        ),
    )