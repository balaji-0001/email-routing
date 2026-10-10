"""Emailing notifications: where each one stands, and each person's choice.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-10
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("email_state", sa.String(12), nullable=False, server_default="pending"))
    op.add_column("notifications", sa.Column("email_attempts", sa.Integer, nullable=False, server_default="0"))
    op.create_index("ix_notifications_email_state", "notifications", ["email_state", "id"])
    # Notifications from before this existed are not emailed after the fact.
    op.execute("UPDATE notifications SET email_state = 'skipped'")
    op.add_column("users", sa.Column("notify_by_email", sa.Boolean, nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("users", "notify_by_email")
    op.drop_index("ix_notifications_email_state", table_name="notifications")
    op.drop_column("notifications", "email_attempts")
    op.drop_column("notifications", "email_state")
