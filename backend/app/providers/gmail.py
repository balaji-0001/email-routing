import re
import base64
import email
import email.utils
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

import httpx2

from app.core.database import utcnow
from app.providers.base import EmailProvider
from app.providers.imap_smtp import _decode_mime_header, _parse_address_list, _parse_email_address
from app.providers.mime import add_attachments

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
# Sending a whole message as its own request body, which is what allows attachments of real size.
GMAIL_UPLOAD = "https://gmail.googleapis.com/upload/gmail/v1/users/me"

# Gmail's own labels and the folder kind each one stands for.
SYSTEM_LABELS = {"INBOX": "inbox", "SENT": "sent", "DRAFT": "drafts", "TRASH": "trash", "SPAM": "trash"}

# The most new messages taken in one sync when following Gmail's change history.
HISTORY_CAP = 200

# How many messages are downloaded at the same time. Google limits each mailbox's
# requests per minute, so this stays small and the import paces itself between pages.
FETCH_THREADS = 4

# Tests replace this with a stand-in for Google. It is never set in the running product.
SAFE_MESSAGE_ID = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.@-]{1,250}$")
transport: httpx2.BaseTransport | None = None


def http_client() -> httpx2.Client:
    return httpx2.Client(timeout=20, transport=transport)


class GmailApiError(Exception):
    """Google answered with a failure that is safe to show."""


class GmailRateLimited(GmailApiError):
    """Google's per-minute limit for this mailbox was reached. Nothing is wrong; try again in a minute."""


class ReconnectRequired(Exception):
    """Google no longer accepts the stored sign-in; the owner has to connect again."""


def _error_message(response: httpx2.Response) -> str:
    try:
        error = response.json().get("error")
    except ValueError:
        error = None
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])
    return f"Gmail answered with status {response.status_code}."


def _is_rate_limit(response: httpx2.Response) -> bool:
    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False
    text = response.text.lower()
    return "quota exceeded" in text or "ratelimitexceeded" in text or "rate limit" in text


def _decode_part(part: email.message.Message) -> str:
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    try:
        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def parse_raw_message(raw: bytes, *, gmail_id: str, thread_id: str | None, internal_date_ms: str | None, label_ids: list[str] | None = None) -> dict[str, Any]:
    """Turn one RFC 822 message from Gmail into the shape the sync service stores."""
    msg = email.message_from_bytes(raw)
    sender_name, sender_email = _parse_email_address(msg.get("From"))

    sent_at = utcnow()
    if internal_date_ms:
        sent_at = datetime.fromtimestamp(int(internal_date_ms) / 1000, tz=timezone.utc).replace(tzinfo=None)
    elif msg.get("Date"):
        try:
            parsed = email.utils.parsedate_to_datetime(msg["Date"])
            sent_at = parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
        except (TypeError, ValueError):
            pass

    body_text = ""
    body_html = ""
    attachments: list[dict[str, Any]] = []
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.is_multipart():
            continue
        content_type = part.get_content_type()
        filename = part.get_filename()
        if filename or "attachment" in str(part.get("Content-Disposition", "")):
            attachments.append({
                "filename": _decode_mime_header(filename or "attachment")[:255],
                "content_type": content_type[:128],
                "file_size": len(part.get_payload(decode=True) or b""),
            })
        elif content_type == "text/plain" and not body_text:
            body_text = _decode_part(part)
        elif content_type == "text/html" and not body_html:
            body_html = _decode_part(part)

    return {
        "provider_message_id": (msg.get("Message-ID") or f"<{gmail_id}@gmail.local>").strip()[:255],
        "provider_thread_id": thread_id,
        "subject": _decode_mime_header(msg.get("Subject")) or "(no subject)",
        "sender_name": sender_name,
        "sender_email": sender_email,
        "to_recipients": _parse_address_list(msg.get("To")),
        "cc_recipients": _parse_address_list(msg.get("Cc")),
        "sent_at": sent_at,
        "in_reply_to": (msg.get("In-Reply-To") or "").strip()[:500] or None,
        "references": msg.get("References"),
        "body_text": body_text,
        "body_html": body_html,
        "snippet": (body_text or body_html or "")[:200].replace("\n", " ").strip(),
        "attachments": attachments,
        # Gmail knows whether the owner has already read or starred it.
        "is_read": "UNREAD" not in (label_ids or ["UNREAD"]),
        "is_starred": "STARRED" in (label_ids or []),
    }


class GmailProvider(EmailProvider):
    """A Gmail mailbox reached through the Gmail API with the owner's Google sign-in."""

    def __init__(self, *, token_source: Callable[[bool], str], from_address: str, from_name: str = "", cursor: str | None = None):
        # token_source(force) returns a valid access token, getting a fresh one when asked to.
        self._token = token_source
        self.from_address = from_address
        self.from_name = from_name
        self.cursor = cursor
        # Where the next sync should start from, set by fetch_messages.
        self.next_cursor: str | None = None

    def _call(self, client: httpx2.Client, method: str, path: str, *, params: dict | None = None, json: dict | None = None, allow: tuple[int, ...] = (), raw_message: bytes | None = None) -> httpx2.Response:
        refreshed = False
        retries = 0
        while True:
            # After a refused token, ask for a fresh one and try once more.
            headers = {"Authorization": f"Bearer {self._token(refreshed)}"}
            if raw_message is not None:
                response = client.request(method, GMAIL_UPLOAD + path, params=params, content=raw_message, headers={**headers, "Content-Type": "message/rfc822"})
            else:
                response = client.request(method, GMAIL_API + path, params=params, json=json, headers=headers)
            if response.status_code == 401 and not refreshed:
                refreshed = True
                continue
            if (response.status_code in (500, 502, 503) or _is_rate_limit(response)) and retries < 2:
                retries += 1
                time.sleep(retries)
                continue
            break
        if _is_rate_limit(response):
            raise GmailRateLimited("Gmail asked to slow down. It will continue shortly.")
        if response.status_code in allow:
            return response
        if response.status_code == 401:
            raise ReconnectRequired("Google no longer accepts this connection.")
        if response.status_code >= 400:
            raise GmailApiError(_error_message(response))
        return response

    def test_connection(self) -> tuple[bool, str]:
        try:
            with http_client() as client:
                self._call(client, "GET", "/profile")
        except (GmailApiError, ReconnectRequired, httpx2.HTTPError) as exc:
            return False, str(exc)
        return True, ""

    def list_folders(self) -> list[dict[str, str]]:
        with http_client() as client:
            labels = self._call(client, "GET", "/labels").json().get("labels", [])
        folders = []
        for label in labels:
            if label.get("id") in SYSTEM_LABELS:
                folders.append({"name": label["id"], "system_folder": SYSTEM_LABELS[label["id"]]})
            elif label.get("type") == "user":
                folders.append({"name": str(label.get("name", ""))[:255], "system_folder": "custom"})
        if not any(f["system_folder"] == "inbox" for f in folders):
            folders.insert(0, {"name": "INBOX", "system_folder": "inbox"})
        return folders

    def _new_ids_since_cursor(self, client: httpx2.Client, label: str) -> list[str] | None:
        """Ids of messages that arrived after the cursor, or None when Gmail has forgotten it."""
        ids: list[str] = []
        page_token = None
        while True:
            params = {"startHistoryId": self.cursor, "historyTypes": "messageAdded", "labelId": label, "maxResults": 500}
            if page_token:
                params["pageToken"] = page_token
            response = self._call(client, "GET", "/history", params=params, allow=(404,))
            if response.status_code == 404:
                return None
            body = response.json()
            for record in body.get("history", []):
                for added in record.get("messagesAdded", []):
                    message = added.get("message", {})
                    if label in message.get("labelIds", []) and message.get("id") not in ids:
                        ids.append(message["id"])
            page_token = body.get("nextPageToken")
            if not page_token or len(ids) >= HISTORY_CAP:
                break
        return ids[-HISTORY_CAP:]

    def fetch_messages(self, folder_name: str = "INBOX", limit: int = 40) -> list[dict[str, Any]]:
        label = folder_name or "INBOX"
        with http_client() as client:
            # Read the position first, so nothing that arrives during this sync is skipped next time.
            history_id = str(self._call(client, "GET", "/profile").json().get("historyId") or "")

            ids = self._new_ids_since_cursor(client, label) if self.cursor else None
            if ids is None:
                listing = self._call(client, "GET", "/messages", params={"labelIds": label, "maxResults": limit}).json()
                ids = [m["id"] for m in listing.get("messages", [])]

            messages = self._fetch(client, ids)

        self.next_cursor = history_id or None
        return messages

    def _fetch(self, client: httpx2.Client, ids: list[str]) -> list[dict[str, Any]]:
        def one(gmail_id: str) -> dict[str, Any] | None:
            response = self._call(client, "GET", f"/messages/{gmail_id}", params={"format": "raw"}, allow=(404,))
            if response.status_code == 404:
                return None  # deleted since it was listed
            body = response.json()
            raw = base64.urlsafe_b64decode(body.get("raw", "") + "==")
            return parse_raw_message(raw, gmail_id=gmail_id, thread_id=body.get("threadId"), internal_date_ms=body.get("internalDate"), label_ids=body.get("labelIds"))

        if not ids:
            return []
        # Renew the token once here, not in every thread at the same moment.
        self._token(False)
        # A few at a time: well inside Gmail's per-user rate limit, and several times faster than one by one.
        with ThreadPoolExecutor(max_workers=FETCH_THREADS) as pool:
            messages = [m for m in pool.map(one, ids) if m is not None]
        messages.sort(key=lambda m: m["sent_at"], reverse=True)
        return messages

    def label_total(self, label: str = "INBOX") -> int | None:
        """How many messages Gmail says the label holds."""
        with http_client() as client:
            total = self._call(client, "GET", f"/labels/{label}").json().get("messagesTotal")
        return int(total) if total is not None else None

    def fetch_page(self, label: str = "INBOX", page_token: str | None = None, page_size: int = 50) -> tuple[list[dict[str, Any]], str | None]:
        """One page of a label's messages, newest first, and the token for the page after it (None on the last)."""
        params: dict[str, Any] = {"labelIds": label, "maxResults": page_size}
        if page_token:
            params["pageToken"] = page_token
        with http_client() as client:
            listing = self._call(client, "GET", "/messages", params=params).json()
            messages = self._fetch(client, [m["id"] for m in listing.get("messages", [])])
        return messages, listing.get("nextPageToken")

    def send_message(
        self,
        to: list[str],
        subject: str,
        body_text: str | None,
        body_html: str | None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
        attachments: list[tuple[str, str, bytes]] | None = None,
        thread_id: str | None = None,
    ) -> str:
        msg = EmailMessage()
        msg["From"] = email.utils.formataddr((self.from_name, self.from_address)) if self.from_name else self.from_address
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)
        msg["Subject"] = subject
        message_id = email.utils.make_msgid()
        msg["Message-ID"] = message_id
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = references or in_reply_to
        msg.set_content(body_text or "")
        if body_html:
            msg.add_alternative(body_html, subtype="html")

        add_attachments(msg, attachments)

        with http_client() as client:
            if attachments:
                # Gmail threads these by their In-Reply-To and References headers.
                sent = self._call(client, "POST", "/messages/send", params={"uploadType": "media"}, raw_message=msg.as_bytes()).json()
            else:
                body: dict[str, Any] = {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")}
                if thread_id:
                    body["threadId"] = thread_id
                sent = self._call(client, "POST", "/messages/send", json=body).json()
            # Gmail may replace the Message-ID; replies must point at the one it kept.
            if sent.get("id"):
                meta = self._call(client, "GET", f"/messages/{sent['id']}", params={"format": "metadata", "metadataHeaders": "Message-ID"}, allow=(404,))
                if meta.status_code == 200:
                    for header in meta.json().get("payload", {}).get("headers", []):
                        if header.get("name", "").lower() == "message-id" and header.get("value"):
                            return str(header["value"])
        return message_id

    def fetch_raw(self, provider_message_id: str) -> bytes | None:
        # The id comes from the email's own header, which its sender wrote. Only a plain id is searched for.
        if not SAFE_MESSAGE_ID.match(provider_message_id.strip("<>")):
            return None
        with http_client() as client:
            found = self._call(client, "GET", "/messages", params={"q": f"rfc822msgid:{provider_message_id.strip('<>')}", "maxResults": 1, "includeSpamTrash": "true"}).json()
            messages = found.get("messages") or []
            if not messages:
                return None
            response = self._call(client, "GET", f"/messages/{messages[0]['id']}", params={"format": "raw"}, allow=(404,))
            if response.status_code == 404:
                return None
            return base64.urlsafe_b64decode(response.json().get("raw", "") + "==")
