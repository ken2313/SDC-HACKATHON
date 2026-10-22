"""Feature 2 tests: automatic low-stock alerts.

Run from the backend folder:   pytest -v

Seeded alerts at the start of every test (created by the start-up scan):
  Kopi Kita Café:        CHOC-500 (0 left, critical), COFB-ROB (4/5, low), LID-12OZ (11/15, low)
  Kedai Runcit Pak Din:  SOY-500 (0 left, critical), EGG-A30 (3/5, low)
"""
import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import ActivityLog, InventoryItem, StockAlert
from app.services.alert_service import reconcile_all, urgency_for
from tests.conftest import CAFE_EMPLOYEE, CAFE_OWNER, SHOP_EMPLOYEE, SHOP_OWNER, find_item


def move(client, headers, item_id, movement_type, quantity, **extra):
    return client.post(
        f"/api/inventory/{item_id}/movements",
        headers=headers,
        json={"movement_type": movement_type, "quantity": quantity, **extra},
    )


def alerts(client, headers, status="open"):
    response = client.get("/api/alerts", headers=headers, params={"status": status})
    assert response.status_code == 200, response.text
    return response.json()


def alert_skus(client, headers, status="open"):
    return {row["sku"] for row in alerts(client, headers, status)}


def db_alerts_for(db_session, sku):
    item = db_session.scalars(select(InventoryItem).where(InventoryItem.sku == sku)).first()
    db_session.expire_all()
    return list(db_session.scalars(select(StockAlert).where(StockAlert.item_id == item.id).order_by(StockAlert.id)))


# ---------------------------------------------------------------- urgency rule

@pytest.mark.parametrize(
    "quantity, threshold, expected",
    [
        (0, 10, "critical"),
        (0, 0, "critical"),
        (5, 10, "urgent"),    # exactly half of the threshold
        (3, 10, "urgent"),
        (6, 10, "low"),
        (10, 10, "low"),      # exactly at the threshold
        (1, 1, "low"),
    ],
)
def test_urgency_rule(quantity, threshold, expected):
    assert urgency_for(quantity, threshold) == expected


# ---------------------------------------------------------------- start-up scan

def test_startup_scan_opens_alerts_for_products_that_are_already_low(client):
    assert alert_skus(client, CAFE_OWNER) == {"CHOC-500", "COFB-ROB", "LID-12OZ"}
    assert alert_skus(client, SHOP_OWNER) == {"SOY-500", "EGG-A30"}


def test_healthy_products_have_no_alert(client):
    assert "MILK-1L" not in alert_skus(client, CAFE_OWNER)
    assert "TEHT-500" not in alert_skus(client, CAFE_OWNER)  # 9 > threshold 8


def test_scan_is_repeatable_and_creates_no_duplicates(db_session):
    before = db_session.scalars(select(StockAlert)).all()
    reconcile_all(db_session)
    reconcile_all(db_session)
    after = db_session.scalars(select(StockAlert)).all()
    assert len(after) == len(before) == 5


def test_scan_repairs_missing_alerts(db_session):
    for alert in db_session.scalars(select(StockAlert)).all():
        db_session.delete(alert)
    db_session.commit()
    reconcile_all(db_session)
    assert len(db_session.scalars(select(StockAlert).where(StockAlert.status == "open")).all()) == 5


# ---------------------------------------------------------------- opening alerts

def test_hackathon_demo_milk_alert(client, db_session):
    """20 cartons, threshold 10. Employee removes 15 -> 5 left -> alert generated."""
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    assert "MILK-1L" not in alert_skus(client, CAFE_OWNER)

    assert move(client, CAFE_EMPLOYEE, milk["id"], "out", 15, reason="Weekend rush").status_code == 201

    row = next(row for row in alerts(client, CAFE_OWNER) if row["sku"] == "MILK-1L")
    assert (row["quantity"], row["reorder_threshold"], row["shortfall"]) == (5, 10, 5)
    assert row["urgency"] == "urgent"
    assert row["status"] == "open"
    assert row["stock_status"] == "low_stock"

    entry = db_session.scalars(select(ActivityLog).where(ActivityLog.action == "alert.opened")).all()
    milk_entry = [e for e in entry if json.loads(e.new_value).get("item_id") == milk["id"]]
    assert len(milk_entry) == 1 and milk_entry[0].user_id == 2  # Hafiz caused it


def test_reaching_exactly_the_threshold_opens_an_alert(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 10)  # 20 -> 10 == threshold
    assert "MILK-1L" in alert_skus(client, CAFE_OWNER)


def test_one_above_the_threshold_does_not_open_an_alert(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 9)  # 20 -> 11
    assert "MILK-1L" not in alert_skus(client, CAFE_OWNER)


def test_running_out_of_stock_is_critical(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 20)
    row = next(row for row in alerts(client, CAFE_OWNER) if row["sku"] == "MILK-1L")
    assert row["urgency"] == "critical" and row["stock_status"] == "out_of_stock"


def test_creating_a_product_that_starts_low_opens_an_alert(client):
    payload = {"name": "Vanilla Syrup", "sku": "SYR-VAN", "category": "Syrups", "unit": "bottles", "quantity": 2, "reorder_threshold": 3}
    assert client.post("/api/inventory", headers=CAFE_OWNER, json=payload).status_code == 201
    assert "SYR-VAN" in alert_skus(client, CAFE_OWNER)


def test_creating_a_healthy_product_opens_no_alert(client):
    payload = {"name": "Vanilla Syrup", "sku": "SYR-VAN", "category": "Syrups", "unit": "bottles", "quantity": 8, "reorder_threshold": 3}
    client.post("/api/inventory", headers=CAFE_OWNER, json=payload)
    assert "SYR-VAN" not in alert_skus(client, CAFE_OWNER)


# ---------------------------------------------------------------- no duplicates

def test_further_drops_do_not_create_a_second_alert(client, db_session):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 15)
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 2)
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 3)  # now 0

    assert len(db_alerts_for(db_session, "MILK-1L")) == 1
    opened = [e for e in db_session.scalars(select(ActivityLog).where(ActivityLog.action == "alert.opened")) if json.loads(e.new_value)["item_id"] == milk["id"]]
    assert len(opened) == 1
    # ...but the alert shows the live numbers and the higher urgency
    row = next(row for row in alerts(client, CAFE_OWNER) if row["sku"] == "MILK-1L")
    assert (row["quantity"], row["urgency"]) == (0, "critical")


def test_retrying_the_same_request_id_creates_only_one_alert(client, db_session):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    request_id = str(uuid.uuid4())
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 15, request_id=request_id)
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 15, request_id=request_id)
    assert len(db_alerts_for(db_session, "MILK-1L")) == 1
    assert find_item(client, CAFE_OWNER, "MILK-1L")["quantity"] == 5


def test_database_refuses_a_second_open_alert_for_the_same_item(db_session):
    """Safety net below the code: a partial unique index blocks duplicates."""
    existing = db_session.scalars(select(StockAlert).where(StockAlert.status == "open")).first()
    db_session.add(
        StockAlert(business_id=existing.business_id, item_id=existing.item_id, quantity_at_alert=1, threshold_at_alert=5)
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_a_resolved_alert_does_not_block_a_new_one(db_session):
    """The unique rule only covers OPEN alerts, so history can pile up."""
    existing = db_session.scalars(select(StockAlert).where(StockAlert.status == "open")).first()
    existing.status = "resolved"
    db_session.commit()
    db_session.add(
        StockAlert(business_id=existing.business_id, item_id=existing.item_id, quantity_at_alert=1, threshold_at_alert=5)
    )
    db_session.commit()  # must not raise


# ---------------------------------------------------------------- auto-resolve

def test_restocking_above_the_threshold_resolves_the_alert(client, db_session):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 15)  # 5, alert open
    move(client, CAFE_EMPLOYEE, milk["id"], "in", 6)    # 11 > 10

    assert "MILK-1L" not in alert_skus(client, CAFE_OWNER, "open")
    resolved = next(row for row in alerts(client, CAFE_OWNER, "resolved") if row["sku"] == "MILK-1L")
    assert resolved["status"] == "resolved"
    assert resolved["resolution"] == "replenished"
    assert resolved["resolved_at"] is not None
    assert resolved["urgency"] is None

    log = [e for e in db_session.scalars(select(ActivityLog).where(ActivityLog.action == "alert.resolved")) if json.loads(e.new_value)["quantity"] == 11]
    assert len(log) == 1 and log[0].user_id == 2


def test_partial_restock_that_is_still_low_keeps_the_alert_open(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 15)  # 5
    move(client, CAFE_EMPLOYEE, milk["id"], "in", 5)    # 10 == threshold, still low
    assert "MILK-1L" in alert_skus(client, CAFE_OWNER)


def test_restocking_an_out_of_stock_product_resolves_when_above_threshold(client):
    chocolate = find_item(client, CAFE_OWNER, "CHOC-500")  # 0 left, threshold 4
    assert "CHOC-500" in alert_skus(client, CAFE_OWNER)
    move(client, CAFE_EMPLOYEE, chocolate["id"], "in", 4)  # 4 == threshold
    assert "CHOC-500" in alert_skus(client, CAFE_OWNER)
    move(client, CAFE_EMPLOYEE, chocolate["id"], "in", 1)  # 5 > 4
    assert "CHOC-500" not in alert_skus(client, CAFE_OWNER)


def test_running_low_again_creates_a_new_alert_and_keeps_the_old_one(client, db_session):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 15)
    move(client, CAFE_EMPLOYEE, milk["id"], "in", 10)   # resolved at 15
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 12)  # 3 left, new alert

    history = db_alerts_for(db_session, "MILK-1L")
    assert [a.status for a in history] == ["resolved", "open"]
    assert len(alerts(client, CAFE_OWNER, "all")) >= 5


# ---------------------------------------------------------------- customising thresholds

def test_owner_raising_the_threshold_opens_an_alert(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")  # 20 cartons
    assert client.patch(f"/api/inventory/{milk['id']}", headers=CAFE_OWNER, json={"reorder_threshold": 25}).status_code == 200
    row = next(row for row in alerts(client, CAFE_OWNER) if row["sku"] == "MILK-1L")
    assert (row["quantity"], row["reorder_threshold"]) == (20, 25)


def test_owner_lowering_the_threshold_resolves_the_alert(client):
    cups = find_item(client, CAFE_OWNER, "LID-12OZ")  # 11 left, threshold 15, alert open
    assert "LID-12OZ" in alert_skus(client, CAFE_OWNER)
    client.patch(f"/api/inventory/{cups['id']}", headers=CAFE_OWNER, json={"reorder_threshold": 5})
    assert "LID-12OZ" not in alert_skus(client, CAFE_OWNER)
    resolved = next(row for row in alerts(client, CAFE_OWNER, "resolved") if row["sku"] == "LID-12OZ")
    assert resolved["resolution"] == "threshold_changed"


def test_editing_other_fields_does_not_touch_alerts(client, db_session):
    lids = find_item(client, CAFE_OWNER, "LID-12OZ")
    before = len(db_alerts_for(db_session, "LID-12OZ"))
    client.patch(f"/api/inventory/{lids['id']}", headers=CAFE_OWNER, json={"name": "Cup Lids 12oz (50 pcs) - new pack"})
    assert len(db_alerts_for(db_session, "LID-12OZ")) == before
    assert "LID-12OZ" in alert_skus(client, CAFE_OWNER)


def test_employee_cannot_change_thresholds(client):
    lids = find_item(client, CAFE_OWNER, "LID-12OZ")
    assert client.patch(f"/api/inventory/{lids['id']}", headers=CAFE_EMPLOYEE, json={"reorder_threshold": 1}).status_code == 403
    assert "LID-12OZ" in alert_skus(client, CAFE_OWNER)


# ---------------------------------------------------------------- archive / restore

def test_archiving_a_product_closes_its_alert_and_restoring_reopens_it(client):
    lids = find_item(client, CAFE_OWNER, "LID-12OZ")
    client.post(f"/api/inventory/{lids['id']}/archive", headers=CAFE_OWNER)
    assert "LID-12OZ" not in alert_skus(client, CAFE_OWNER)
    resolved = next(row for row in alerts(client, CAFE_OWNER, "resolved") if row["sku"] == "LID-12OZ")
    assert resolved["resolution"] == "archived"

    client.post(f"/api/inventory/{lids['id']}/restore", headers=CAFE_OWNER)
    assert "LID-12OZ" in alert_skus(client, CAFE_OWNER)  # still low, so a fresh alert


def test_archived_healthy_product_gets_no_alert_on_restore(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    client.post(f"/api/inventory/{milk['id']}/archive", headers=CAFE_OWNER)
    client.post(f"/api/inventory/{milk['id']}/restore", headers=CAFE_OWNER)
    assert "MILK-1L" not in alert_skus(client, CAFE_OWNER)


# ---------------------------------------------------------------- urgent products listing

def test_open_alerts_are_sorted_most_urgent_first(client):
    rows = alerts(client, CAFE_OWNER)
    ranks = {"critical": 0, "urgent": 1, "low": 2}
    assert [ranks[row["urgency"]] for row in rows] == sorted(ranks[row["urgency"]] for row in rows)
    assert rows[0]["sku"] == "CHOC-500"  # out of stock comes first


def test_alert_rows_contain_the_product_details_the_page_needs(client):
    row = next(row for row in alerts(client, CAFE_OWNER) if row["sku"] == "COFB-ROB")
    assert row["item_name"] == "Robusta Coffee Beans 1kg"
    assert row["category"] == "Coffee"
    assert row["unit"] == "bags"
    assert row["supplier_name"].startswith("Kopi Borneo")
    assert (row["quantity"], row["reorder_threshold"], row["shortfall"]) == (4, 5, 1)


def test_summary_counts(client):
    assert client.get("/api/alerts/summary", headers=CAFE_OWNER).json() == {
        "open": 3, "critical": 1, "urgent": 0, "low": 2, "resolved": 0,
    }
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 15)  # becomes urgent
    after = client.get("/api/alerts/summary", headers=CAFE_OWNER).json()
    assert (after["open"], after["urgent"]) == (4, 1)
    move(client, CAFE_EMPLOYEE, milk["id"], "in", 10)   # resolved again
    final = client.get("/api/alerts/summary", headers=CAFE_OWNER).json()
    assert (final["open"], final["resolved"]) == (3, 1)


def test_status_filter(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 15)
    move(client, CAFE_EMPLOYEE, milk["id"], "in", 10)
    assert "MILK-1L" not in alert_skus(client, CAFE_OWNER, "open")
    assert alert_skus(client, CAFE_OWNER, "resolved") == {"MILK-1L"}
    assert {"MILK-1L", "CHOC-500"} <= alert_skus(client, CAFE_OWNER, "all")
    assert client.get("/api/alerts", headers=CAFE_OWNER, params={"status": "bogus"}).status_code == 422


# ---------------------------------------------------------------- permissions & separation

def test_alerts_require_a_session(client):
    assert client.get("/api/alerts").status_code == 401
    assert client.get("/api/alerts/summary").status_code == 401
    assert client.get("/api/alerts", headers={"X-User-Id": "9999"}).status_code == 401


def test_employees_can_view_alerts(client):
    assert client.get("/api/alerts", headers=CAFE_EMPLOYEE).status_code == 200
    assert client.get("/api/alerts/summary", headers=CAFE_EMPLOYEE).status_code == 200


def test_alerts_cannot_be_created_or_edited_through_the_api(client):
    """Alerts are automatic. There is no way to write them by hand."""
    assert client.post("/api/alerts", headers=CAFE_OWNER, json={"item_id": 1}).status_code == 405
    assert client.delete("/api/alerts/1", headers=CAFE_OWNER).status_code in (404, 405)
    assert client.patch("/api/alerts/1", headers=CAFE_OWNER, json={"status": "resolved"}).status_code in (404, 405)


def test_each_business_only_sees_its_own_alerts(client):
    assert alert_skus(client, CAFE_OWNER).isdisjoint(alert_skus(client, SHOP_OWNER))
    assert "SOY-500" not in alert_skus(client, CAFE_EMPLOYEE)
    assert "SOY-500" in alert_skus(client, SHOP_EMPLOYEE)
    shop_summary = client.get("/api/alerts/summary", headers=SHOP_OWNER).json()
    assert shop_summary["open"] == 2


def test_stock_changes_in_one_business_do_not_affect_the_others_alerts(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 15)
    assert alert_skus(client, SHOP_OWNER) == {"SOY-500", "EGG-A30"}


def test_orbyte_context_lists_the_alerts_permission(client):
    permissions = client.get("/api/orbyte-mock/context", headers=CAFE_EMPLOYEE).json()["permissions"]
    assert "alerts:view" in permissions
