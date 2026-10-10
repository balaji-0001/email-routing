"""The things that happen on the clock rather than when mail arrives. One tick does each of them once."""

import logging

from app.automation import engine
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


def tick() -> None:
    from app.services import notify_email, reminders

    for name, job in (("retry failed rules", engine.retry_failed), ("waiting rules", engine.run_waiting), ("reminders", reminders.fire_due), ("notification emails", notify_email.send_pending)):
        db = SessionLocal()
        try:
            job(db)
        except Exception as exc:  # noqa: BLE001 - one job failing must not stop the others
            db.rollback()
            logger.warning("Scheduled job '%s' failed: %s", name, exc)
        finally:
            db.close()
