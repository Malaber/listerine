"""add per-list category ordering

Revision ID: 0004_add_list_category_orders
Revises: 0003_add_admin_and_global_categories
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_add_list_category_orders"
down_revision = "0003_add_admin_and_global_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "list_category_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("list_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["list_id"], ["grocery_lists.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("list_id", "category_id", name="uq_list_category_orders_list_category"),
        sa.UniqueConstraint(
            "list_id", "sort_order", name="uq_list_category_orders_list_sort_order"
        ),
    )


def downgrade() -> None:
    op.drop_table("list_category_orders")
