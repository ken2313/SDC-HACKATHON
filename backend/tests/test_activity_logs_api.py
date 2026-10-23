"""Feature 4 tests: role-based permissions checked by the backend + the Activity Logs API.

Run from the backend folder:   pytest -v

Seeded users: 1 = Aisyah (OWNER, café), 2 = Hafiz (EMPLOYEE, café),
              3 = Din (OWNER, shop),    4 = Siti (EMPLOYEE, shop).
"""
import json

from sqlalchemy import select

from app.models import ActivityLog
from tests.conftest import CAFE_EMPLOYEE, CAFE_OWNER, SHOP_EMPLOYEE, SHOP_OWNER, find_item


def move(client, headers, item_id, movement_type, quantity):
    return client.post(
        f"/api/inventory/{item_id}/movements",
        headers=headers,
        json={"movement_type": movement_type, "quantity": quantity},
    )


def logs(client, headers, **params):
    response = client.get("/api/activity-logs", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def milk_draft_order_id(client):
    """Café scenario: employee removes 15 milk (20 -> 5); a draft order is prepared."""
    milk = find_item(client, CAFE_EMPLOYEE, "MILK-1L")
    assert move(client, CAFE_EMPLOYEE, milk["id"], "out", 15).status_code == 201
    found = client.get("/api/purchase-orders", headers=CAFE_OWNER).json()
    return milk, found[0]["id"]


# ---------------------------------------------------------------- permissions (backend)

def test_employee_cannot_read_activity_logs(client):
    for path in ("/api/activity-logs", "/api/activity-logs/summary", "/api/activity-logs/filters"):
        assert client.get(path, headers=CAFE_EMPLOYEE).status_code == 403, path


def test_logs_need_a_session(client):
    assert client.get("/api/activity-logs").status_code == 401


def test_owner_can_read_activity_logs(client):
    assert client.get("/api/activity-logs", headers=CAFE_OWNER).status_code == 200


def test_there_is_no_way_to_change_or_delete_a_log_entry(client):
    entry_id = logs(client, CAFE_OWNER)["items"][0]["id"] if logs(client, CAFE_OWNER)["items"] else 1
    for method in ("post", "put", "patch", "delete"):
        response = getattr(client, method)(f"/api/activity-logs/{entry_id}", headers=CAFE_OWNER)
        assert response.status_code in (404, 405), (method, response.status_code)
    assert client.post("/api/activity-logs", headers=CAFE_OWNER, json={}).status_code == 405


def test_employee_permissions_exclude_every_owner_only_action(client):
    owner = client.get("/api/orbyte-mock/context", headers=CAFE_OWNER).json()["permissions"]
    employee = client.get("/api/orbyte-mock/context", headers=CAFE_EMPLOYEE).json()["permissions"]
    for permission in ("orders:approve", "logs:view", "inventory:manage", "suppliers:manage", "reports:view"):
        assert permission in owner
        assert permission not in employee
    for permission in ("inventory:view", "stock:record", "orders:prepare"):
        assert permission in employee


def test_permission_matrix_lists_both_roles(client):
    response = client.get("/api/access/matrix", headers=CAFE_EMPLOYEE)
    assert response.status_code == 200
    body = response.json()
    assert body["your_role"] == "employee"
    approve = next(row for row in body["permissions"] if row["key"] == "orders:approve")
    assert approve["allowed"] == {"owner": True, "employee": False}
    assert client.get("/api/access/matrix").status_code == 401


# ---------------------------------------------------------------- blocked attempts are logged

def test_blocked_attempt_is_written_to_the_log(client, db_session):
    _milk, order_id = milk_draft_order_id(client)
    response = client.post(f"/api/purchase-orders/{order_id}/approve", headers=CAFE_EMPLOYEE)
    assert response.status_code == 403

    entry = db_session.scalars(select(ActivityLog).where(ActivityLog.action == "access.denied")).one()
    assert entry.user_id == 2
    new_value = json.loads(entry.new_value)
    assert new_value["permission_needed"] == "orders:approve"
    assert new_value["decision"] == "denied"
    # the order itself did not change
    assert client.get(f"/api/purchase-orders/{order_id}", headers=CAFE_OWNER).json()["status"] == "draft"

    shown = logs(client, CAFE_OWNER, approval="denied")
    assert shown["total"] == 1
    assert shown["items"][0]["approval_status"] == "denied"
    assert shown["items"][0]["user_name"] == "Hafiz Ismail"


def test_allowed_requests_do_not_write_denied_entries(client, db_session):
    find_item(client, CAFE_EMPLOYEE, "MILK-1L")
    assert db_session.scalars(select(ActivityLog).where(ActivityLog.action == "access.denied")).first() is None


# ---------------------------------------------------------------- the café workflow in the log

def test_workflow_is_visible_with_before_and_after_values(client):
    milk, order_id = milk_draft_order_id(client)
    approve = client.post(f"/api/purchase-orders/{order_id}/approve", headers=CAFE_OWNER)
    assert approve.status_code == 200, approve.text

    page = logs(client, CAFE_OWNER)
    actions = [row["action"] for row in page["items"]]
    for expected in ("stock.out", "alert.opened", "po.generated", "po.approved"):
        assert expected in actions

    stock = next(row for row in page["items"] if row["action"] == "stock.out" and row["entity_id"] == milk["id"])
    assert stock["user_name"] == "Hafiz Ismail"
    assert stock["user_role"] == "employee"
    assert stock["entity_label"] == "Fresh Milk 1L"
    assert stock["old_value"] == {"quantity": 20}
    assert stock["new_value"]["quantity"] == 5
    quantity_change = next(change for change in stock["changes"] if change["field"] == "quantity")
    assert (quantity_change["old"], quantity_change["new"]) == (20, 5)

    approved = next(row for row in page["items"] if row["action"] == "po.approved")
    assert approved["user_name"] == "Aisyah Rahman"
    assert approved["approval_status"] == "approved"
    assert approved["entity_type"] == "purchase_order"
    assert approved["entity_label"].startswith("PO")
    assert approved["old_value"] == {"status": "draft"}


def test_rejection_is_recorded_with_its_reason(client):
    _milk, order_id = milk_draft_order_id(client)
    reason = "Too expensive this week"
    assert client.post(
        f"/api/purchase-orders/{order_id}/reject", headers=CAFE_OWNER, json={"reason": reason}
    ).status_code == 200
    shown = logs(client, CAFE_OWNER, approval="rejected")
    assert shown["total"] == 1
    assert shown["items"][0]["approval_status"] == "rejected"
    assert shown["items"][0]["new_value"]["reason"] == reason


def test_automatic_actions_show_as_system(client):
    # The start-up alert scan has no person behind it. Simulate such a row.
    from app.database import SessionLocal

    with SessionLocal() as db:
        db.add(ActivityLog(business_id=1, user_id=None, action="alert.opened", entity_type="stock_alert",
                           entity_id=None, summary="Scan opened an alert"))
        db.commit()
    row = logs(client, CAFE_OWNER, search="Scan opened")["items"][0]
    assert row["user_name"] == "System"
    assert row["user_role"] is None
    assert row["entity_label"] is None


# ---------------------------------------------------------------- filters, paging, summary

def test_filters(client):
    milk, order_id = milk_draft_order_id(client)
    client.post(f"/api/purchase-orders/{order_id}/approve", headers=CAFE_OWNER)

    assert {r["action"] for r in logs(client, CAFE_OWNER, category="stock")["items"]} == {"stock.out"}
    assert all(r["category"] == "purchase_order" for r in logs(client, CAFE_OWNER, category="purchase_order")["items"])
    assert logs(client, CAFE_OWNER, action="po.approved")["total"] == 1
    assert logs(client, CAFE_OWNER, approval="decisions")["total"] == 1
    assert all(r["user_id"] == 2 for r in logs(client, CAFE_OWNER, user_id=2)["items"])
    assert logs(client, CAFE_OWNER, user_id=2)["total"] >= 1
    assert logs(client, CAFE_OWNER, search="milk")["total"] >= 1
    assert logs(client, CAFE_OWNER, search="zzz-no-such-text")["total"] == 0
    # today (UTC) is inside the range, a range in the past is empty
    assert logs(client, CAFE_OWNER, date_from="2000-01-01", date_to="2100-01-01")["total"] > 0
    assert logs(client, CAFE_OWNER, date_from="2000-01-01", date_to="2000-01-02")["total"] == 0


def test_invalid_filter_values_are_rejected(client):
    assert client.get("/api/activity-logs", headers=CAFE_OWNER, params={"category": "nope"}).status_code == 422
    assert client.get("/api/activity-logs", headers=CAFE_OWNER, params={"limit": 0}).status_code == 422
    assert client.get("/api/activity-logs", headers=CAFE_OWNER, params={"limit": 1000}).status_code == 422
    assert client.get("/api/activity-logs", headers=CAFE_OWNER, params={"date_from": "not-a-date"}).status_code == 422


def test_paging_newest_first(client):
    milk = find_item(client, CAFE_EMPLOYEE, "OATM-1L")
    for _ in range(3):
        assert move(client, CAFE_EMPLOYEE, milk["id"], "out", 1).status_code == 201
    first = logs(client, CAFE_OWNER, limit=2, offset=0)
    second = logs(client, CAFE_OWNER, limit=2, offset=2)
    assert len(first["items"]) == 2
    assert first["total"] >= 3
    assert first["items"][0]["id"] > first["items"][1]["id"] > second["items"][0]["id"]


def test_summary_counts(client):
    _milk, order_id = milk_draft_order_id(client)
    client.post(f"/api/purchase-orders/{order_id}/approve", headers=CAFE_EMPLOYEE)  # blocked
    client.post(f"/api/purchase-orders/{order_id}/approve", headers=CAFE_OWNER)
    summary = client.get("/api/activity-logs/summary", headers=CAFE_OWNER).json()
    assert summary["approvals"] == 1
    assert summary["rejections"] == 0
    assert summary["blocked_attempts"] == 1
    assert summary["total"] >= 4
    assert summary["last_24_hours"] >= 4


def test_filter_options_list_only_this_business(client):
    options = client.get("/api/activity-logs/filters", headers=CAFE_OWNER).json()
    assert {u["name"] for u in options["users"]} == {"Aisyah Rahman", "Hafiz Ismail"}
    assert any(c["value"] == "purchase_order" for c in options["categories"])


# ---------------------------------------------------------------- business separation

def test_logs_are_separated_per_business(client):
    milk, _order_id = milk_draft_order_id(client)
    cafe_ids = {row["id"] for row in logs(client, CAFE_OWNER)["items"]}
    shop = logs(client, SHOP_OWNER)
    assert cafe_ids
    assert not cafe_ids & {row["id"] for row in shop["items"]}
    assert all("Milk" not in row["summary"] for row in shop["items"])
    # a shop employee being blocked is logged in the SHOP's log, not the café's
    assert client.get("/api/activity-logs", headers=SHOP_EMPLOYEE).status_code == 403
    assert logs(client, SHOP_OWNER, approval="denied")["total"] == 1
    assert logs(client, CAFE_OWNER, approval="denied")["total"] == 0
