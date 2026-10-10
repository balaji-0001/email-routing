"""An email is stored once per mailbox, enforced by the database rather than by a check before saving.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-10
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Two syncs running at the same moment could both pass the "is it already here?" check and store it twice.
    op.create_index("uq_messages_account_provider_id", "messages", ["email_account_id", "provider_message_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_messages_account_provider_id", table_name="messages")
