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
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("passkey_credential_id", sa.String(length=255), nullable=True),
        )
        batch_op.add_column(sa.Column("passkey_public_key", sa.LargeBinary(), nullable=True))
        batch_op.add_column(
            sa.Column("passkey_sign_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_unique_constraint(
            "uq_users_passkey_credential_id", ["passkey_credential_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("uq_users_passkey_credential_id", type_="unique")
        batch_op.drop_column("passkey_sign_count")
        batch_op.drop_column("passkey_public_key")
        batch_op.drop_column("passkey_credential_id")
