"""Sign-in page and Settings page tests.

Run from the backend folder:   pytest -v

Demo account: business123@gmail.com / SISO67#   (synthetic, for the demo only)
Most other test files switch the sign-in check off (conftest.py). The `signed_in_required`
fixture below switches it back on.
"""
import time

import pytest
from sqlalchemy import create_engine, select, text

from app.auth.login import create_token, password_matches, reset_login_state
from app.models import ActivityLog
from app.schema_upgrade import upgrade_schema
from tests.conftest import CAFE_EMPLOYEE, CAFE_OWNER, find_item

EMAIL = "business123@gmail.com"
PASSWORD = "SISO67#"


@pytest.fixture(autouse=True)
def clean_login_state():
    reset_login_state()
    yield
    reset_login_state()


@pytest.fixture()
def signed_in_required(monkeypatch):
    monkeypatch.setenv("REQUIRE_LOGIN", "true")


def sign_in(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def with_token(token, user_headers=CAFE_OWNER):
    return {**user_headers, "Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- signing in

def test_correct_account_signs_in(client):
    response = sign_in(client, email="  Business123@GMAIL.com ")  # spaces and capitals are fine
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == EMAIL
    assert body["token"].count(".") == 1
    assert body["expires_at"] > time.time() + 3600


def test_wrong_details_are_refused(client):
    assert sign_in(client, password="siso67#").status_code == 401      # case-sensitive password
    assert sign_in(client, password="SISO67").status_code == 401
    assert sign_in(client, email="someone@gmail.com").status_code == 401
    assert sign_in(client).status_code == 200
    assert client.post("/api/auth/login", json={"email": EMAIL}).status_code == 422
    assert client.post("/api/auth/login", json={"email": EMAIL, "password": ""}).status_code == 422


def test_password_is_checked_against_a_hash(monkeypatch):
    assert password_matches(PASSWORD) is True
    assert password_matches("SISO67# ") is False
    monkeypatch.setenv("DEMO_LOGIN_PASSWORD", "another-one")  # optional override in .env
    assert password_matches("another-one") is True
    assert password_matches(PASSWORD) is False


def test_too_many_wrong_passwords_are_blocked(client):
    for _ in range(5):
        assert sign_in(client, password="wrong").status_code == 401
    response = sign_in(client)  # even the right password waits now
    assert response.status_code == 429
    assert "Too many" in response.json()["detail"]


# ---------------------------------------------------------------- the whole API needs a session

def test_api_needs_a_session(client, signed_in_required):
    response = client.get("/api/inventory", headers=CAFE_OWNER)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert client.get("/api/orbyte-mock/users").status_code == 401
    assert client.get("/api/health").status_code == 200  # the health check stays open

    token = sign_in(client).json()["token"]
    assert client.get("/api/inventory", headers=with_token(token)).status_code == 200
    assert client.get("/api/orbyte-mock/users", headers=with_token(token)).status_code == 200


def test_forged_and_expired_tokens_are_refused(client, signed_in_required):
    token = sign_in(client).json()["token"]
    forged = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    assert client.get("/api/inventory", headers=with_token(forged)).status_code == 401
    expired, _ = create_token(EMAIL, lifetime_seconds=-5)
    assert client.get("/api/inventory", headers=with_token(expired)).status_code == 401
    assert client.get("/api/inventory", headers=with_token("not-a-token")).status_code == 401


def test_sign_out_ends_the_session(client, signed_in_required):
    token = sign_in(client).json()["token"]
    session = client.get("/api/auth/session", headers={"Authorization": f"Bearer {token}"})
    assert session.status_code == 200 and session.json()["email"] == EMAIL

    assert client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code == 204
    assert client.get("/api/auth/session", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.get("/api/inventory", headers=with_token(token)).status_code == 401
    # Signing in again gives a new, working token
    new_token = sign_in(client).json()["token"]
    assert client.get("/api/inventory", headers=with_token(new_token)).status_code == 200


def test_sign_in_is_checked_before_the_role(client, db_session, signed_in_required):
    """Without a session the request stops at 401: it never reaches the role check,
    so no 'access denied' entry is written for an anonymous caller."""
    assert client.post("/api/purchase-orders/1/approve", headers=CAFE_EMPLOYEE).status_code == 401
    assert db_session.scalars(select(ActivityLog).where(ActivityLog.action == "access.denied")).all() == []
    token = sign_in(client).json()["token"]
    # Signed in, but an employee: the role rules still apply
    assert client.post("/api/purchase-orders/1/approve", headers=with_token(token, CAFE_EMPLOYEE)).status_code == 403


# ---------------------------------------------------------------- settings

def test_everyone_can_read_settings(client):
    body = client.get("/api/settings", headers=CAFE_EMPLOYEE).json()
    assert body["business_name"] == "Kopi Kita Café (demo)"
    assert body["auto_draft_orders"] is True
    assert body["can_edit"] is False
    assert client.get("/api/settings", headers=CAFE_OWNER).json()["can_edit"] is True


def test_owner_changes_settings_and_it_is_logged(client):
    response = client.patch("/api/settings", headers=CAFE_OWNER, json={"business_name": "Kopi Kita Café Bangsar (demo)"})
    assert response.status_code == 200, response.text
    assert response.json()["business_name"] == "Kopi Kita Café Bangsar (demo)"
    context = client.get("/api/orbyte-mock/context", headers=CAFE_OWNER).json()
    assert context["business"]["name"] == "Kopi Kita Café Bangsar (demo)"

    log = client.get("/api/activity-logs", headers=CAFE_OWNER, params={"category": "settings"}).json()["items"][0]
    assert log["action"] == "business.updated"
    assert {row["field"]: (row["old"], row["new"]) for row in log["changes"]}["business_name"] == (
        "Kopi Kita Café (demo)", "Kopi Kita Café Bangsar (demo)"
    )


def test_settings_rules(client):
    assert client.patch("/api/settings", headers=CAFE_EMPLOYEE, json={"auto_draft_orders": False}).status_code == 403
    for body in ({}, {"business_name": ""}, {"business_name": None}, {"auto_draft_orders": None}, {"x": 1}):
        assert client.patch("/api/settings", headers=CAFE_OWNER, json=body).status_code == 422, body
    assert client.get("/api/settings", headers=CAFE_OWNER).json()["auto_draft_orders"] is True


def test_switching_off_automatic_drafts(client):
    assert client.patch("/api/settings", headers=CAFE_OWNER, json={"auto_draft_orders": False}).status_code == 200
    milk = find_item(client, CAFE_EMPLOYEE, "MILK-1L")
    response = client.post(f"/api/inventory/{milk['id']}/movements", headers=CAFE_EMPLOYEE,
                           json={"movement_type": "out", "quantity": 15})
    assert response.status_code == 201
    assert response.json()["draft_purchase_order"] is None
    assert client.get("/api/purchase-orders", headers=CAFE_OWNER).json() == []
    # The low-stock alert still opens, and the manual button still prepares drafts
    assert any(a["sku"] == "MILK-1L" for a in client.get("/api/alerts", headers=CAFE_OWNER).json())
    generated = client.post("/api/purchase-orders/generate", headers=CAFE_EMPLOYEE).json()
    assert generated["lines_added"] >= 1
    # Another business is not affected
    assert client.get("/api/settings", headers={"X-User-Id": "3"}).json()["auto_draft_orders"] is True


def test_schema_upgrade_adds_the_settings_column(tmp_path):
    old_engine = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with old_engine.begin() as connection:
        connection.execute(text("CREATE TABLE businesses (id INTEGER PRIMARY KEY, name VARCHAR(120), created_at DATETIME)"))
    assert upgrade_schema(old_engine) == ["businesses.auto_draft_orders"]
    assert upgrade_schema(old_engine) == []
    old_engine.dispose()
