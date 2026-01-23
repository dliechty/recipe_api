"""add_time_indexes

Revision ID: cf20728c63d3
Revises: ae01b1201858
Create Date: 2026-01-04 14:35:36.719234

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "cf20728c63d3"
down_revision: Union[str, Sequence[str], None] = "ae01b1201858"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        op.f("ix_recipes_active_time_minutes"),
        "recipes",
        ["active_time_minutes"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recipes_cook_time_minutes"),
        "recipes",
        ["cook_time_minutes"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recipes_prep_time_minutes"),
        "recipes",
        ["prep_time_minutes"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_recipes_prep_time_minutes"), table_name="recipes")
    op.drop_index(op.f("ix_recipes_cook_time_minutes"), table_name="recipes")
    op.drop_index(op.f("ix_recipes_active_time_minutes"), table_name="recipes")
