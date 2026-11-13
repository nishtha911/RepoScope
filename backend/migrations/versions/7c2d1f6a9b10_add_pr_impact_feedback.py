"""Persist PR impact review feedback."""

from alembic import op
import sqlalchemy as sa

revision = "7c2d1f6a9b10"
down_revision = "e42c7f1a8b90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pr_impact_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("analysis_key", sa.String(length=512), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_pr_impact_feedback_repository_id",
        "pr_impact_feedback",
        ["repository_id"],
    )
    op.create_index(
        "ix_pr_impact_feedback_analysis_key",
        "pr_impact_feedback",
        ["analysis_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_pr_impact_feedback_analysis_key", table_name="pr_impact_feedback")
    op.drop_index("ix_pr_impact_feedback_repository_id", table_name="pr_impact_feedback")
    op.drop_table("pr_impact_feedback")
