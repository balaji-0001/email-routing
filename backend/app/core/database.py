from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

def connect_args() -> dict:
    """Extra connection settings: an encrypted, verified connection when the database is a hosted one."""
    settings = get_settings()
    if not settings.database_ssl:
        return {}
    import ssl

    # With the provider's own certificate if one was given, otherwise the certificates this machine trusts.
    # Either way the server's identity is checked; the connection is never merely "encrypted to someone".
    context = ssl.create_default_context(cadata=settings.database_ca.replace("\\n", "\n")) if settings.database_ca else ssl.create_default_context()
    return {"ssl": context}


engine = create_engine(get_settings().database_url, pool_pre_ping=True, pool_recycle=3600, connect_args=connect_args())
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Current time as naive UTC, which is how every DATETIME column is stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_db() -> Iterator[Session]:
    """One database session per request. Services commit; anything left over is rolled back."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
