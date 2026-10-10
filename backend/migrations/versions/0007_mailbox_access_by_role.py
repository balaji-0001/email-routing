"""Giving a whole role access to a restricted mailbox.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-08
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_account_roles",
        sa.Column("email_account_id", sa.BigInteger, sa.ForeignKey("email_accounts.id", name="fk_email_account_roles_account", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(20), primary_key=True),
        sa.Column("permission", sa.String(16), nullable=False, server_default="send"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )


def downgrade() -> None:
    op.drop_table("email_account_roles")
