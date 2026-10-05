from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from repolens.models.base import Base


class File(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True) #PK, unique identifier of each file

    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id"),
        index=True,
    ) #FK to repo, which repo owns this file

    path: Mapped[str] = mapped_column(Text) #path
    language: Mapped[str | None] = mapped_column(String(50)) #which programming language

    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "path",
            name="uq_files_repository_path",   #repo_id+path must be unique for each file
        ),
    )