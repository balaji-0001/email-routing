"""Importing a mailbox's existing mail in the background: progress per account.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-08
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Accounts connected before this start as "pending", so their older mail is brought in too.
    op.add_column("email_accounts", sa.Column("import_state", sa.String(16), nullable=False, server_default="pending"))
    op.add_column("email_accounts", sa.Column("import_page_token", sa.String(255), nullable=True))
    op.add_column("email_accounts", sa.Column("import_total", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("email_accounts", "import_total")
    op.drop_column("email_accounts", "import_page_token")
    op.drop_column("email_accounts", "import_state")
