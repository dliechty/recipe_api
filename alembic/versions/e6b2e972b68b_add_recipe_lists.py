"""add_recipe_lists

Revision ID: e6b2e972b68b
Revises: 20fdb31754ac
Create Date: 2026-01-23 15:47:47.497064

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6b2e972b68b"
down_revision: Union[str, Sequence[str], None] = "20fdb31754ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create recipe_lists table
    op.create_table(
        "recipe_lists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("recipe_lists", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_recipe_lists_id"), ["id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_recipe_lists_user_id"), ["user_id"], unique=False
        )

    # Create recipe_list_items table
    op.create_table(
        "recipe_list_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recipe_list_id", sa.Uuid(), nullable=False),
        sa.Column("recipe_id", sa.Uuid(), nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
        ),
        sa.ForeignKeyConstraint(
            ["recipe_list_id"],
            ["recipe_lists.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("recipe_list_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_recipe_list_items_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_recipe_list_items_recipe_id"), ["recipe_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_recipe_list_items_recipe_list_id"),
            ["recipe_list_id"],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("recipe_list_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_recipe_list_items_recipe_list_id"))
        batch_op.drop_index(batch_op.f("ix_recipe_list_items_recipe_id"))
        batch_op.drop_index(batch_op.f("ix_recipe_list_items_id"))

    op.drop_table("recipe_list_items")

    with op.batch_alter_table("recipe_lists", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_recipe_lists_user_id"))
        batch_op.drop_index(batch_op.f("ix_recipe_lists_id"))

    op.drop_table("recipe_lists")
