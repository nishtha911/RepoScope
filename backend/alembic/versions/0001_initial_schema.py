"""Create the initial repository graph schema."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=512), nullable=False),
        sa.Column("remote_url", sa.Text(), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=True),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("full_name"),
    )
    op.create_table(
        "files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=64), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.CheckConstraint("size_bytes >= 0", name="ck_files_size_nonnegative"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repository_id", "path", name="uq_files_repository_path"),
    )
    op.create_index("ix_files_repository_id", "files", ["repository_id"])
    op.create_table(
        "symbols",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("qualified_name", sa.Text(), nullable=True),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("docstring", sa.Text(), nullable=True),
        sa.Column("source_code", sa.Text(), nullable=True),
        sa.CheckConstraint("start_line >= 1", name="ck_symbols_start_line"),
        sa.CheckConstraint("end_line >= start_line", name="ck_symbols_line_range"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_symbols_file_id", "symbols", ["file_id"])
    op.create_index("ix_symbols_file_name", "symbols", ["file_id", "name"])
    op.create_table(
        "edges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_symbol_id", sa.Integer(), nullable=False),
        sa.Column("target_symbol_id", sa.Integer(), nullable=False),
        sa.Column("edge_type", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["source_symbol_id"], ["symbols.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_symbol_id"], ["symbols.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_symbol_id",
            "target_symbol_id",
            "edge_type",
            name="uq_edges_source_target_type",
        ),
    )
    op.create_index("ix_edges_source_symbol_id", "edges", ["source_symbol_id"])
    op.create_index("ix_edges_target_symbol_id", "edges", ["target_symbol_id"])


def downgrade() -> None:
    op.drop_index("ix_edges_target_symbol_id", table_name="edges")
    op.drop_index("ix_edges_source_symbol_id", table_name="edges")
    op.drop_table("edges")
    op.drop_index("ix_symbols_file_name", table_name="symbols")
    op.drop_index("ix_symbols_file_id", table_name="symbols")
    op.drop_table("symbols")
    op.drop_index("ix_files_repository_id", table_name="files")
    op.drop_table("files")
    op.drop_table("repositories")