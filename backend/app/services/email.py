import smtplib
from email.message import EmailMessage

from email.utils import parseaddr

from app.core.config import get_settings

# Every email this app sends about itself starts its subject with this.
PREFIX = "[Email Routing] "


def is_app_mail(sender_email: str | None, subject: str | None) -> bool:
    """True for one of this app's own emails arriving in a connected mailbox.

    Such mail must never set off rules or the AI: a notification that causes a notification would never stop.
    """
    ours = parseaddr(get_settings().smtp_from or "")[1].lower()
    return bool(ours) and (sender_email or "").lower() == ours and (subject or "").startswith(PREFIX)


def send_email(to: str, subject: str, body: str) -> None:
    """Send a plain-text email through the configured SMTP server. Raises if it cannot."""
    settings = get_settings()
    if not settings.email_enabled:
        raise RuntimeError("Outgoing email is not configured")

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password or "")
        smtp.send_message(message)
