"""add per-list disabled categories

Revision ID: 0013_add_list_disabled_categories
Revises: 0012_add_offline_item_sync
Create Date: 2026-05-14
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_add_list_disabled_categories"
down_revision = "0012_add_offline_item_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "list_disabled_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("list_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["list_id"], ["grocery_lists.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "list_id",
            "category_id",
            name="uq_list_disabled_categories_list_category",
        ),
    )


def downgrade() -> None:
    op.drop_table("list_disabled_categories")
