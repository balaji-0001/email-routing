from abc import ABC, abstractmethod
from typing import Any


class EmailProvider(ABC):
    """Abstract interface that all email provider adapters (IMAP/SMTP, Gmail, Microsoft) implement."""

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """Test authentication and connectivity. Returns (success, error_message)."""
        pass

    @abstractmethod
    def list_folders(self) -> list[dict[str, str]]:
        """List folders available on the mail server. Returns [{'name': str, 'system_folder': str}]."""
        pass

    @abstractmethod
    def fetch_messages(self, folder_name: str, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch latest messages from the given folder."""
        pass

    @abstractmethod
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
        """Send an email through the provider. Returns provider Message-ID.

        `attachments` are (file name, content type, content). `thread_id` is the
        provider's own thread, for providers that have one.
        """
        pass

    def fetch_raw(self, provider_message_id: str) -> bytes | None:
        """The whole original message by its Message-ID, or None if the mailbox no longer has it."""
        return None

