"""Sending people their notifications by email as well as in the app."""

import logging
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import utcnow
from app.models.collab import Notification
from app.models.user import User
from app.models.workspace import Workspace
from app.services import email
from app.services.auth import Identity

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
PER_TICK = 20
# A notification nobody could be emailed about within a day is no longer news.
FRESH_FOR = timedelta(hours=24)


def preference(db: Session, identity: Identity) -> dict:
    return {"available": get_settings().email_enabled, "enabled": identity.user.notify_by_email, "address": identity.user.email}


def set_preference(db: Session, identity: Identity, enabled: bool) -> dict:
    identity.user.notify_by_email = enabled
    db.commit()
    return preference(db, identity)


def _text(notification: Notification, workspace: Workspace | None) -> str:
    base = get_settings().app_url.rstrip("/")
    link = f"{base}/inbox?c={notification.conversation_id}" if notification.conversation_id else f"{base}/notifications"
    lines = [notification.title, ""]
    if notification.body:
        lines += [notification.body, ""]
    lines += [f"Open it: {link}", "", "--", f"You are getting this because email notifications are on for your account in Email Routing{f' ({workspace.name})' if workspace else ''}.",
              "To stop them, open Settings > Profile and switch off “Email me my notifications”."]
    return "\n".join(lines)


def send_pending(db: Session) -> int:
    """Email the notifications that have not gone out yet. Each is sent once; a failure is tried three times."""
    if not get_settings().email_enabled:
        # Nothing waits for the day email is set up: that would send a flood of old news.
        db.execute(update(Notification).where(Notification.email_state == "pending").values(email_state="skipped"))
        db.commit()
        return 0
    sent = 0
    for notification in db.scalars(select(Notification).where(Notification.email_state == "pending").order_by(Notification.id).limit(PER_TICK)).all():
        person = db.get(User, notification.user_id)
        if notification.read_at is not None or person is None or not person.notify_by_email or notification.created_at < utcnow() - FRESH_FOR:
            notification.email_state = "skipped"  # already seen in the app, switched off, or too old to be news
        else:
            notification.email_attempts += 1
            try:
                email.send_email(person.email, f"{email.PREFIX}{notification.title}"[:200], _text(notification, db.get(Workspace, notification.workspace_id)))
                notification.email_state = "sent"
                sent += 1
            except Exception as exc:  # noqa: BLE001 - recorded and tried again on a later tick
                logger.warning("Notification %s could not be emailed: %s", notification.id, type(exc).__name__)
                if notification.email_attempts >= MAX_ATTEMPTS:
                    notification.email_state = "failed"
        db.commit()
    return sent
