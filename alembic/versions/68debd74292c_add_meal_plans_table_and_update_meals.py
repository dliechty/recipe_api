"""Add meal_plans table and update meals with meal_plan_id and pinned

Revision ID: 68debd74292c
Revises: 20fdb31754ac
Create Date: 2026-01-18 20:33:13.842245

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '68debd74292c'
down_revision: Union[str, Sequence[str], None] = '20fdb31754ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create meal_plans table
    op.create_table(
        'meal_plans',
        sa.Column('id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('start_date', sa.DateTime(), nullable=False),
        sa.Column('end_date', sa.DateTime(), nullable=False),
        sa.Column('status', sa.Enum('DRAFT', 'FINALIZED', name='mealplanstatus'), nullable=False),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_meal_plans_id'), 'meal_plans', ['id'], unique=False)
    op.create_index(op.f('ix_meal_plans_user_id'), 'meal_plans', ['user_id'], unique=False)

    # Add meal_plan_id and pinned columns to meals table
    with op.batch_alter_table('meals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('meal_plan_id', sa.Uuid(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column('pinned', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.create_foreign_key(
            'fk_meals_meal_plan_id_meal_plans',
            'meal_plans',
            ['meal_plan_id'],
            ['id']
        )
        batch_op.create_index(op.f('ix_meals_meal_plan_id'), ['meal_plan_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Remove meal_plan_id and pinned columns from meals
    with op.batch_alter_table('meals', schema=None) as batch_op:
        batch_op.drop_index(op.f('ix_meals_meal_plan_id'))
        batch_op.drop_constraint('fk_meals_meal_plan_id_meal_plans', type_='foreignkey')
        batch_op.drop_column('pinned')
        batch_op.drop_column('meal_plan_id')

    # Drop meal_plans table
    op.drop_index(op.f('ix_meal_plans_user_id'), table_name='meal_plans')
    op.drop_index(op.f('ix_meal_plans_id'), table_name='meal_plans')
    op.drop_table('meal_plans')
