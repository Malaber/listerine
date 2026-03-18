"""add admin users and global categories

Revision ID: 0003_add_admin_and_global_categories
Revises: 0002_add_passkey_columns
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_add_admin_and_global_categories"
down_revision = "0002_add_passkey_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="0"))
    with op.batch_alter_table("categories") as batch_op:
        batch_op.alter_column("household_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("categories") as batch_op:
        batch_op.alter_column("household_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("users", "is_admin")
