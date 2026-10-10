"""Connecting Gmail by Google sign-in: how an account signs in, and sign-in attempts.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def upgrade() -> None:
    # Existing accounts all sign in with a mailbox password ("basic"), which is the default.
    op.add_column("email_accounts", sa.Column("auth_type", sa.String(16), nullable=False, server_default="basic"))

    op.create_table(
        "email_oauth_states",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("session_id", sa.BigInteger, sa.ForeignKey("sessions.id", name="fk_email_oauth_states_session", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id", name="fk_email_oauth_states_workspace", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id", name="fk_email_oauth_states_user", ondelete="CASCADE"), nullable=False),
        sa.Column("code_verifier_encrypted", sa.Text, nullable=False),
        sa.Column("expires_at", DATETIME(fsp=6), nullable=False),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.UniqueConstraint("state_hash", name="uq_email_oauth_states_state_hash"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_email_oauth_states_session_id", "email_oauth_states", ["session_id"])
    op.create_index("ix_email_oauth_states_workspace_id", "email_oauth_states", ["workspace_id"])
    op.create_index("ix_email_oauth_states_user_id", "email_oauth_states", ["user_id"])
    op.create_index("ix_email_oauth_states_expires_at", "email_oauth_states", ["expires_at"])


def downgrade() -> None:
    op.drop_table("email_oauth_states")
    op.drop_column("email_accounts", "auth_type")
