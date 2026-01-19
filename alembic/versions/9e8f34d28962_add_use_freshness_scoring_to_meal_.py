"""Add use_freshness_scoring to meal_template_slots

Revision ID: 9e8f34d28962
Revises: 68debd74292c
Create Date: 2026-01-18 21:09:30.485656

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9e8f34d28962'
down_revision: Union[str, Sequence[str], None] = '68debd74292c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add use_freshness_scoring column to meal_template_slots table."""
    with op.batch_alter_table('meal_template_slots', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('use_freshness_scoring', sa.Boolean(), nullable=False, server_default='0')
        )


def downgrade() -> None:
    """Remove use_freshness_scoring column from meal_template_slots table."""
    with op.batch_alter_table('meal_template_slots', schema=None) as batch_op:
        batch_op.drop_column('use_freshness_scoring')
