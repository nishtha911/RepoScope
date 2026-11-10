"""Persist structured PR analyses and grounded executive summaries (Day 14 Track 1)."""
from alembic import op
import sqlalchemy as sa

revision = 'e42c7f1a8b90'
down_revision = 'd13b7f2a9c40'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pr_analyses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'repository_id',
            sa.Integer(),
            sa.ForeignKey('repositories.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('pr_number', sa.Integer(), nullable=True),
        sa.Column('pr_url', sa.String(512), nullable=True),
        sa.Column('base_sha', sa.String(64), nullable=True),
        sa.Column('head_sha', sa.String(64), nullable=True),
        sa.Column('risk_level', sa.String(32), nullable=False),
        sa.Column('risk_score', sa.Float(), nullable=True),
        sa.Column('report_json', sa.JSON(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index('ix_pr_analyses_repository_id', 'pr_analyses', ['repository_id'])
    op.create_index('ix_pr_analyses_pr_number', 'pr_analyses', ['pr_number'])


def downgrade():
    op.drop_table('pr_analyses')
