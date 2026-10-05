from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Edge(Base):
    __tablename__ = "edges"
    __table_args__ = (
        UniqueConstraint(
            "source_symbol_id",
            "target_symbol_id",
            "edge_type",
            name="uq_edges_source_target_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    source_symbol_id: Mapped[int] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_symbol_id: Mapped[int] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    edge_type: Mapped[str] = mapped_column(String(64), nullable=False)


__all__ = ["Edge"]