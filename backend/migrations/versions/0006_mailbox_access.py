"""Who may use each mailbox.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def upgrade() -> None:
    # Existing mailboxes stay open to the whole workspace, as they were.
    op.add_column("email_accounts", sa.Column("access_mode", sa.String(16), nullable=False, server_default="everyone"))
    op.create_table(
        "email_account_members",
        sa.Column("email_account_id", sa.BigInteger, sa.ForeignKey("email_accounts.id", name="fk_email_account_members_account", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id", name="fk_email_account_members_user", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission", sa.String(16), nullable=False, server_default="send"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_email_account_members_user_id", "email_account_members", ["user_id"])


def downgrade() -> None:
    op.drop_table("email_account_members")
    op.drop_column("email_accounts", "access_mode")
