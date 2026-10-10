from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Server settings. Real environment variables win over the repo-root .env."""

    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    port: int = 5000
    log_level: str = "info"
    database_url: str = "mysql+pymysql://root@127.0.0.1:3308/email_management"

    # Where the web app is served. Used for links in emails and to reject
    # state-changing requests that come from any other origin.
    app_url: str = "http://localhost:5173"
    web_port: int = 5173

    session_cookie_name: str = "em_session"
    session_hours: int = 24
    remember_days: int = 30
    password_reset_minutes: int = 60

    # Outgoing email. Password reset is reported as unavailable until this is set.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True

    # Google sign-in for Gmail mailboxes. Connecting with Google is reported as
    # unavailable until both are set.
    google_client_id: str | None = None
    google_client_secret: str | None = None

    # Google Gemini, for summaries, priority and reply drafts. AI is reported as not set up until the key is here.
    gemini_api_key: str | None = None
    ai_model: str = "gemini-3.5-flash-lite"

    # Secret that protects stored mailbox passwords and tokens. Without it the
    # key is derived from DATABASE_URL, which is only acceptable in development.
    encryption_key: str | None = None

    @field_validator(
        "smtp_host", "smtp_username", "smtp_password", "smtp_from",
        "google_client_id", "google_client_secret", "encryption_key", "gemini_api_key",
        mode="before",
    )
    @classmethod
    def _blank_is_unset(cls, value: str | None) -> str | None:
        return value or None

    @property
    def is_production(self) -> bool:
        # Anything not plainly a development setting gets production's protections ("prod", "staging", a typo).
        return self.app_env.lower() not in ("development", "dev", "local", "test")

    @model_validator(mode="after")
    def _production_is_fully_set_up(self) -> "Settings":
        if not self.is_production:
            return self
        problems = []
        if not self.encryption_key:
            problems.append("ENCRYPTION_KEY must be set (stored mailbox passwords and tokens are protected with it)")
        if not self.app_url.lower().startswith("https://"):
            problems.append("APP_URL must be the site's https:// address")
        if "@127.0.0.1" in self.database_url and "root@" in self.database_url:
            problems.append("DATABASE_URL must point at the production database with its own user and password")
        if problems:
            raise ValueError("Not safe to start in production: " + "; ".join(problems) + ".")
        return self

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def ai_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def google_redirect_uri(self) -> str:
        # Built from APP_URL, never from the request: the dev server forwards /api,
        # so the request itself appears to come from the API's own port.
        return f"{self.app_url.rstrip('/')}/api/v1/email-accounts/oauth/google/callback"

    @property
    def allowed_origins(self) -> set[str]:
        origins = {self.app_url.rstrip("/")}
        if not self.is_production:
            origins |= {f"http://localhost:{self.web_port}", f"http://127.0.0.1:{self.web_port}"}
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
