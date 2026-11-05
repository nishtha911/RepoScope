"""Add repository-scoped 90-day per-file Git statistics.

Revision ID: e10a90c7d201
Revises: d5e2a6b7c801
"""
from alembic import op
import sqlalchemy as sa

revision = "e10a90c7d201"
down_revision = "d5e2a6b7c801"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "git_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("commit_count_90d", sa.Integer(), nullable=False),
        sa.Column("distinct_authors_90d", sa.Integer(), nullable=False),
        sa.Column("last_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bugfix_commit_count_90d", sa.Integer(), nullable=False),
        sa.Column("bugfix_frequency_90d", sa.Float(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("head_sha", sa.String(64), nullable=False),
        sa.Column("bugfix_rule_version", sa.String(64), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("repository_id", "path", name="uq_git_stats_repository_path"),
        sa.CheckConstraint("commit_count_90d >= 0", name="ck_git_stats_commits"),
        sa.CheckConstraint("distinct_authors_90d >= 0 AND distinct_authors_90d <= commit_count_90d", name="ck_git_stats_authors"),
        sa.CheckConstraint("bugfix_commit_count_90d >= 0 AND bugfix_commit_count_90d <= commit_count_90d", name="ck_git_stats_bugfixes"),
        sa.CheckConstraint("bugfix_frequency_90d >= 0 AND bugfix_frequency_90d <= 1", name="ck_git_stats_frequency"),
        sa.CheckConstraint("window_start <= window_end", name="ck_git_stats_window"),
    )
    op.create_index("ix_git_stats_repository_id", "git_stats", ["repository_id"])


def downgrade():
    op.drop_index("ix_git_stats_repository_id", table_name="git_stats")
    op.drop_table("git_stats")
