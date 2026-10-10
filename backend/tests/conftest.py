"""Tests run against a real MySQL database whose name ends in `_test`, never the dev one."""

import os
from pathlib import Path

from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]


def _test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    from app.core.config import Settings

    url = make_url(Settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


# Must happen before anything imports the app: the engine is created from this setting.
os.environ["DATABASE_URL"] = _test_database_url()
os.environ["APP_ENV"] = "development"
os.environ["APP_URL"] = "http://localhost:5173"
os.environ["SMTP_HOST"] = ""
os.environ["SMTP_FROM"] = ""
# Tests never use the owner's real Google app or encryption key.
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["GOOGLE_CLIENT_SECRET"] = ""
os.environ["ENCRYPTION_KEY"] = ""
# Nor a real AI key: tests talk to a stand-in for Gemini.
os.environ["GEMINI_API_KEY"] = ""

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.main import app  # noqa: E402

assert make_url(get_settings().database_url).database.endswith("_test"), "Refusing to run tests against a non-test database"


@pytest.fixture(scope="session", autouse=True)
def schema():
    """Build the schema from the migrations, so the migrations themselves are tested."""
    with engine.begin() as connection:
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for (table,) in connection.execute(text("SHOW TABLES")).all():
            connection.execute(text(f"DROP TABLE `{table}`"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(config, "head")
    yield


@pytest.fixture(autouse=True)
def clean_state():
    """Every test starts with empty tables and no rate-limit history."""
    with engine.begin() as connection:
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in Base.metadata.sorted_tables:
            connection.execute(text(f"TRUNCATE TABLE `{table.name}`"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    limiter.clear()
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


PASSWORD = "correct-horse-battery"


@pytest.fixture
def signed_up(client):
    """A new account, signed in on `client`, without a workspace yet."""
    response = client.post("/api/v1/auth/register", json={"email": "ada@example.com", "password": PASSWORD, "name": "Ada Lovelace"})
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.fixture
def member(client, signed_up):
    """A signed-in owner of a workspace."""
    response = client.post("/api/v1/workspaces", json={"name": "Analytical Engines"})
    assert response.status_code == 201, response.text
    return client.get("/api/v1/auth/me").json()["data"]
