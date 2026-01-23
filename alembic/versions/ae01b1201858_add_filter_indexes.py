"""add_filter_indexes

Revision ID: ae01b1201858
Revises: 7d68d01253c7
Create Date: 2026-01-04 14:21:36.284248

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ae01b1201858"
down_revision: Union[str, Sequence[str], None] = "7d68d01253c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(op.f("ix_recipes_category"), "recipes", ["category"], unique=False)
    op.create_index(op.f("ix_recipes_cuisine"), "recipes", ["cuisine"], unique=False)
    op.create_index(
        op.f("ix_recipes_difficulty"), "recipes", ["difficulty"], unique=False
    )
    op.create_index(op.f("ix_recipes_protein"), "recipes", ["protein"], unique=False)
    op.create_index(
        op.f("ix_recipes_yield_amount"), "recipes", ["yield_amount"], unique=False
    )
    op.create_index(op.f("ix_recipes_calories"), "recipes", ["calories"], unique=False)
    op.create_index(
        op.f("ix_recipes_total_time_minutes"),
        "recipes",
        ["total_time_minutes"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_recipes_total_time_minutes"), table_name="recipes")
    op.drop_index(op.f("ix_recipes_calories"), table_name="recipes")
    op.drop_index(op.f("ix_recipes_yield_amount"), table_name="recipes")
    op.drop_index(op.f("ix_recipes_protein"), table_name="recipes")
    op.drop_index(op.f("ix_recipes_difficulty"), table_name="recipes")
    op.drop_index(op.f("ix_recipes_cuisine"), table_name="recipes")
    op.drop_index(op.f("ix_recipes_category"), table_name="recipes")
