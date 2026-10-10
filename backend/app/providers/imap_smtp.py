import ssl
import socket
import ipaddress
import email
import email.header
import email.utils
import imaplib
import smtplib
from datetime import timezone
from email.message import EmailMessage
from typing import Any

from app.core.database import utcnow
from app.providers.base import EmailProvider
from app.providers.mime import add_attachments


def _decode_mime_header(header_value: str | None) -> str:
    if not header_value:
        return ""
    decoded_fragments = []
    for fragment, encoding in email.header.decode_header(header_value):
        if isinstance(fragment, bytes):
            try:
                decoded_fragments.append(fragment.decode(encoding or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                decoded_fragments.append(fragment.decode("latin1", errors="replace"))
        else:
            decoded_fragments.append(str(fragment))
    return " ".join(decoded_fragments).strip()


def _parse_email_address(raw_header: str | None) -> tuple[str, str]:
    if not raw_header:
        return "", ""
    name, addr = email.utils.parseaddr(raw_header)
    return _decode_mime_header(name), addr.strip().lower()


def _parse_address_list(raw_header: str | None) -> list[tuple[str, str]]:
    if not raw_header:
        return []
    addresses = email.utils.getaddresses([raw_header])
    return [(_decode_mime_header(name), addr.strip().lower()) for name, addr in addresses if addr]


def _system_folder_kind(folder_name: str) -> str:
    lower = folder_name.lower()
    if "inbox" in lower:
        return "inbox"
    if any(k in lower for k in ("sent", "gesendet", "envoy")):
        return "sent"
    if any(k in lower for k in ("draft", "brouillon", "entw")):
        return "drafts"
    if any(k in lower for k in ("trash", "bin", "corbeille", "papierkorb", "deleted")):
        return "trash"
    if any(k in lower for k in ("archive", "archiv")):
        return "archive"
    if any(k in lower for k in ("spam", "junk")):
        return "trash"
    return "custom"


class HostNotAllowed(Exception):
    """The server name points inside this server's own network, where mail servers of customers never are."""


def assert_public_host(host: str) -> None:
    """Refuse hosts that resolve to loopback, private, link-local or otherwise non-public addresses.

    Without this, the "connect a mailbox" form could be used to reach databases and internal services
    next to this server, and to learn what is running there from the error.
    """
    try:
        found = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise HostNotAllowed("The server name could not be found.") from exc
    for entry in found:
        address = ipaddress.ip_address(entry[4][0].split("%")[0])
        if not address.is_global:
            raise HostNotAllowed("That server address is not a public mail server.")


def _why(error: Exception) -> str:
    """A fixed sentence per kind of failure. The server's own reply is never passed on to the browser."""
    if isinstance(error, HostNotAllowed):
        return str(error)
    if isinstance(error, (imaplib.IMAP4.error, smtplib.SMTPAuthenticationError)):
        return "the username or password was not accepted."
    if isinstance(error, socket.gaierror):
        return "the server name could not be found."
    if isinstance(error, (TimeoutError, socket.timeout)):
        return "the server did not answer in time."
    if isinstance(error, ConnectionRefusedError):
        return "the server refused the connection. Check the port."
    if isinstance(error, ssl.SSLError):
        return "a secure connection could not be made. Check the port and security setting."
    return "the connection failed. Check the server name, port and security setting."


class ImapSmtpProvider(EmailProvider):
    """Real IMAP and SMTP provider implementation using standard protocols."""

    def __init__(
        self,
        *,
        incoming_host: str,
        incoming_port: int,
        incoming_security: str,
        incoming_username: str,
        incoming_password: str,
        outgoing_host: str,
        outgoing_port: int,
        outgoing_security: str,
        outgoing_username: str,
        outgoing_password: str,
        from_address: str,
        from_name: str = "",
    ):
        self.incoming_host = incoming_host
        self.incoming_port = incoming_port
        self.incoming_security = incoming_security.lower()
        self.incoming_username = incoming_username
        self.incoming_password = incoming_password
        self.outgoing_host = outgoing_host
        self.outgoing_port = outgoing_port
        self.outgoing_security = outgoing_security.lower()
        self.outgoing_username = outgoing_username
        self.outgoing_password = outgoing_password
        self.from_address = from_address
        self.from_name = from_name

    def _imap_connect(self) -> imaplib.IMAP4:
        assert_public_host(self.incoming_host)
        if self.incoming_security == "ssl" or self.incoming_port == 993:
            imap = imaplib.IMAP4_SSL(self.incoming_host, self.incoming_port, timeout=12)
        else:
            imap = imaplib.IMAP4(self.incoming_host, self.incoming_port, timeout=12)
            if self.incoming_security == "starttls":
                imap.starttls()
        imap.login(self.incoming_username, self.incoming_password)
        return imap

    def _smtp_connect(self) -> smtplib.SMTP:
        assert_public_host(self.outgoing_host)
        if self.outgoing_security == "ssl" or self.outgoing_port == 465:
            smtp = smtplib.SMTP_SSL(self.outgoing_host, self.outgoing_port, timeout=12)
        else:
            smtp = smtplib.SMTP(self.outgoing_host, self.outgoing_port, timeout=12)
            if self.outgoing_security == "starttls" or self.outgoing_port == 587:
                smtp.starttls()
        if self.outgoing_username:
            smtp.login(self.outgoing_username, self.outgoing_password)
        return smtp

    def test_connection(self) -> tuple[bool, str]:
        # Test IMAP
        try:
            imap = self._imap_connect()
            try:
                imap.logout()
            except Exception:
                pass
        except Exception as e:
            return False, f"Incoming mail (IMAP): {_why(e)}"

        # Test SMTP
        try:
            smtp = self._smtp_connect()
            try:
                smtp.quit()
            except Exception:
                pass
        except Exception as e:
            return False, f"Outgoing mail (SMTP): {_why(e)}"

        return True, ""

    def list_folders(self) -> list[dict[str, str]]:
        folders: list[dict[str, str]] = []
        try:
            imap = self._imap_connect()
            try:
                status, folder_lines = imap.list()
                if status == "OK" and folder_lines:
                    for line in folder_lines:
                        if not isinstance(line, bytes):
                            continue
                        decoded = line.decode("utf-8", errors="replace")
                        # IMAP list response format: (\\Flags) "/" "Folder Name"
                        parts = decoded.split(' "/" ')
                        if len(parts) >= 2:
                            name = parts[-1].strip().strip('"')
                        else:
                            name = decoded.split()[-1].strip('"')
                        folders.append({
                            "name": name,
                            "system_folder": _system_folder_kind(name),
                        })
            finally:
                try:
                    imap.logout()
                except Exception:
                    pass
        except Exception:
            # Fallback default folders if listing has an issue
            folders = [
                {"name": "INBOX", "system_folder": "inbox"},
                {"name": "Sent", "system_folder": "sent"},
                {"name": "Trash", "system_folder": "trash"},
                {"name": "Drafts", "system_folder": "drafts"},
            ]
        if not any(f["system_folder"] == "inbox" for f in folders):
            folders.insert(0, {"name": "INBOX", "system_folder": "inbox"})
        return folders

    def fetch_messages(self, folder_name: str = "INBOX", limit: int = 40) -> list[dict[str, Any]]:
        messages_data: list[dict[str, Any]] = []
        imap = self._imap_connect()
        try:
            status, _ = imap.select(f'"{folder_name}"', readonly=True)
            if status != "OK":
                status, _ = imap.select("INBOX", readonly=True)
                if status != "OK":
                    return []

            status, data = imap.search(None, "ALL")
            if status != "OK" or not data or not data[0]:
                return []

            msg_nums = data[0].split()
            # Fetch most recent messages up to limit
            selected_nums = msg_nums[-limit:]
            selected_nums.reverse()  # Newest first

            for num in selected_nums:
                try:
                    res, fetch_data = imap.fetch(num, "(RFC822)")
                    if res != "OK" or not fetch_data:
                        continue
                    raw_email = None
                    for part in fetch_data:
                        if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], bytes):
                            raw_email = part[1]
                            break
                    if not raw_email:
                        continue

                    msg = email.message_from_bytes(raw_email)
                    subject = _decode_mime_header(msg.get("Subject", "(no subject)"))
                    sender_name, sender_email = _parse_email_address(msg.get("From"))
                    to_recipients = _parse_address_list(msg.get("To"))
                    cc_recipients = _parse_address_list(msg.get("Cc"))
                    date_str = msg.get("Date")
                    sent_at = utcnow()
                    if date_str:
                        try:
                            dt = email.utils.parsedate_to_datetime(date_str)
                            if dt.tzinfo is not None:
                                sent_at = dt.astimezone(timezone.utc).replace(tzinfo=None)
                            else:
                                sent_at = dt
                        except Exception:
                            sent_at = utcnow()

                    provider_msg_id = msg.get("Message-ID", f"msg-{num.decode('utf-8', errors='ignore')}")
                    in_reply_to = msg.get("In-Reply-To")
                    references = msg.get("References")

                    body_text = ""
                    body_html = ""
                    attachments: list[dict[str, Any]] = []

                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition", ""))
                            filename = part.get_filename()

                            if filename or "attachment" in content_disposition:
                                attachments.append({
                                    "filename": _decode_mime_header(filename or "attachment"),
                                    "content_type": content_type,
                                    "file_size": len(part.get_payload(decode=True) or b""),
                                })
                            elif content_type == "text/plain" and not body_text:
                                payload = part.get_payload(decode=True)
                                if payload:
                                    charset = part.get_content_charset() or "utf-8"
                                    body_text = payload.decode(charset, errors="replace")
                            elif content_type == "text/html" and not body_html:
                                payload = part.get_payload(decode=True)
                                if payload:
                                    charset = part.get_content_charset() or "utf-8"
                                    body_html = payload.decode(charset, errors="replace")
                    else:
                        payload = msg.get_payload(decode=True)
                        if payload:
                            charset = msg.get_content_charset() or "utf-8"
                            text = payload.decode(charset, errors="replace")
                            if msg.get_content_type() == "text/html":
                                body_html = text
                            else:
                                body_text = text

                    snippet = (body_text or body_html or "")[:200].replace("\n", " ").strip()

                    messages_data.append({
                        "provider_message_id": provider_msg_id,
                        "subject": subject,
                        "sender_name": sender_name,
                        "sender_email": sender_email,
                        "to_recipients": to_recipients,
                        "cc_recipients": cc_recipients,
                        "sent_at": sent_at,
                        "in_reply_to": in_reply_to,
                        "references": references,
                        "body_text": body_text,
                        "body_html": body_html,
                        "snippet": snippet,
                        "attachments": attachments,
                    })
                except Exception:
                    continue
        finally:
            try:
                imap.logout()
            except Exception:
                pass

        return messages_data

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
        from_header = f"{self.from_name} <{self.from_address}>" if self.from_name else self.from_address
        msg["From"] = from_header
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)
        msg["Subject"] = subject
        msg_id = email.utils.make_msgid()
        msg["Message-ID"] = msg_id

        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references

        text_content = body_text or ""
        msg.set_content(text_content)
        if body_html:
            msg.add_alternative(body_html, subtype="html")
        add_attachments(msg, attachments)

        smtp = self._smtp_connect()
        try:
            smtp.send_message(msg)
        finally:
            try:
                smtp.quit()
            except Exception:
                pass

        return msg_id

    def fetch_raw(self, provider_message_id: str) -> bytes | None:
        # The id comes from the email's own header, which its sender wrote: a quote, a backslash or a
        # line break in it could turn the search below into a search for some other message.
        if any(ch in provider_message_id for ch in '"\\\r\n') or len(provider_message_id) > 250:
            return None
        imap = self._imap_connect()
        try:
            status, _ = imap.select("INBOX", readonly=True)
            if status != "OK":
                return None
            status, data = imap.search(None, "HEADER", "Message-ID", f'"{provider_message_id}"')
            if status != "OK" or not data or not data[0]:
                return None
            status, fetched = imap.fetch(data[0].split()[-1], "(RFC822)")
            if status != "OK" or not fetched:
                return None
            for part in fetched:
                if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], bytes):
                    return part[1]
            return None
        finally:
            try:
                imap.logout()
            except Exception:
                pass
