import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://stockflow:stockflow@localhost:5432/stockflow_test"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)

# Tests drop and recreate the schema, so refuse to point at anything that is
# not clearly a throwaway database.
if not (make_url(TEST_DATABASE_URL).database or "").endswith("_test"):
    raise RuntimeError("TEST_DATABASE_URL must name a database ending in '_test'")

# Must happen before the app is imported so its engine binds to the test database.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database.connection import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TABLES = "stock_movements, order_items, orders, inventory, products"


@pytest.fixture(scope="session")
def migrated_database() -> None:
    """Build the schema from an empty database using the real Alembic migrations."""
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


@pytest.fixture
def clean_database(migrated_database: None) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client(clean_database: None) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session(clean_database: None) -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
