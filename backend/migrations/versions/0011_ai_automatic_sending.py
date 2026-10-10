"""AI automatic sending: separate switches for Low and Medium, a daily limit, a per-mailbox switch, and a record on each reply.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-09
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Everything starts off: nothing is sent automatically until an owner or admin says so.
    op.add_column("ai_settings", sa.Column("auto_send_low", sa.Boolean, nullable=False, server_default="0"))
    op.add_column("ai_settings", sa.Column("auto_send_medium", sa.Boolean, nullable=False, server_default="0"))
    op.add_column("ai_settings", sa.Column("daily_limit", sa.Integer, nullable=False, server_default="20"))
    op.add_column("ai_account_settings", sa.Column("auto_send", sa.Boolean, nullable=False, server_default="1"))
    op.add_column("ai_replies", sa.Column("auto_sent", sa.Boolean, nullable=False, server_default="0"))
    op.add_column("ai_replies", sa.Column("auto_note", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("ai_replies", "auto_note")
    op.drop_column("ai_replies", "auto_sent")
    op.drop_column("ai_account_settings", "auto_send")
    op.drop_column("ai_settings", "daily_limit")
    op.drop_column("ai_settings", "auto_send_medium")
    op.drop_column("ai_settings", "auto_send_low")
