"""add passkey columns

Revision ID: 0002_add_passkey_columns
Revises: 0001_initial
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_add_passkey_columns"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("passkey_credential_id", sa.String(length=255), nullable=True),
    )
    op.add_column("users", sa.Column("passkey_public_key", sa.LargeBinary(), nullable=True))
    op.add_column(
        "users", sa.Column("passkey_sign_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.create_unique_constraint(
        "uq_users_passkey_credential_id", "users", ["passkey_credential_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_passkey_credential_id", "users", type_="unique")
    op.drop_column("users", "passkey_sign_count")
    op.drop_column("users", "passkey_public_key")
    op.drop_column("users", "passkey_credential_id")
