"""Persist snapshot-scoped recommendation publications (Day 13 Track 2)."""
from alembic import op
import sqlalchemy as sa
revision='d13b7f2a9c40'
down_revision='e10a90c7d201'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('recommendation_runs',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('repo_id',sa.Integer(),sa.ForeignKey('repositories.id',ondelete='CASCADE'),nullable=False),
        sa.Column('snapshot_id',sa.Integer(),sa.ForeignKey('repository_snapshots.id',ondelete='CASCADE'),nullable=False),
        sa.Column('digest',sa.String(64),nullable=False),
        sa.Column('gaps',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.UniqueConstraint('repo_id','snapshot_id','digest',name='uq_recommendation_run_digest'))
    op.create_index('ix_recommendation_runs_repo_id','recommendation_runs',['repo_id'])
    op.create_index('ix_recommendation_runs_snapshot_id','recommendation_runs',['snapshot_id'])
    op.create_table('recommendation_items',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('run_id',sa.Integer(),sa.ForeignKey('recommendation_runs.id',ondelete='CASCADE'),nullable=False),
        sa.Column('rank',sa.Integer(),nullable=False),
        sa.Column('finding',sa.JSON(),nullable=False),
        sa.Column('features',sa.JSON(),nullable=False),
        sa.Column('facts',sa.JSON(),nullable=False),
        sa.Column('evidence',sa.JSON(),nullable=False),
        sa.Column('round_digits',sa.Integer(),nullable=False),
        sa.UniqueConstraint('run_id','rank',name='uq_recommendation_item_rank'))
    op.create_index('ix_recommendation_items_run_id','recommendation_items',['run_id'])


def downgrade():
    op.drop_table('recommendation_items')
    op.drop_table('recommendation_runs')
