"""add order_number to payments

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-28

"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('payments', sa.Column('order_number', sa.String(20), nullable=True, unique=True))


def downgrade() -> None:
    op.drop_column('payments', 'order_number')
