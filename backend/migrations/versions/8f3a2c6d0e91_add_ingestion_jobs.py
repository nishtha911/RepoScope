"""Add durable ingestion job storage.

Revision ID: 8f3a2c6d0e91
Revises: 7c2d1f6a9b10
"""
from alembic import op
import sqlalchemy as sa

revision = "8f3a2c6d0e91"
down_revision = "7c2d1f6a9b10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("lease_token", sa.String(36), nullable=True),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("repository_id", "idempotency_key", name="uq_ingestion_jobs_repository_key"),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name='ck_ingestion_jobs_status'),
        sa.CheckConstraint('attempts >= 0 AND max_attempts > 0 AND attempts <= max_attempts', name='ck_ingestion_jobs_attempts'),
        sa.CheckConstraint("(status = 'running' AND lease_token IS NOT NULL AND leased_until IS NOT NULL) OR (status <> 'running' AND lease_token IS NULL AND leased_until IS NULL)", name='ck_ingestion_jobs_lease'),
    )
    op.create_index("ix_ingestion_jobs_repository_id", "ingestion_jobs", ["repository_id"])
    op.create_index("ix_ingestion_jobs_ready", "ingestion_jobs", ["status", "available_at", "id"])
    op.create_index("ix_ingestion_jobs_leased_until", "ingestion_jobs", ["leased_until"])


def downgrade():
    op.drop_index("ix_ingestion_jobs_leased_until", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_ready", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_repository_id", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
