"""Add repository snapshots and nullable file snapshot link.

Revision ID: f578caba5116
Revises: 3e17eecfecf0
Create Date: 2026-10-06 12:28:51.723560
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f578caba5116"
down_revision: Union[str, Sequence[str], None] = "3e17eecfecf0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "repository_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column(
            "index_version",
            sa.String(length=100),
            server_default="v1",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'indexing', 'ready', 'failed')",
            name="ck_snapshots_status",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "repository_id",
            "commit_sha",
            "index_version",
            name="uq_snapshots_repository_commit_index",
        ),
    )

    op.create_index(
        op.f("ix_repository_snapshots_repository_id"),
        "repository_snapshots",
        ["repository_id"],
        unique=False,
    )

    op.add_column(
        "files",
        sa.Column("snapshot_id", sa.Integer(), nullable=True),
    )

    op.create_index(
        op.f("ix_files_snapshot_id"),
        "files",
        ["snapshot_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_files_snapshot_id",
        "files",
        "repository_snapshots",
        ["snapshot_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "fk_files_snapshot_id",
        "files",
        type_="foreignkey",
    )

    op.drop_index(
        op.f("ix_files_snapshot_id"),
        table_name="files",
    )

    op.drop_column("files", "snapshot_id")

    op.drop_index(
        op.f("ix_repository_snapshots_repository_id"),
        table_name="repository_snapshots",
    )

    op.drop_table("repository_snapshots")