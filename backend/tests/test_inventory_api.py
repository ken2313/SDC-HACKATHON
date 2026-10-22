"""Feature 1 tests: inventory management API.

Run from the backend folder:   pytest -v
"""
import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import ActivityLog, InventoryItem, StockMovement
from tests.conftest import CAFE_EMPLOYEE, CAFE_OWNER, SHOP_EMPLOYEE, SHOP_OWNER, find_item

NEW_PRODUCT = {
    "name": "Vanilla Syrup 750ml",
    "sku": "syr-van",
    "category": "Syrups",
    "unit": "bottles",
    "quantity": 8,
    "reorder_threshold": 3,
    "supplier_name": "Pasar Borong Jaya (demo)",
}


def move(client, headers, item_id, movement_type, quantity, **extra):
    return client.post(
        f"/api/inventory/{item_id}/movements",
        headers=headers,
        json={"movement_type": movement_type, "quantity": quantity, **extra},
    )


# ---------------------------------------------------------------- session / auth

def test_health_check(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_missing_user_header_is_rejected(client):
    assert client.get("/api/inventory").status_code == 401


def test_unknown_user_is_rejected(client):
    assert client.get("/api/inventory", headers={"X-User-Id": "9999"}).status_code == 401


def test_simulated_orbyte_context_returns_business_role_and_permissions(client):
    body = client.get("/api/orbyte-mock/context", headers=CAFE_EMPLOYEE).json()
    assert body["simulated"] is True
    assert body["business"]["name"].startswith("Kopi Kita")
    assert body["user"]["role"] == "employee"
    assert "inventory:manage" not in body["permissions"]
    assert "stock:record" in body["permissions"]


# ---------------------------------------------------------------- listing & business separation

def test_list_only_returns_own_business_products(client):
    cafe = client.get("/api/inventory", headers=CAFE_OWNER).json()
    shop = client.get("/api/inventory", headers=SHOP_OWNER).json()
    assert {item["sku"] for item in cafe}.isdisjoint({item["sku"] for item in shop})
    assert any(item["sku"] == "MILK-1L" for item in cafe)


def test_cannot_read_or_change_another_businesses_product(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    assert client.get(f"/api/inventory/{milk['id']}", headers=SHOP_OWNER).status_code == 404
    assert client.patch(f"/api/inventory/{milk['id']}", headers=SHOP_OWNER, json={"name": "Hacked"}).status_code == 404
    assert client.post(f"/api/inventory/{milk['id']}/archive", headers=SHOP_OWNER).status_code == 404
    assert move(client, SHOP_EMPLOYEE, milk["id"], "out", 1).status_code == 404
    assert client.get(f"/api/inventory/{milk['id']}/movements", headers=SHOP_OWNER).status_code == 404
    # ...and the cafe's milk is untouched
    assert find_item(client, CAFE_OWNER, "MILK-1L")["quantity"] == 20


def test_two_businesses_can_use_the_same_sku(client):
    payload = {**NEW_PRODUCT, "sku": "MILK-1L"}  # cafe already has MILK-1L
    assert client.post("/api/inventory", headers=SHOP_OWNER, json=payload).status_code == 201
    assert client.post("/api/inventory", headers=CAFE_OWNER, json=payload).status_code == 409


# ---------------------------------------------------------------- create

def test_owner_can_create_product_and_sku_is_normalised(client, db_session):
    response = client.post("/api/inventory", headers=CAFE_OWNER, json=NEW_PRODUCT)
    assert response.status_code == 201
    body = response.json()
    assert body["sku"] == "SYR-VAN"
    assert body["quantity"] == 8
    assert body["stock_status"] == "in_stock"

    # Opening stock is recorded in the ledger and the audit log
    movements = db_session.scalars(select(StockMovement).where(StockMovement.item_id == body["id"])).all()
    assert len(movements) == 1 and movements[0].movement_type == "initial"
    log = db_session.scalars(select(ActivityLog).where(ActivityLog.action == "item.created")).all()
    assert len(log) == 1 and log[0].user_id == 1


def test_create_with_zero_quantity_is_out_of_stock(client):
    body = client.post("/api/inventory", headers=CAFE_OWNER, json={**NEW_PRODUCT, "quantity": 0}).json()
    assert body["stock_status"] == "out_of_stock"


def test_duplicate_sku_in_same_business_is_rejected(client):
    assert client.post("/api/inventory", headers=CAFE_OWNER, json=NEW_PRODUCT).status_code == 201
    duplicate = client.post("/api/inventory", headers=CAFE_OWNER, json={**NEW_PRODUCT, "sku": "SYR-VAN"})
    assert duplicate.status_code == 409
    assert "already used" in duplicate.json()["detail"]


@pytest.mark.parametrize(
    "bad_fields",
    [
        {"name": ""},
        {"name": "   "},
        {"category": ""},
        {"sku": "has space"},
        {"sku": "bad/char"},
        {"sku": ""},
        {"quantity": -1},
        {"reorder_threshold": -5},
        {"quantity": "many"},
        {"quantity": 2_000_000},
        {"unknown_field": 1},
    ],
)
def test_create_rejects_invalid_input(client, bad_fields):
    response = client.post("/api/inventory", headers=CAFE_OWNER, json={**NEW_PRODUCT, **bad_fields})
    assert response.status_code == 422


def test_employee_cannot_create_edit_or_archive(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    assert client.post("/api/inventory", headers=CAFE_EMPLOYEE, json=NEW_PRODUCT).status_code == 403
    assert client.patch(f"/api/inventory/{milk['id']}", headers=CAFE_EMPLOYEE, json={"name": "X"}).status_code == 403
    assert client.post(f"/api/inventory/{milk['id']}/archive", headers=CAFE_EMPLOYEE).status_code == 403
    assert client.post(f"/api/inventory/{milk['id']}/restore", headers=CAFE_EMPLOYEE).status_code == 403


def test_employee_can_view_inventory(client):
    assert client.get("/api/inventory", headers=CAFE_EMPLOYEE).status_code == 200


# ---------------------------------------------------------------- edit

def test_edit_changes_fields_and_writes_old_and_new_values_to_log(client, db_session):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    response = client.patch(
        f"/api/inventory/{milk['id']}", headers=CAFE_OWNER, json={"reorder_threshold": 12, "name": "Fresh Milk 1L (Full Cream)"}
    )
    assert response.status_code == 200
    assert response.json()["reorder_threshold"] == 12

    entry = db_session.scalars(select(ActivityLog).where(ActivityLog.action == "item.updated")).one()
    assert json.loads(entry.old_value)["reorder_threshold"] == 10
    assert json.loads(entry.new_value)["reorder_threshold"] == 12


def test_edit_cannot_change_quantity_directly(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    response = client.patch(f"/api/inventory/{milk['id']}", headers=CAFE_OWNER, json={"quantity": 999})
    assert response.status_code == 422
    assert find_item(client, CAFE_OWNER, "MILK-1L")["quantity"] == 20


def test_edit_to_existing_sku_is_rejected(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    assert client.patch(f"/api/inventory/{milk['id']}", headers=CAFE_OWNER, json={"sku": "oatm-1l"}).status_code == 409


def test_edit_can_keep_own_sku(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    assert client.patch(f"/api/inventory/{milk['id']}", headers=CAFE_OWNER, json={"sku": "milk-1l"}).status_code == 200


def test_edit_with_no_real_change_writes_no_log(client, db_session):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    client.patch(f"/api/inventory/{milk['id']}", headers=CAFE_OWNER, json={"reorder_threshold": 10})
    assert db_session.scalars(select(ActivityLog).where(ActivityLog.action == "item.updated")).first() is None


@pytest.mark.parametrize("bad_fields", [{"name": None}, {"reorder_threshold": -1}, {"sku": "no spaces!"}])
def test_edit_rejects_invalid_input(client, bad_fields):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    assert client.patch(f"/api/inventory/{milk['id']}", headers=CAFE_OWNER, json=bad_fields).status_code == 422


# ---------------------------------------------------------------- stock status rules

@pytest.mark.parametrize(
    "quantity, threshold, expected",
    [
        (20, 10, "in_stock"),
        (11, 10, "in_stock"),
        (10, 10, "low_stock"),   # reaching the threshold counts as low
        (5, 10, "low_stock"),
        (1, 10, "low_stock"),
        (0, 10, "out_of_stock"),
        (0, 0, "out_of_stock"),
        (1, 0, "in_stock"),
    ],
)
def test_stock_status_rules(client, quantity, threshold, expected):
    payload = {**NEW_PRODUCT, "quantity": quantity, "reorder_threshold": threshold}
    assert client.post("/api/inventory", headers=CAFE_OWNER, json=payload).json()["stock_status"] == expected


def test_hackathon_demo_scenario_milk_drops_to_low_stock(client):
    """20 cartons, threshold 10. Employee removes 15 -> 5 left -> Low Stock."""
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    assert (milk["quantity"], milk["reorder_threshold"], milk["stock_status"]) == (20, 10, "in_stock")

    response = move(client, CAFE_EMPLOYEE, milk["id"], "out", 15, reason="Weekend rush")
    assert response.status_code == 201
    body = response.json()
    assert body["item"]["quantity"] == 5
    assert body["item"]["stock_status"] == "low_stock"
    assert body["movement"]["quantity_before"] == 20
    assert body["movement"]["quantity_after"] == 5
    assert body["movement"]["quantity_change"] == -15
    assert body["movement"]["user_name"] == "Hafiz Ismail"


# ---------------------------------------------------------------- stock movements

def test_stock_in_and_out_update_quantity_and_status(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    assert move(client, CAFE_EMPLOYEE, milk["id"], "out", 20).json()["item"]["stock_status"] == "out_of_stock"
    assert move(client, CAFE_EMPLOYEE, milk["id"], "in", 10).json()["item"]["stock_status"] == "low_stock"
    assert move(client, CAFE_EMPLOYEE, milk["id"], "in", 1).json()["item"]["stock_status"] == "in_stock"
    assert find_item(client, CAFE_OWNER, "MILK-1L")["quantity"] == 11


def test_cannot_remove_more_than_available(client, db_session):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    response = move(client, CAFE_EMPLOYEE, milk["id"], "out", 21)
    assert response.status_code == 409
    assert "Not enough stock" in response.json()["detail"]
    assert find_item(client, CAFE_OWNER, "MILK-1L")["quantity"] == 20
    # No ledger row and no audit row were created for the failed attempt
    assert db_session.scalars(select(StockMovement).where(StockMovement.item_id == milk["id"], StockMovement.movement_type == "out")).first() is None
    assert db_session.scalars(select(ActivityLog).where(ActivityLog.action == "stock.out")).first() is None


def test_can_remove_exactly_all_stock(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    assert move(client, CAFE_EMPLOYEE, milk["id"], "out", 20).json()["item"]["quantity"] == 0


def test_cannot_remove_from_out_of_stock_item(client):
    chocolate = find_item(client, CAFE_OWNER, "CHOC-500")
    assert chocolate["quantity"] == 0
    assert move(client, CAFE_EMPLOYEE, chocolate["id"], "out", 1).status_code == 409


@pytest.mark.parametrize(
    "bad_body",
    [
        {"movement_type": "out", "quantity": 0},
        {"movement_type": "out", "quantity": -3},
        {"movement_type": "in", "quantity": 1.5},
        {"movement_type": "in", "quantity": "ten"},
        {"movement_type": "steal", "quantity": 1},
        {"movement_type": "initial", "quantity": 1},
        {"movement_type": "in"},
        {"quantity": 5},
        {"movement_type": "in", "quantity": 5_000_000},
    ],
)
def test_movement_rejects_invalid_input(client, bad_body):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    response = client.post(f"/api/inventory/{milk['id']}/movements", headers=CAFE_EMPLOYEE, json=bad_body)
    assert response.status_code == 422
    assert find_item(client, CAFE_OWNER, "MILK-1L")["quantity"] == 20


def test_movement_is_recorded_in_ledger_and_audit_log(client, db_session):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 15, reason="Weekend rush")

    ledger = db_session.scalars(select(StockMovement).where(StockMovement.item_id == milk["id"], StockMovement.movement_type == "out")).one()
    assert (ledger.user_id, ledger.quantity_change, ledger.reason) == (2, -15, "Weekend rush")

    entry = db_session.scalars(select(ActivityLog).where(ActivityLog.action == "stock.out")).one()
    assert entry.user_id == 2 and entry.entity_id == milk["id"]
    assert json.loads(entry.old_value) == {"quantity": 20}
    assert json.loads(entry.new_value)["quantity"] == 5


def test_movement_history_endpoint(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 3)
    move(client, CAFE_OWNER, milk["id"], "in", 5)
    history = client.get(f"/api/inventory/{milk['id']}/movements", headers=CAFE_EMPLOYEE).json()
    assert [row["quantity_change"] for row in history] == [5, -3, 20]  # newest first, opening stock last
    assert history[0]["user_name"] == "Aisyah Rahman"


# ---------------------------------------------------------------- duplicate-update protection

def test_retrying_the_same_request_id_changes_stock_only_once(client, db_session):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    request_id = str(uuid.uuid4())

    first = move(client, CAFE_EMPLOYEE, milk["id"], "out", 15, request_id=request_id)
    second = move(client, CAFE_EMPLOYEE, milk["id"], "out", 15, request_id=request_id)

    assert first.status_code == 201 and first.json()["already_applied"] is False
    assert second.status_code == 201 and second.json()["already_applied"] is True
    assert second.json()["movement"]["id"] == first.json()["movement"]["id"]
    assert find_item(client, CAFE_OWNER, "MILK-1L")["quantity"] == 5
    assert len(db_session.scalars(select(StockMovement).where(StockMovement.request_id == request_id)).all()) == 1
    assert len(db_session.scalars(select(ActivityLog).where(ActivityLog.action == "stock.out")).all()) == 1


def test_request_id_cannot_be_reused_for_a_different_product(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    oat = find_item(client, CAFE_OWNER, "OATM-1L")
    request_id = str(uuid.uuid4())
    assert move(client, CAFE_EMPLOYEE, milk["id"], "out", 1, request_id=request_id).status_code == 201
    assert move(client, CAFE_EMPLOYEE, oat["id"], "out", 1, request_id=request_id).status_code == 409
    assert find_item(client, CAFE_OWNER, "OATM-1L")["quantity"] == 12


def test_different_request_ids_are_applied_separately(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 2, request_id=str(uuid.uuid4()))
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 2, request_id=str(uuid.uuid4()))
    assert find_item(client, CAFE_OWNER, "MILK-1L")["quantity"] == 16


def test_database_itself_refuses_negative_stock(db_session):
    """Safety net below the API: the CHECK constraint blocks bad data even if code had a bug."""
    item = db_session.scalars(select(InventoryItem).where(InventoryItem.sku == "MILK-1L")).one()
    item.quantity = -1
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ---------------------------------------------------------------- archive / restore

def test_archive_hides_product_but_keeps_history(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    assert client.post(f"/api/inventory/{milk['id']}/archive", headers=CAFE_OWNER).json()["is_archived"] is True

    visible = client.get("/api/inventory", headers=CAFE_OWNER).json()
    assert all(item["sku"] != "MILK-1L" for item in visible)

    with_archived = client.get("/api/inventory", headers=CAFE_OWNER, params={"include_archived": True}).json()
    assert any(item["sku"] == "MILK-1L" and item["is_archived"] for item in with_archived)

    history = client.get(f"/api/inventory/{milk['id']}/movements", headers=CAFE_OWNER).json()
    assert len(history) == 1  # opening stock still there


def test_archived_product_cannot_be_edited_or_moved_until_restored(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    client.post(f"/api/inventory/{milk['id']}/archive", headers=CAFE_OWNER)

    assert client.patch(f"/api/inventory/{milk['id']}", headers=CAFE_OWNER, json={"name": "X"}).status_code == 409
    assert move(client, CAFE_EMPLOYEE, milk["id"], "out", 1).status_code == 409

    assert client.post(f"/api/inventory/{milk['id']}/restore", headers=CAFE_OWNER).json()["is_archived"] is False
    assert move(client, CAFE_EMPLOYEE, milk["id"], "out", 1).status_code == 201


def test_archive_and_restore_are_logged_and_repeatable(client, db_session):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    client.post(f"/api/inventory/{milk['id']}/archive", headers=CAFE_OWNER)
    client.post(f"/api/inventory/{milk['id']}/archive", headers=CAFE_OWNER)  # second call: no-op
    client.post(f"/api/inventory/{milk['id']}/restore", headers=CAFE_OWNER)
    item_logs = db_session.scalars(
        select(ActivityLog).where(ActivityLog.action.like("item.%")).order_by(ActivityLog.id)
    )
    assert [row.action for row in item_logs] == ["item.archived", "item.restored"]


def test_archived_sku_stays_reserved(client):
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    client.post(f"/api/inventory/{milk['id']}/archive", headers=CAFE_OWNER)
    assert client.post("/api/inventory", headers=CAFE_OWNER, json={**NEW_PRODUCT, "sku": "MILK-1L"}).status_code == 409


# ---------------------------------------------------------------- search, filter, sort, summary

def test_search_matches_name_sku_category_and_supplier_case_insensitively(client):
    def skus(**params):
        return {item["sku"] for item in client.get("/api/inventory", headers=CAFE_OWNER, params=params).json()}

    assert skus(search="milk") == {"MILK-1L", "OATM-1L"}
    assert skus(search="CROI-FRZ") == {"CROI-FRZ"}
    assert skus(search="bakery") == {"CROI-FRZ"}
    assert skus(search="borneo") == {"COFB-1KG", "COFB-ROB"}
    assert skus(search="no-such-thing") == set()


def test_search_treats_percent_literally(client):
    assert client.get("/api/inventory", headers=CAFE_OWNER, params={"search": "%"}).json() == []


def test_category_and_status_filters(client):
    dairy = client.get("/api/inventory", headers=CAFE_OWNER, params={"category": "Dairy"}).json()
    assert {item["sku"] for item in dairy} == {"MILK-1L", "OATM-1L"}

    def skus_with(status):
        return {item["sku"] for item in client.get("/api/inventory", headers=CAFE_OWNER, params={"status": status}).json()}

    assert skus_with("out_of_stock") == {"CHOC-500"}
    assert skus_with("low_stock") == {"COFB-ROB", "LID-12OZ"}
    assert "MILK-1L" in skus_with("in_stock")
    assert "TEHT-500" in skus_with("in_stock")  # 9 > threshold 8


def test_invalid_filter_values_are_rejected(client):
    assert client.get("/api/inventory", headers=CAFE_OWNER, params={"status": "bogus"}).status_code == 422
    assert client.get("/api/inventory", headers=CAFE_OWNER, params={"sort_by": "password"}).status_code == 422


def test_sorting(client):
    by_qty = client.get("/api/inventory", headers=CAFE_OWNER, params={"sort_by": "quantity", "sort_dir": "desc"}).json()
    quantities = [item["quantity"] for item in by_qty]
    assert quantities == sorted(quantities, reverse=True)


def test_categories_endpoint_is_scoped_to_business(client):
    cafe = client.get("/api/inventory/categories", headers=CAFE_OWNER).json()
    shop = client.get("/api/inventory/categories", headers=SHOP_OWNER).json()
    assert "Dairy" in cafe and "Dairy" not in shop
    assert "Rice & Grains" in shop


def test_summary_counts_and_updates_after_stock_change(client):
    summary = client.get("/api/inventory/summary", headers=CAFE_OWNER).json()
    assert summary == {"total_products": 10, "in_stock": 7, "low_stock": 2, "out_of_stock": 1, "archived": 0}

    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    move(client, CAFE_EMPLOYEE, milk["id"], "out", 15)  # milk: 20 -> 5, becomes Low Stock
    after = client.get("/api/inventory/summary", headers=CAFE_OWNER).json()
    assert (after["in_stock"], after["low_stock"]) == (6, 3)

    client.post(f"/api/inventory/{milk['id']}/archive", headers=CAFE_OWNER)
    final = client.get("/api/inventory/summary", headers=CAFE_OWNER).json()
    assert (final["total_products"], final["archived"]) == (9, 1)
