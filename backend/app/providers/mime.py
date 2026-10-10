"""Reading attachments out of a raw email, the same way for every provider."""

import email
import email.header
from email.message import EmailMessage, Message


def _decode_mime_header(value: str) -> str:
    try:
        return str(email.header.make_header(email.header.decode_header(value))).strip()
    except (LookupError, UnicodeDecodeError, ValueError):
        return value.strip()


def is_attachment(part: Message) -> bool:
    """The rule the sync uses when it records a message's attachments. Keep the two in step."""
    return bool(part.get_filename()) or "attachment" in str(part.get("Content-Disposition", ""))


def extract_attachments(raw: bytes) -> list[tuple[str, str, bytes]]:
    """Every attachment in a raw message, in the order the sync recorded them: (file name, type, content)."""
    msg = email.message_from_bytes(raw)
    found: list[tuple[str, str, bytes]] = []
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.is_multipart() or not is_attachment(part):
            continue
        found.append((_decode_mime_header(part.get_filename() or "attachment"), part.get_content_type(), part.get_payload(decode=True) or b""))
    return found


def add_attachments(msg: EmailMessage, attachments: list[tuple[str, str, bytes]] | None) -> None:
    for filename, content_type, content in attachments or []:
        maintype, _, subtype = (content_type or "application/octet-stream").partition("/")
        msg.add_attachment(content, maintype=maintype or "application", subtype=subtype or "octet-stream", filename=filename)
