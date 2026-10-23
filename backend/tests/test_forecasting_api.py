"""Feature 8 tests: demand forecasting (7-day moving average).

Run from the backend folder:   pytest -v

Most tests use a test product with a hand-made usage history, so the expected numbers
can be worked out on paper:
  20 days of history, 5 units used every day, 30 on hand, reorder level 5,
  supplier Roti Segar (usual delivery 2 days, minimum order 4)
  -> forecast 5/day, runs out in 6 days, order by today + (6 - 2 - 2) = today + 2,
     order 5 x (2 + 7 + 2) - 30 = 25 units, suggested reorder level 5 x (2 + 2) = 20.
"""
from datetime import datetime, time, timedelta

from sqlalchemy import select

from app.models import InventoryItem, StockMovement
from app.seed.history_data import seed_history_if_missing
from app.services.forecast_service import today_my
from tests.conftest import CAFE_EMPLOYEE, CAFE_OWNER, SHOP_OWNER, find_item

MY = timedelta(hours=8)
ROTI = "Roti Segar Bakery Supply (demo)"


def create_product(client, sku="SODA-TEST", quantity=30, threshold=5):
    response = client.post(
        "/api/inventory", headers=CAFE_OWNER,
        json={"name": f"Test product {sku}", "sku": sku, "category": "Test", "unit": "cans",
              "quantity": quantity, "reorder_threshold": threshold},
    )
    assert response.status_code == 201, response.text
    return response.json()


def give_history(db, item_id, days, used_on_day):
    """Pretend the product existed `days` days ago and used `used_on_day(i)` units on day i."""
    today = today_my()
    first = today - timedelta(days=days)
    start = datetime.combine(first, time(8, 0)) - MY
    item = db.get(InventoryItem, item_id)
    item.created_at = start
    for movement in db.scalars(select(StockMovement).where(StockMovement.item_id == item_id)):
        movement.created_at = start
    for i in range(days):
        used = used_on_day(i)
        if used:
            db.add(StockMovement(
                business_id=item.business_id, item_id=item_id, user_id=2, movement_type="out",
                quantity_change=-used, quantity_before=100, quantity_after=100 - used,
                reason="test usage", created_at=datetime.combine(first + timedelta(days=i), time(21, 0)) - MY,
            ))
    db.commit()


def add_roti_price(client, item_id):
    roti = next(s for s in client.get("/api/suppliers", headers=CAFE_OWNER).json() if s["name"] == ROTI)
    response = client.post(
        f"/api/suppliers/{roti['id']}/products", headers=CAFE_OWNER,
        json={"item_id": item_id, "unit_price": 3, "min_order_qty": 4},
    )
    assert response.status_code == 201, response.text


def forecast(client, item_id, headers=CAFE_OWNER, **params):
    response = client.get(f"/api/forecasts/{item_id}", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def all_forecasts(client, headers=CAFE_OWNER):
    response = client.get("/api/forecasts", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- the worked example

def test_steady_demand_gives_the_expected_plan(client, db_session):
    item = create_product(client)
    add_roti_price(client, item["id"])
    give_history(db_session, item["id"], 20, lambda i: 5)
    today = today_my()

    data = forecast(client, item["id"], CAFE_EMPLOYEE)
    assert data["history_days"] == 20
    assert data["daily_forecast"] == 5.0
    assert data["weekly_forecast"] == 35.0
    assert data["days_until_out"] == 6.0
    assert data["run_out_date"] == (today + timedelta(days=6)).isoformat()
    assert data["order_by_date"] == (today + timedelta(days=2)).isoformat()
    assert data["status"] == "order_soon"
    assert data["recommended_quantity"] == 25
    assert data["rule_quantity"] == 4          # Feature 3 rule, shown for comparison
    assert data["suggested_reorder_level"] == 20
    assert data["level_check"] == "too_low"
    assert data["supplier_name"] == ROTI and data["lead_time_days"] == 2
    # Predicted vs actual: steady use is predicted perfectly
    assert data["accuracy_pct"] == 100.0
    assert data["mean_absolute_error"] == 0.0
    assert data["backtest_days"] == 13  # days with 7 days of history before them
    assert any("reorder level (5)" in w for w in data["warnings"])


def test_chart_series(client, db_session):
    item = create_product(client)
    give_history(db_session, item["id"], 20, lambda i: 5)
    data = forecast(client, item["id"], horizon_days=10)
    assert len(data["history"]) == 28
    existed = [p for p in data["history"] if p["actual"] is not None]
    assert len(existed) == 20 and all(p["actual"] == 5 for p in existed)
    assert data["history"][0]["actual"] is None  # before the product existed
    predicted = [p for p in data["history"] if p["predicted"] is not None]
    assert len(predicted) == 13 and all(p["predicted"] == 5.0 for p in predicted)

    assert len(data["future"]) == 10
    assert data["future"][0]["date"] == today_my().isoformat()
    assert data["future"][0]["projected_stock"] == 30
    assert data["future"][2]["projected_stock"] == 20
    assert data["future"][9]["projected_stock"] == 0  # never below zero
    assert data["method"]["window_days"] == 7


def test_without_a_supplier_the_delivery_time_is_unknown(client, db_session):
    item = create_product(client)
    give_history(db_session, item["id"], 20, lambda i: 5)
    data = forecast(client, item["id"])
    assert data["supplier_name"] is None and data["lead_time_days"] is None
    assert data["order_by_date"] == (today_my() + timedelta(days=4)).isoformat()  # 6 - 0 - 2
    assert any("No supplier price" in w for w in data["warnings"])


# ---------------------------------------------------------------- not enough data

def test_new_product_has_no_forecast(client):
    item = create_product(client)
    data = forecast(client, item["id"])
    assert data["status"] == "insufficient_data"
    assert data["daily_forecast"] is None
    assert data["run_out_date"] is None and data["recommended_quantity"] is None
    assert any("Not enough history" in w for w in data["warnings"])
    assert all(p["forecast"] is None for p in data["future"])


def test_limited_history_gives_a_warning(client, db_session):
    item = create_product(client)
    give_history(db_session, item["id"], 10, lambda i: 4)
    data = forecast(client, item["id"])
    assert data["daily_forecast"] == 4.0
    assert data["status"] != "insufficient_data"
    assert any("Limited history" in w for w in data["warnings"])


def test_no_usage_means_no_run_out(client, db_session):
    item = create_product(client)
    give_history(db_session, item["id"], 15, lambda i: 0)
    data = forecast(client, item["id"])
    assert data["status"] == "no_demand"
    assert data["daily_forecast"] == 0.0
    assert data["run_out_date"] is None
    assert data["recommended_quantity"] == 0


def test_erratic_use_is_marked_low_accuracy(client, db_session):
    item = create_product(client)
    give_history(db_session, item["id"], 20, lambda i: 10 if i % 2 else 0)
    data = forecast(client, item["id"])
    assert data["accuracy_pct"] < 50
    assert any("Low accuracy" in w for w in data["warnings"])


# ---------------------------------------------------------------- the café with its synthetic history

def test_milk_forecast_from_the_demo_history(client, db_session):
    seed_history_if_missing(db_session, today=today_my())
    data = all_forecasts(client, CAFE_EMPLOYEE)
    milk = next(row for row in data["items"] if row["sku"] == "MILK-1L")
    assert 7 <= milk["daily_forecast"] <= 13      # about 10 cartons a day
    assert milk["history_days"] >= 30
    assert milk["accuracy_pct"] is not None
    # 20 cartons last about 2 days, Segar delivers in 1: the reorder level of 10 is too low
    assert milk["status"] == "order_now"
    assert milk["level_check"] == "too_low"
    assert milk["suggested_reorder_level"] > 10

    assert data["summary"]["order_now"] >= 1
    assert data["summary"]["average_accuracy_pct"] is not None
    assert data["items"][0]["status"] == "order_now"  # most urgent first
    assert len(data["items"]) == 10


def test_orders_are_taken_into_account(client, db_session):
    seed_history_if_missing(db_session, today=today_my())
    milk = find_item(client, CAFE_EMPLOYEE, "MILK-1L")
    client.post(f"/api/inventory/{milk['id']}/movements", headers=CAFE_EMPLOYEE,
                json={"movement_type": "out", "quantity": 15})
    data = forecast(client, milk["id"])
    assert data["in_drafts"] == 15 and data["on_order"] == 0
    assert data["status"] == "order_now"  # a draft is not ordered yet

    order_id = client.get("/api/purchase-orders", headers=CAFE_OWNER).json()[0]["id"]
    client.post(f"/api/purchase-orders/{order_id}/approve", headers=CAFE_OWNER)
    data = forecast(client, milk["id"])
    assert data["on_order"] == 15 and data["in_drafts"] == 0
    assert data["status"] == "on_order"


# ---------------------------------------------------------------- access and input

def test_forecast_access_rules(client, db_session):
    item = create_product(client)
    assert client.get("/api/forecasts").status_code == 401
    assert client.get(f"/api/forecasts/{item['id']}", headers=SHOP_OWNER).status_code == 404
    assert client.get("/api/forecasts/99999", headers=CAFE_OWNER).status_code == 404
    for horizon in (6, 61):
        assert client.get(f"/api/forecasts/{item['id']}", headers=CAFE_OWNER,
                          params={"horizon_days": horizon}).status_code == 422
    # Applying a suggested reorder level uses the existing owner-only route
    assert client.patch(f"/api/inventory/{item['id']}", headers=CAFE_EMPLOYEE,
                        json={"reorder_threshold": 20}).status_code == 403
    assert client.patch(f"/api/inventory/{item['id']}", headers=CAFE_OWNER,
                        json={"reorder_threshold": 20}).status_code == 200
    assert forecast(client, item["id"])["reorder_threshold"] == 20


def test_archived_products_are_left_out(client):
    croissant = find_item(client, CAFE_OWNER, "CROI-FRZ")
    client.post(f"/api/inventory/{croissant['id']}/archive", headers=CAFE_OWNER)
    skus = [row["sku"] for row in all_forecasts(client)["items"]]
    assert "CROI-FRZ" not in skus and len(skus) == 9
    assert all_forecasts(client, SHOP_OWNER)["items"][0]["sku"] not in skus  # per business
