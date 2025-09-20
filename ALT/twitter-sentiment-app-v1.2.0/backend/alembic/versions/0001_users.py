"""create users table

Revision ID: 0001_users
Revises: 
Create Date: 2025-09-19 16:42:36
"""
from alembic import op
import sqlalchemy as sa
revision = '0001_users'
down_revision = None
branch_labels = None
depends_on = None
def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('username', sa.String(length=255), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('pro', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    op.create_index('ix_users_username', 'users', ['username'], unique=True)
def downgrade() -> None:
    op.drop_index('ix_users_username', table_name='users')
    op.drop_table('users')