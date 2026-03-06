"""add api_key plaintext to auth

Revision ID: a1b2c3d4e5f6
Revises: f68d8965d452
Create Date: 2026-03-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f68d8965d452'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('auth', sa.Column('api_key', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('auth', 'api_key')
