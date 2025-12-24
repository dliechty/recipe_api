"""Add description to recipes

Revision ID: e42718e24c6c
Revises: 50114936ed77
Create Date: 2025-12-24 15:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e42718e24c6c'
down_revision: Union[str, Sequence[str], None] = '50114936ed77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recipes', sa.Column('description', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('recipes', 'description')
