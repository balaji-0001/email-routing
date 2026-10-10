"""What a rule can check about a new email. Each check takes the rule's value and the email."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Mail:
    """The parts of one new email that rules look at."""

    account_id: int
    sender: str
    recipients: str
    subject: str
    body: str
    has_attachments: bool
    # 'low', 'medium' or 'high' once the AI has analysed it; None before that or when AI is off.
    ai_priority: str | None = None


def _contains(needle: str, haystack: str) -> bool:
    return needle.strip().lower() in (haystack or "").lower()


CHECKS: dict[str, Callable[[object, Mail], bool]] = {
    "account_id": lambda value, mail: mail.account_id == value,
    "sender": lambda value, mail: _contains(str(value), mail.sender),
    "recipient": lambda value, mail: _contains(str(value), mail.recipients),
    "subject": lambda value, mail: _contains(str(value), mail.subject),
    "body": lambda value, mail: _contains(str(value), mail.body),
    "has_attachments": lambda value, mail: mail.has_attachments is bool(value),
    "ai_priority": lambda value, mail: mail.ai_priority == value,
}


def matches(conditions: dict, mail: Mail) -> bool:
    """True when every condition that is filled in holds. Unknown names never match, so a bad rule does nothing."""
    for name, value in (conditions or {}).items():
        if value is None or value == "":
            continue
        check = CHECKS.get(name)
        if check is None or not check(value, mail):
            return False
    return True
