"""Feature 7 tests: inventory dashboard and synthetic stock history.

Run from the backend folder:   pytest -v

Seeded café stock (Kopi Kita Café, user 1 = owner, user 2 = employee), 10 products:
  low:  Robusta 4/5, Cup Lids 11/15      out: Chocolate 0/4      the other 7 are in stock
"""
from datetime import timedelta

from sqlalchemy import select, update

from app.models import InventoryItem, PurchaseOrder, StockMovement
from app.seed.history_data import HISTORY_DAYS, build_history, seed_history_if_missing
from app.services.dashboard_service import today_my
from tests.conftest import CAFE_EMPLOYEE, CAFE_OWNER, SHOP_OWNER, find_item


def overview(client, headers=CAFE_OWNER):
    response = client.get("/api/dashboard", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def trend(client, item_id, headers=CAFE_OWNER, days=30):
    response = client.get("/api/dashboard/trend", headers=headers, params={"item_id": item_id, "days": days})
    assert response.status_code == 200, response.text
    return response.json()


def remove_milk(client, quantity=15):
    milk = find_item(client, CAFE_EMPLOYEE, "MILK-1L")
    response = client.post(
        f"/api/inventory/{milk['id']}/movements",
        headers=CAFE_EMPLOYEE,
        json={"movement_type": "out", "quantity": quantity},
    )
    assert response.status_code == 201, response.text
    return milk


# ---------------------------------------------------------------- counts

def test_overview_counts_for_employee(client):
    data = overview(client, CAFE_EMPLOYEE)
    assert data["stock"] == {"total_products": 10, "in_stock": 7, "low_stock": 2, "out_of_stock": 1, "archived": 0}
    assert data["alerts"] == {"open": 3, "critical": 1, "urgent": 0}
    assert data["orders"]["pending_approval"] == 0
    assert data["orders"]["delayed_or_overdue"] == 0
    assert data["upcoming_deliveries"] == []
    assert data["financials"] is None  # money totals are owner-only
    assert data["anomalies"]["available"] is False  # Feature 9 is not built yet
    assert data["urgent_products"][0]["sku"] == "CHOC-500"  # out of stock comes first


def test_owner_sees_money_totals(client):
    money = overview(client, CAFE_OWNER)["financials"]
    # quantity x cheapest active supplier price, summed over the 10 café products
    assert money["stock_value"] == 2362.0
    assert money["products_without_price"] == 0
    assert money["pending_approval_value"] == 0
    assert money["on_order_value"] == 0
    assert money["received_last_30_days"] == 0


def test_dashboard_needs_a_signed_in_user(client):
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/dashboard/trend", params={"item_id": 1}).status_code == 401


def test_roles_table_shows_reports_are_owner_only(client):
    rules = {row["key"]: row["allowed"] for row in client.get("/api/access/matrix", headers=CAFE_EMPLOYEE).json()["permissions"]}
    assert rules["reports:view"] == {"owner": True, "employee": False}


def test_status_by_category(client):
    rows = {row["category"]: row for row in overview(client)["status_by_category"]}
    assert rows["Packaging"] == {"category": "Packaging", "in_stock": 1, "low_stock": 1, "out_of_stock": 0}
    assert rows["Beverage Mix"]["out_of_stock"] == 1
    assert rows["Dairy"]["in_stock"] == 2
    order = [row["category"] for row in overview(client)["status_by_category"]]
    assert set(order[:3]) == {"Beverage Mix", "Coffee", "Packaging"}  # categories with problems first


def test_archived_products_are_not_counted(client):
    croissant = find_item(client, CAFE_OWNER, "CROI-FRZ")
    client.post(f"/api/inventory/{croissant['id']}/archive", headers=CAFE_OWNER)
    stock = overview(client)["stock"]
    assert stock["total_products"] == 9 and stock["archived"] == 1
    assert croissant["id"] not in [p["item_id"] for p in overview(client)["trend_products"]]


def test_dashboard_is_separated_per_business(client):
    assert overview(client, SHOP_OWNER)["stock"]["total_products"] == 6
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    assert client.get("/api/dashboard/trend", headers=SHOP_OWNER, params={"item_id": milk["id"]}).status_code == 404


# ---------------------------------------------------------------- the café workflow on the dashboard

def test_low_stock_and_draft_show_up(client):
    remove_milk(client)
    data = overview(client)
    assert data["stock"]["low_stock"] == 3
    assert data["orders"]["pending_approval"] == 1
    assert data["financials"]["pending_approval_value"] == 117.0
    milk_row = next(p for p in data["urgent_products"] if p["sku"] == "MILK-1L")
    assert milk_row["urgency"] == "urgent"
    assert milk_row["order_po_number"] == "PO-0001" and milk_row["order_status"] == "draft"
    latest = data["recent_activity"][0]
    assert latest["item_name"] == "Fresh Milk 1L"
    assert latest["quantity_change"] == -15
    assert (latest["quantity_before"], latest["quantity_after"]) == (20, 5)
    assert latest["user_name"] == "Hafiz Ismail"


def test_deliveries_delays_and_overdue(client, db_session):
    remove_milk(client)
    order_id = client.get("/api/purchase-orders", headers=CAFE_OWNER).json()[0]["id"]
    client.post(f"/api/purchase-orders/{order_id}/approve", headers=CAFE_OWNER)
    data = overview(client)
    assert data["orders"]["approved_not_placed"] == 1
    assert data["financials"]["on_order_value"] == 117.0

    client.post(f"/api/supplier-orders/{order_id}/place", headers=CAFE_OWNER)
    data = overview(client, CAFE_EMPLOYEE)
    assert data["orders"]["awaiting_delivery"] == 1
    delivery = data["upcoming_deliveries"][0]
    assert delivery["po_number"] == "PO-0001"
    assert delivery["supplier_name"] == "Segar Dairy Sdn Bhd (demo)"
    assert delivery["days_until"] == 1  # Segar usually delivers in 1 day
    assert delivery["is_overdue"] is False

    new_date = (today_my() + timedelta(days=3)).isoformat()
    response = client.post(
        f"/api/supplier-orders/{order_id}/status", headers=CAFE_EMPLOYEE,
        json={"status": "delayed", "estimated_delivery_date": new_date},
    )
    assert response.status_code == 200, response.text
    assert overview(client)["orders"]["delayed"] == 1
    assert overview(client)["orders"]["delayed_or_overdue"] == 1

    # Testing shortcut: move the expected date into the past
    db_session.execute(
        update(PurchaseOrder).where(PurchaseOrder.id == order_id)
        .values(estimated_delivery_date=today_my() - timedelta(days=2))
    )
    db_session.commit()
    data = overview(client)
    assert data["orders"]["overdue"] == 1
    assert data["orders"]["delayed_or_overdue"] == 1  # the same order is counted once
    assert data["upcoming_deliveries"][0]["is_overdue"] is True
    assert data["upcoming_deliveries"][0]["days_until"] == -2

    lines = client.get(f"/api/supplier-orders/{order_id}", headers=CAFE_OWNER).json()["lines"]
    client.post(
        f"/api/supplier-orders/{order_id}/receive", headers=CAFE_EMPLOYEE,
        json={"lines": [{"line_id": lines[0]["id"], "received_quantity": 15}]},
    )
    data = overview(client)
    assert data["orders"]["awaiting_delivery"] == 0
    assert data["upcoming_deliveries"] == []
    assert data["financials"]["received_last_30_days"] == 117.0
    assert data["financials"]["on_order_value"] == 0


# ---------------------------------------------------------------- trend

def test_trend_without_history(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    data = trend(client, milk["id"], CAFE_EMPLOYEE)
    assert len(data["points"]) == 30
    assert data["points"][-1]["date"] == today_my().isoformat()
    assert data["points"][-1]["quantity"] == 20
    assert data["reorder_threshold"] == 10
    assert data["enough_history"] is False

    remove_milk(client)
    data = trend(client, milk["id"])
    assert data["points"][-1]["quantity"] == 5
    assert data["points"][-1]["stock_out"] == 15
    assert data["total_out"] == 15


def test_trend_input_rules(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    for days in (6, 91):
        response = client.get("/api/dashboard/trend", headers=CAFE_OWNER, params={"item_id": milk["id"], "days": days})
        assert response.status_code == 422
    assert client.get("/api/dashboard/trend", headers=CAFE_OWNER, params={"item_id": 99999}).status_code == 404
    assert len(trend(client, milk["id"], days=7)["points"]) == 7


# ---------------------------------------------------------------- synthetic history

def test_history_builder_ends_at_current_quantity():
    for sku, quantity, threshold in [("MILK-1L", 20, 10), ("CHOC-500", 0, 4), ("LID-12OZ", 11, 15)]:
        opening, events = build_history(sku, quantity, threshold, today_my())
        running = opening
        for event in events:
            running += event["quantity"] if event["kind"] == "in" else -event["quantity"]
            assert running >= 0
        assert running == quantity
        assert all(event["day"] < today_my() for event in events)
    # Same input -> same history (fixed random seed per product)
    assert build_history("MILK-1L", 20, 10, today_my()) == build_history("MILK-1L", 20, 10, today_my())


def test_seed_history_is_consistent_and_safe_to_repeat(client, db_session):
    assert seed_history_if_missing(db_session, today=today_my()) == 16  # every demo product
    assert seed_history_if_missing(db_session, today=today_my()) == 0   # nothing happens twice

    for item in db_session.scalars(select(InventoryItem)):
        movements = db_session.scalars(
            select(StockMovement).where(StockMovement.item_id == item.id)
            .order_by(StockMovement.created_at, StockMovement.id)
        ).all()
        assert movements[0].movement_type == "initial" and movements[0].quantity_before == 0
        for before, after in zip(movements, movements[1:]):
            assert after.quantity_before == before.quantity_after  # an unbroken chain
            assert after.quantity_after >= 0
        assert movements[-1].quantity_after == item.quantity      # current stock unchanged

    # The demo still starts the same: 20 cartons of milk, reorder at 10
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    assert milk["quantity"] == 20 and milk["stock_status"] == "in_stock"

    data = trend(client, milk["id"])
    assert data["enough_history"] is True
    assert 7 <= data["average_daily_usage"] <= 13  # about 10 cartons a day, as in the brief
    assert all(point["quantity"] is not None for point in data["points"])
    assert overview(client)["default_trend_item_id"] == milk["id"]  # the busiest product


def test_seed_history_skips_products_already_used(client, db_session):
    remove_milk(client, quantity=1)
    assert seed_history_if_missing(db_session, today=today_my()) == 15
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    count = len(db_session.scalars(select(StockMovement).where(StockMovement.item_id == milk["id"])).all())
    assert count == 2  # opening quantity + the real movement, no synthetic history
    assert HISTORY_DAYS == 30
