"""Test setup.

DATABASE_URL is pointed at a throw-away file BEFORE the app is imported, so the
tests can never touch your real backend/data/inventory.db.
Every test starts with a fresh database filled with the synthetic demo data.

Seeded IDs used in the tests:
  user 1 = Aisyah Rahman (OWNER,    Kopi Kita Café)
  user 2 = Hafiz Ismail  (EMPLOYEE, Kopi Kita Café)
  user 3 = Din Hassan    (OWNER,    Kedai Runcit Pak Din)
  user 4 = Siti Aminah   (EMPLOYEE, Kedai Runcit Pak Din)
"""
import os
import tempfile
from pathlib import Path

_TEST_DB_FILE = Path(tempfile.mkdtemp(prefix="inventory_tests_")) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_FILE.as_posix()}"
os.environ["AUTO_SEED"] = "false"
# The sign-in check is switched off for most tests (they focus on the business rules).
# test_auth_settings_api.py switches it back on to test signing in.
os.environ["REQUIRE_LOGIN"] = "false"
# Feature 9: tests must never call the real AI server on RunPod (even if .env sets it).
# AI tests switch it on themselves and use a fake AI.
os.environ["AI_BASE_URL"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: E402,F401
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed.seed_data import seed_if_empty  # noqa: E402

CAFE_OWNER = {"X-User-Id": "1"}
CAFE_EMPLOYEE = {"X-User-Id": "2"}
SHOP_OWNER = {"X-User-Id": "3"}
SHOP_EMPLOYEE = {"X-User-Id": "4"}


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_if_empty(db)
    yield


@pytest.fixture()
def client():
    # Not used as a context manager on purpose: that would run the app's
    # start-up code (which is not needed here).
    return TestClient(app)


@pytest.fixture()
def db_session():
    with SessionLocal() as session:
        yield session


def find_item(client, headers, sku, include_archived=True):
    """Look up a seeded product by SKU through the API."""
    response = client.get(
        "/api/inventory", headers=headers, params={"search": sku, "include_archived": include_archived}
    )
    assert response.status_code == 200, response.text
    matches = [item for item in response.json() if item["sku"] == sku]
    assert matches, f"SKU {sku} not found"
    return matches[0]