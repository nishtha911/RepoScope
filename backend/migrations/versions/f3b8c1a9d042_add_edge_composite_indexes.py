"""Add composite indexes on edges for reverse reachability and caller queries.

Revision ID: f3b8c1a9d042
Revises: 9a4c6e7f1023
"""
from alembic import op

revision = "f3b8c1a9d042"
down_revision = "9a4c6e7f1023"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_edges_target_kind_source",
        "edges",
        ["target_symbol_id", "kind", "source_symbol_id"],
        unique=False,
    )
    op.create_index(
        "ix_edges_source_kind_target",
        "edges",
        ["source_symbol_id", "kind", "target_symbol_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_edges_source_kind_target", table_name="edges")
    op.drop_index("ix_edges_target_kind_source", table_name="edges")
