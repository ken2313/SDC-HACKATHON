"""Feature 5 tests: supplier order tracking and delivery confirmation.

Run from the backend folder:   pytest -v

Café scenario used throughout (Kopi Kita Café, user 1 = owner, user 2 = employee):
  MILK-1L 20 cartons, reorder 10. The employee removes 15 -> 5 left -> draft order of
  15 cartons from Segar Dairy -> the owner approves -> tracking starts.
"""
import json
from datetime import timedelta

from sqlalchemy import select, update

from app.models import ActivityLog, OrderStatusHistory, PurchaseOrder, StockMovement
from app.services.order_tracking_service import backfill_history, today_my
from tests.conftest import CAFE_EMPLOYEE, CAFE_OWNER, SHOP_EMPLOYEE, SHOP_OWNER, find_item


def move(client, headers, item_id, movement_type, quantity):
    return client.post(
        f"/api/inventory/{item_id}/movements",
        headers=headers,
        json={"movement_type": movement_type, "quantity": quantity},
    )


def approved_milk_order(client):
    """Employee removes 15 milk; owner approves the draft. Returns (milk, order_id)."""
    milk = find_item(client, CAFE_EMPLOYEE, "MILK-1L")
    assert move(client, CAFE_EMPLOYEE, milk["id"], "out", 15).status_code == 201
    order_id = client.get("/api/purchase-orders", headers=CAFE_OWNER).json()[0]["id"]
    assert client.post(f"/api/purchase-orders/{order_id}/approve", headers=CAFE_OWNER).status_code == 200
    return milk, order_id


def placed_milk_order(client):
    milk, order_id = approved_milk_order(client)
    assert client.post(f"/api/supplier-orders/{order_id}/place", headers=CAFE_OWNER).status_code == 200
    return milk, order_id


def get_order(client, order_id, headers=CAFE_OWNER):
    response = client.get(f"/api/supplier-orders/{order_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def receive(client, order_id, quantities, headers=CAFE_EMPLOYEE, note=None):
    """quantities: received quantity per line, in line order."""
    lines = get_order(client, order_id)["lines"]
    body = {"lines": [{"line_id": line["id"], "received_quantity": q} for line, q in zip(lines, quantities)]}
    if note:
        body["note"] = note
    return client.post(f"/api/supplier-orders/{order_id}/receive", headers=headers, json=body)


def milk_quantity(client):
    return find_item(client, CAFE_OWNER, "MILK-1L")["quantity"]


# ---------------------------------------------------------------- what is tracked

def test_only_approved_orders_are_tracked(client):
    milk = find_item(client, CAFE_EMPLOYEE, "MILK-1L")
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 15)
    draft_id = client.get("/api/purchase-orders", headers=CAFE_OWNER).json()[0]["id"]
    assert client.get("/api/supplier-orders", headers=CAFE_OWNER, params={"view": "all"}).json() == []
    assert client.get(f"/api/supplier-orders/{draft_id}", headers=CAFE_OWNER).status_code == 404

    client.post(f"/api/purchase-orders/{draft_id}/approve", headers=CAFE_OWNER)
    found = client.get("/api/supplier-orders", headers=CAFE_OWNER).json()
    assert [o["id"] for o in found] == [draft_id]
    assert found[0]["status"] == "approved"
    assert found[0]["next_statuses"] == ["ordered", "cancelled"]
    assert found[0]["inventory_applied"] is False


def test_history_starts_with_creation_and_approval(client):
    _milk, order_id = approved_milk_order(client)
    history = get_order(client, order_id)["history"]
    assert [(h["from_status"], h["to_status"]) for h in history] == [(None, "draft"), ("draft", "approved")]
    assert history[0]["user_name"] == "Hafiz Ismail"
    assert history[1]["user_name"] == "Aisyah Rahman"


def test_invalid_view_is_rejected(client):
    assert client.get("/api/supplier-orders", headers=CAFE_OWNER, params={"view": "nope"}).status_code == 422


# ---------------------------------------------------------------- permissions

def test_employee_cannot_place_or_cancel(client, db_session):
    _milk, order_id = approved_milk_order(client)
    assert client.post(f"/api/supplier-orders/{order_id}/place", headers=CAFE_EMPLOYEE).status_code == 403
    assert client.post(
        f"/api/supplier-orders/{order_id}/cancel", headers=CAFE_EMPLOYEE, json={"reason": "changed my mind"}
    ).status_code == 403
    assert get_order(client, order_id)["status"] == "approved"
    denied = db_session.scalars(select(ActivityLog).where(ActivityLog.action == "access.denied")).all()
    assert {json.loads(row.new_value)["permission_needed"] for row in denied} == {"orders:place"}


def test_employee_can_update_shipping_and_confirm_delivery(client):
    _milk, order_id = placed_milk_order(client)
    shipped = client.post(f"/api/supplier-orders/{order_id}/status", headers=CAFE_EMPLOYEE, json={"status": "shipped"})
    assert shipped.status_code == 200, shipped.text
    assert shipped.json()["status"] == "shipped"
    assert receive(client, order_id, [15], headers=CAFE_EMPLOYEE).status_code == 200


def test_tracking_needs_a_session_and_the_right_business(client):
    _milk, order_id = approved_milk_order(client)
    assert client.get("/api/supplier-orders").status_code == 401
    assert client.get(f"/api/supplier-orders/{order_id}", headers=SHOP_OWNER).status_code == 404
    assert client.post(f"/api/supplier-orders/{order_id}/place", headers=SHOP_OWNER).status_code == 404
    assert client.get("/api/supplier-orders", headers=SHOP_EMPLOYEE, params={"view": "all"}).json() == []


# ---------------------------------------------------------------- placing and moving

def test_place_order_is_simulated_and_sets_expected_date(client, db_session):
    _milk, order_id = approved_milk_order(client)
    placed = client.post(f"/api/supplier-orders/{order_id}/place", headers=CAFE_OWNER).json()
    assert placed["status"] == "ordered"
    expected = today_my() + timedelta(days=placed["lead_time_days"])
    assert placed["estimated_delivery_date"] == expected.isoformat()
    assert placed["next_statuses"] == ["shipped", "delayed", "delivered", "cancelled"]
    note = placed["history"][-1]["note"]
    assert "Simulated" in note

    entry = db_session.scalars(select(ActivityLog).where(ActivityLog.action == "po.placed")).one()
    assert entry.user_id == 1
    assert json.loads(entry.new_value)["simulated"] is True
    assert json.loads(entry.old_value)["status"] == "approved"


def test_steps_cannot_be_skipped_or_repeated(client):
    _milk, order_id = approved_milk_order(client)
    # approved -> shipped is not allowed (must be placed first)
    assert client.post(f"/api/supplier-orders/{order_id}/status", headers=CAFE_OWNER, json={"status": "shipped"}).status_code == 409
    # approved orders cannot receive goods
    assert receive(client, order_id, [15], headers=CAFE_OWNER).status_code == 409
    assert client.post(f"/api/supplier-orders/{order_id}/place", headers=CAFE_OWNER).status_code == 200
    assert client.post(f"/api/supplier-orders/{order_id}/place", headers=CAFE_OWNER).status_code == 409
    assert client.post(f"/api/supplier-orders/{order_id}/status", headers=CAFE_OWNER, json={"status": "shipped"}).status_code == 200
    assert client.post(f"/api/supplier-orders/{order_id}/status", headers=CAFE_OWNER, json={"status": "shipped"}).status_code == 409


def test_status_endpoint_only_accepts_shipped_or_delayed(client):
    _milk, order_id = placed_milk_order(client)
    for status in ("delivered", "cancelled", "ordered", "approved", "nonsense"):
        response = client.post(f"/api/supplier-orders/{order_id}/status", headers=CAFE_OWNER, json={"status": status})
        assert response.status_code == 422, status
    assert get_order(client, order_id)["status"] == "ordered"


def test_delay_needs_a_future_date_and_can_recover(client):
    _milk, order_id = placed_milk_order(client)
    url = f"/api/supplier-orders/{order_id}/status"
    assert client.post(url, headers=CAFE_EMPLOYEE, json={"status": "delayed"}).status_code == 422
    yesterday = (today_my() - timedelta(days=1)).isoformat()
    assert client.post(url, headers=CAFE_EMPLOYEE, json={"status": "delayed", "estimated_delivery_date": yesterday}).status_code == 422

    new_date = (today_my() + timedelta(days=10)).isoformat()
    delayed = client.post(url, headers=CAFE_EMPLOYEE, json={"status": "delayed", "estimated_delivery_date": new_date, "note": "Truck broke down"})
    assert delayed.status_code == 200, delayed.text
    body = delayed.json()
    assert body["status"] == "delayed"
    assert body["estimated_delivery_date"] == new_date
    assert body["history"][-1]["note"] == "Truck broke down"
    # delayed -> shipped is allowed
    assert client.post(url, headers=CAFE_EMPLOYEE, json={"status": "shipped"}).json()["status"] == "shipped"


# ---------------------------------------------------------------- overdue

def test_overdue_orders_are_identified(client, db_session):
    _milk, order_id = placed_milk_order(client)
    assert get_order(client, order_id)["is_overdue"] is False
    assert client.get("/api/supplier-orders", headers=CAFE_OWNER, params={"view": "overdue"}).json() == []

    db_session.execute(
        update(PurchaseOrder).where(PurchaseOrder.id == order_id).values(estimated_delivery_date=today_my() - timedelta(days=3))
    )
    db_session.commit()

    order = get_order(client, order_id)
    assert order["is_overdue"] is True
    assert order["days_overdue"] == 3
    assert order["status"] == "ordered"   # nothing changes status by itself
    overdue = client.get("/api/supplier-orders", headers=CAFE_OWNER, params={"view": "overdue"}).json()
    assert [o["id"] for o in overdue] == [order_id]
    assert client.get("/api/supplier-orders/summary", headers=CAFE_OWNER).json()["overdue"] == 1


def test_approved_but_not_placed_order_is_never_overdue(client, db_session):
    _milk, order_id = approved_milk_order(client)
    db_session.execute(
        update(PurchaseOrder).where(PurchaseOrder.id == order_id).values(estimated_delivery_date=today_my() - timedelta(days=9))
    )
    db_session.commit()
    assert get_order(client, order_id)["is_overdue"] is False


def test_summary_counts(client):
    _milk, order_id = placed_milk_order(client)
    summary = client.get("/api/supplier-orders/summary", headers=CAFE_EMPLOYEE).json()
    assert summary["in_transit"] == 1
    assert summary["awaiting_placement"] == 0
    assert summary["due_next_7_days"] == 1
    assert summary["delivered"] == 0
    receive(client, order_id, [15])
    summary = client.get("/api/supplier-orders/summary", headers=CAFE_EMPLOYEE).json()
    assert summary["in_transit"] == 0
    assert summary["delivered"] == 1


# ---------------------------------------------------------------- the delivery

def test_confirmed_delivery_updates_inventory_and_resolves_the_alert(client, db_session):
    milk, order_id = placed_milk_order(client)
    assert milk_quantity(client) == 5

    response = receive(client, order_id, [15], note="Checked against the delivery note")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["order"]["status"] == "delivered"
    assert body["order"]["inventory_applied"] is True
    assert body["order"]["lines"][0]["received_quantity"] == 15
    assert body["stock_updates"] == [{"item_name": "Fresh Milk 1L", "unit": "cartons", "added": 15, "new_quantity": 20}]
    assert body["follow_up_drafts"] == []
    assert body["order"]["history"][-1]["to_status"] == "delivered"

    assert milk_quantity(client) == 20
    open_alerts = client.get("/api/alerts", headers=CAFE_OWNER, params={"status": "open"}).json()
    assert all(alert["item_id"] != milk["id"] for alert in open_alerts)

    movement = db_session.scalars(select(StockMovement).where(StockMovement.reason == "Delivery PO-0001")).one()
    assert (movement.quantity_before, movement.quantity_after, movement.quantity_change) == (5, 20, 15)
    assert movement.user_id == 2

    delivered = db_session.scalars(select(ActivityLog).where(ActivityLog.action == "po.delivered")).one()
    payload = json.loads(delivered.new_value)
    assert (payload["ordered"], payload["received"], payload["short_delivery"]) == (15, 15, False)
    assert payload["note"] == "Checked against the delivery note"


def test_a_delivery_can_never_update_inventory_twice(client, db_session):
    _milk, order_id = placed_milk_order(client)
    assert receive(client, order_id, [15]).status_code == 200
    assert milk_quantity(client) == 20

    second = receive(client, order_id, [15])
    assert second.status_code == 409
    assert "already" in second.json()["detail"].lower()
    assert milk_quantity(client) == 20
    assert len(db_session.scalars(select(StockMovement).where(StockMovement.reason == "Delivery PO-0001")).all()) == 1
    assert len(db_session.scalars(select(ActivityLog).where(ActivityLog.action == "po.delivered")).all()) == 1


def test_database_blocks_a_second_stock_update_even_if_the_flags_are_reset(client, db_session):
    """Last line of defence: even if someone reset the order's status AND the applied flag,
    the unique request_id on the stock movement refuses a second update, and nothing changes."""
    _milk, order_id = placed_milk_order(client)
    assert receive(client, order_id, [15]).status_code == 200
    db_session.execute(
        update(PurchaseOrder).where(PurchaseOrder.id == order_id).values(status="shipped", inventory_applied=False)
    )
    db_session.commit()

    again = receive(client, order_id, [15])
    assert again.status_code == 409
    assert milk_quantity(client) == 20
    assert get_order(client, order_id)["status"] == "shipped"  # the failed attempt rolled back completely


def test_short_delivery_adds_only_what_arrived_and_prepares_a_new_draft(client):
    _milk, order_id = placed_milk_order(client)
    response = receive(client, order_id, [3])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["order"]["status"] == "delivered"
    assert body["stock_updates"][0]["added"] == 3
    assert milk_quantity(client) == 8          # 5 + 3, still at or below the level of 10
    assert len(body["follow_up_drafts"]) == 1   # the system prepares a new DRAFT, it does not order
    drafts = client.get("/api/purchase-orders", headers=CAFE_OWNER, params={"status": "draft"}).json()
    assert any(d["po_number"] == body["follow_up_drafts"][0] for d in drafts)


def test_delivery_validation(client):
    _milk, order_id = placed_milk_order(client)
    line_id = get_order(client, order_id)["lines"][0]["id"]
    url = f"/api/supplier-orders/{order_id}/receive"

    assert client.post(url, headers=CAFE_EMPLOYEE, json={"lines": []}).status_code == 422
    assert client.post(url, headers=CAFE_EMPLOYEE, json={"lines": [{"line_id": line_id, "received_quantity": -1}]}).status_code == 422
    assert client.post(url, headers=CAFE_EMPLOYEE, json={"lines": [{"line_id": line_id, "received_quantity": 0}]}).status_code == 422
    assert client.post(url, headers=CAFE_EMPLOYEE, json={"lines": [{"line_id": 99999, "received_quantity": 5}]}).status_code == 404
    twice = {"lines": [{"line_id": line_id, "received_quantity": 5}, {"line_id": line_id, "received_quantity": 5}]}
    assert client.post(url, headers=CAFE_EMPLOYEE, json=twice).status_code == 422
    assert client.post(url, headers=CAFE_EMPLOYEE, json={"lines": [{"line_id": line_id, "received_quantity": 1.5}]}).status_code == 422
    assert client.post(url, headers=CAFE_EMPLOYEE, json={"lines": [{"line_id": line_id, "received_quantity": 5}], "extra": 1}).status_code == 422

    # nothing above changed anything
    assert milk_quantity(client) == 5
    assert get_order(client, order_id)["status"] == "ordered"


def test_every_line_must_be_reported(client):
    # Two products from the same supplier on one order
    milk = find_item(client, CAFE_EMPLOYEE, "MILK-1L")
    oat = find_item(client, CAFE_EMPLOYEE, "OATM-1L")
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 15)
    move(client, CAFE_EMPLOYEE, oat["id"], "out", 10)
    orders = client.get("/api/purchase-orders", headers=CAFE_OWNER, params={"status": "draft"}).json()
    order = next(o for o in orders if len(o["lines"]) == 2)
    client.post(f"/api/purchase-orders/{order['id']}/approve", headers=CAFE_OWNER)
    client.post(f"/api/supplier-orders/{order['id']}/place", headers=CAFE_OWNER)

    first_line = order["lines"][0]["id"]
    partial = client.post(
        f"/api/supplier-orders/{order['id']}/receive", headers=CAFE_EMPLOYEE,
        json={"lines": [{"line_id": first_line, "received_quantity": 1}]},
    )
    assert partial.status_code == 422
    assert get_order(client, order["id"])["status"] == "ordered"

    full = receive(client, order["id"], [order["lines"][0]["quantity_ordered"], 0])
    assert full.status_code == 200, full.text
    assert len(full.json()["stock_updates"]) == 1   # the line with 0 received changes no stock


def test_archived_product_blocks_receiving(client):
    milk, order_id = placed_milk_order(client)
    assert client.post(f"/api/inventory/{milk['id']}/archive", headers=CAFE_OWNER).status_code == 200
    response = receive(client, order_id, [15])
    assert response.status_code == 409
    assert "archived" in response.json()["detail"].lower()
    assert get_order(client, order_id)["status"] == "ordered"


# ---------------------------------------------------------------- cancel

def test_cancel_needs_a_reason_and_frees_the_product(client):
    _milk, order_id = placed_milk_order(client)
    url = f"/api/supplier-orders/{order_id}/cancel"
    assert client.post(url, headers=CAFE_OWNER, json={}).status_code == 422
    assert client.post(url, headers=CAFE_OWNER, json={"reason": "  "}).status_code == 422

    cancelled = client.post(url, headers=CAFE_OWNER, json={"reason": "Supplier out of stock"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["history"][-1]["note"] == "Supplier out of stock"

    # the product is no longer claimed by an outstanding order, so a new draft can be prepared
    generated = client.post("/api/purchase-orders/generate", headers=CAFE_OWNER).json()
    assert generated["created_orders"] >= 1
    assert milk_quantity(client) == 5   # cancelling never touches stock


def test_delivered_or_cancelled_orders_are_final(client):
    _milk, order_id = placed_milk_order(client)
    receive(client, order_id, [15])
    assert client.post(f"/api/supplier-orders/{order_id}/cancel", headers=CAFE_OWNER, json={"reason": "too late now"}).status_code == 409
    assert client.post(f"/api/supplier-orders/{order_id}/status", headers=CAFE_OWNER, json={"status": "shipped"}).status_code == 409
    assert client.post(f"/api/supplier-orders/{order_id}/place", headers=CAFE_OWNER).status_code == 409


# ---------------------------------------------------------------- audit trail

def test_whole_workflow_is_in_the_activity_log(client):
    _milk, order_id = placed_milk_order(client)
    client.post(f"/api/supplier-orders/{order_id}/status", headers=CAFE_EMPLOYEE, json={"status": "shipped"})
    receive(client, order_id, [15])
    logged = client.get("/api/activity-logs", headers=CAFE_OWNER, params={"limit": 200}).json()["items"]
    actions = [row["action"] for row in logged]
    for expected in ("stock.out", "alert.opened", "po.generated", "po.approved", "po.placed", "po.shipped", "po.delivered", "stock.in", "alert.resolved"):
        assert expected in actions, expected
    delivered = next(row for row in logged if row["action"] == "po.delivered")
    assert delivered["action_label"] == "Delivery confirmed"
    assert delivered["user_name"] == "Hafiz Ismail"
    assert delivered["entity_label"] == "PO-0001"


# ---------------------------------------------------------------- orders from before Feature 5

def test_backfill_gives_old_orders_a_timeline(client, db_session):
    _milk, order_id = approved_milk_order(client)
    for row in db_session.scalars(select(OrderStatusHistory)).all():
        db_session.delete(row)
    db_session.commit()
    assert get_order(client, order_id)["history"] == []

    assert backfill_history(db_session) >= 1
    history = get_order(client, order_id)["history"]
    assert [(h["from_status"], h["to_status"]) for h in history] == [(None, "draft"), ("draft", "approved")]
    assert backfill_history(db_session) == 0   # safe to repeat
