"""mentions & rollups & baselines

Revision ID: 0002_mentions
Revises: 0001_users
Create Date: 2025-09-19 20:33:58
"""
from alembic import op
import sqlalchemy as sa
revision='0002_mentions'
down_revision='0001_users'
branch_labels=None
depends_on=None
def upgrade()->None:
    op.create_table('mention_minutes',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('ticker',sa.String(length=16),nullable=False),
        sa.Column('ts',sa.DateTime(),nullable=False),
        sa.Column('mentions',sa.Integer(),nullable=False),
        sa.Column('pos',sa.Integer(),nullable=False,server_default="0"),
        sa.Column('neg',sa.Integer(),nullable=False,server_default="0"),
        sa.Column('neu',sa.Integer(),nullable=False,server_default="0")
    )
    op.create_index('ix_mm_ticker_ts','mention_minutes',['ticker','ts'],unique=True)
    op.create_index('ix_mm_ts','mention_minutes',['ts'])

    op.create_table('daily_rollups',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('d',sa.DateTime(),nullable=False),
        sa.Column('ticker',sa.String(length=16),nullable=False),
        sa.Column('mentions',sa.Integer(),nullable=False),
        sa.Column('pos',sa.Integer(),nullable=False,server_default="0"),
        sa.Column('neg',sa.Integer(),nullable=False,server_default="0"),
        sa.Column('neu',sa.Integer(),nullable=False,server_default="0"),
        sa.Column('interest_score',sa.Float(),nullable=False),
        sa.Column('zscore',sa.Float(),nullable=False)
    )
    op.create_index('ix_dr_d_ticker','daily_rollups',['d','ticker'],unique=True)

    op.create_table('baselines',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('ticker',sa.String(length=16),unique=True,nullable=False),
        sa.Column('window_days',sa.Integer(),nullable=False,server_default="30"),
        sa.Column('mean_mentions',sa.Float(),nullable=False),
        sa.Column('std_mentions',sa.Float(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False,server_default=sa.func.now())
    )
def downgrade()->None:
    op.drop_index('ix_dr_d_ticker',table_name='daily_rollups')
    op.drop_table('daily_rollups')
    op.drop_index('ix_mm_ts',table_name='mention_minutes')
    op.drop_index('ix_mm_ticker_ts',table_name='mention_minutes')
    op.drop_table('mention_minutes')
    op.drop_table('baselines')
