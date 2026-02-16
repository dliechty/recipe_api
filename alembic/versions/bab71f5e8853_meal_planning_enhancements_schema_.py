"""meal planning enhancements schema updates

Revision ID: bab71f5e8853
Revises: e6b2e972b68b
Create Date: 2026-02-15 17:47:55.947676

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bab71f5e8853'
down_revision: Union[str, Sequence[str], None] = 'e6b2e972b68b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Meal table: rename date -> scheduled_date, add new fields, update status enum
    with op.batch_alter_table('meals', schema=None) as batch_op:
        batch_op.alter_column('date', new_column_name='scheduled_date')
        batch_op.add_column(sa.Column('is_shopped', sa.Boolean(), nullable=False, server_default=sa.text('0')))
        batch_op.add_column(sa.Column('queue_position', sa.Integer(), nullable=True))

    # Recipe table: add last_cooked_at
    with op.batch_alter_table('recipes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_cooked_at', sa.DateTime(), nullable=True))

    # MealTemplate table: add last_used_at
    with op.batch_alter_table('meal_templates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_used_at', sa.DateTime(), nullable=True))

    # Migrate existing status values: Draft -> Queued, Scheduled -> Queued
    op.execute("UPDATE meals SET status = 'Queued' WHERE status IN ('Draft', 'Scheduled')")


def downgrade() -> None:
    """Downgrade schema."""
    # Revert status values: Queued -> Draft, Cancelled -> Draft
    op.execute("UPDATE meals SET status = 'Draft' WHERE status IN ('Queued', 'Cancelled')")

    with op.batch_alter_table('meal_templates', schema=None) as batch_op:
        batch_op.drop_column('last_used_at')

    with op.batch_alter_table('recipes', schema=None) as batch_op:
        batch_op.drop_column('last_cooked_at')

    with op.batch_alter_table('meals', schema=None) as batch_op:
        batch_op.drop_column('queue_position')
        batch_op.drop_column('is_shopped')
        batch_op.alter_column('scheduled_date', new_column_name='date')
