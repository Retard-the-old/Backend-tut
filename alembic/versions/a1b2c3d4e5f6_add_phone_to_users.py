"""add phone to users

Revision ID: a1b2c3d4e5f6
Revises: 0c6d1bba9306
Create Date: 2026-04-07 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '0c6d1bba9306'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('phone', sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'phone')
