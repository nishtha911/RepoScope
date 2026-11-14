"""Persist ingestion progress for repository status polling.

Revision ID: 9a4c6e7f1023
Revises: 8f3a2c6d0e91
"""
from alembic import op
import sqlalchemy as sa

revision = "9a4c6e7f1023"
down_revision = "8f3a2c6d0e91"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ingestion_jobs",
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("progress_stage", sa.String(40), nullable=False, server_default="queued"),
    )
    op.create_check_constraint(
        "ck_ingestion_jobs_progress",
        "ingestion_jobs",
        "progress_percent >= 0 AND progress_percent <= 100",
    )


def downgrade():
    op.drop_constraint("ck_ingestion_jobs_progress", "ingestion_jobs", type_="check")
    op.drop_column("ingestion_jobs", "progress_stage")
    op.drop_column("ingestion_jobs", "progress_percent")
