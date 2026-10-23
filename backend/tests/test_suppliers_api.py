"""Feature 6 tests: supplier management.

Run from the backend folder:   pytest -v

Seeded café suppliers (Kopi Kita Café, user 1 = owner, user 2 = employee):
  Segar Dairy        milk RM 7.80 (min 6), oat milk RM 11.50   typical delivery 1 day
  Kopi Borneo        coffee beans                              4 days
  Pasar Borong Jaya  sugar, teh tarik, chocolate, milk RM 8.50 (min 12)   2 days
  PakEco Packaging   cups, lids                                5 days
  Roti Segar Bakery  croissants                                2 days
Every seeded café product has at least one supplier price.
"""
from datetime import timedelta

from sqlalchemy import create_engine, select, text, update

from app.models import ActivityLog, OrderStatusHistory
from app.schema_upgrade import upgrade_schema
from tests.conftest import CAFE_EMPLOYEE, CAFE_OWNER, SHOP_OWNER, find_item

SEGAR = "Segar Dairy Sdn Bhd (demo)"
PASAR = "Pasar Borong Jaya (demo)"
ROTI = "Roti Segar Bakery Supply (demo)"


def suppliers(client, headers=CAFE_OWNER, **params):
    response = client.get("/api/suppliers", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def supplier_id(client, name, headers=CAFE_OWNER):
    matches = [s for s in suppliers(client, headers, include_inactive=True) if s["name"] == name]
    assert matches, f"supplier {name} not found"
    return matches[0]["id"]


def detail(client, sid, headers=CAFE_OWNER):
    response = client.get(f"/api/suppliers/{sid}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def price_line(supplier, sku):
    matches = [p for p in supplier["products"] if p["sku"] == sku]
    assert matches, f"{sku} not on the price list"
    return matches[0]


def remove_milk(client, quantity=15):
    milk = find_item(client, CAFE_EMPLOYEE, "MILK-1L")
    response = client.post(
        f"/api/inventory/{milk['id']}/movements",
        headers=CAFE_EMPLOYEE,
        json={"movement_type": "out", "quantity": quantity},
    )
    assert response.status_code == 201, response.text
    return response.json()


def supplier_logs(client):
    response = client.get("/api/activity-logs", headers=CAFE_OWNER, params={"category": "supplier"})
    assert response.status_code == 200, response.text
    return response.json()["items"]


NEW_SUPPLIER = {
    "name": "Susu Lembu Utara (demo)",
    "contact_name": "Ahmad Faizal",
    "phone": "+60 4-555 0199",
    "email": "Orders@SusuUtara.example",
    "address": "Lot 4, Jalan Ladang, Alor Setar, Kedah",
    "notes": "Delivers Monday to Friday only.",
    "lead_time_days": 2,
}


# ---------------------------------------------------------------- viewing

def test_employee_can_view_suppliers_and_contacts(client):
    rows = suppliers(client, CAFE_EMPLOYEE)
    names = [row["name"] for row in rows]
    assert len(rows) == 5
    assert SEGAR in names and PASAR in names
    segar = next(row for row in rows if row["name"] == SEGAR)
    assert segar["contact_name"] == "Lim Wei Jie"
    assert segar["phone"] and segar["email"] and segar["address"]
    assert segar["lead_time_days"] == 1
    assert segar["product_count"] == 2
    assert segar["is_active"] is True
    assert segar["open_orders"] == 0


def test_search_suppliers(client):
    found = suppliers(client, search="lim wei")
    assert [row["name"] for row in found] == [SEGAR]
    assert suppliers(client, search="no such supplier") == []


def test_suppliers_are_separated_per_business(client):
    shop_names = {row["name"] for row in suppliers(client, SHOP_OWNER)}
    assert shop_names == {"Pak Mat Wholesale (demo)", "Ladang Telur Sejahtera (demo)"}
    cafe_supplier = supplier_id(client, SEGAR)
    assert client.get(f"/api/suppliers/{cafe_supplier}", headers=SHOP_OWNER).status_code == 404
    assert client.patch(f"/api/suppliers/{cafe_supplier}", headers=SHOP_OWNER, json={"notes": "x"}).status_code == 404


def test_summary_counts(client):
    summary = client.get("/api/suppliers/summary", headers=CAFE_EMPLOYEE).json()
    assert summary["active"] == 5
    assert summary["inactive"] == 0
    assert summary["products_with_supplier"] == 10
    assert summary["products_without_supplier"] == 0
    assert summary["low_without_supplier"] == 0
    assert summary["average_lead_time_days"] == 2.8  # (1 + 4 + 2 + 5 + 2) / 5


def test_detail_shows_price_list_and_which_supplier_is_chosen(client):
    segar = detail(client, supplier_id(client, SEGAR), CAFE_EMPLOYEE)
    milk = price_line(segar, "MILK-1L")
    assert milk["unit_price"] == 7.8
    assert milk["min_order_qty"] == 6
    assert milk["other_suppliers"] == 1          # Pasar Borong also sells milk
    assert milk["chosen_for_auto_orders"] is True  # cheapest
    assert price_line(segar, "OATM-1L")["other_suppliers"] == 0

    pasar = detail(client, supplier_id(client, PASAR))
    assert price_line(pasar, "MILK-1L")["chosen_for_auto_orders"] is False
    assert segar["orders"] == []
    assert segar["stats"]["total_orders"] == 0
    assert segar["stats"]["average_delivery_days"] is None


# ---------------------------------------------------------------- permissions

def test_employee_cannot_manage_suppliers_and_attempts_are_logged(client, db_session):
    sid = supplier_id(client, SEGAR)
    milk = price_line(detail(client, sid), "MILK-1L")
    croissant = find_item(client, CAFE_OWNER, "CROI-FRZ")
    attempts = [
        client.post("/api/suppliers", headers=CAFE_EMPLOYEE, json=NEW_SUPPLIER),
        client.patch(f"/api/suppliers/{sid}", headers=CAFE_EMPLOYEE, json={"lead_time_days": 9}),
        client.post(f"/api/suppliers/{sid}/deactivate", headers=CAFE_EMPLOYEE),
        client.post(f"/api/suppliers/{sid}/products", headers=CAFE_EMPLOYEE,
                    json={"item_id": croissant["id"], "unit_price": 40}),
        client.patch(f"/api/suppliers/{sid}/products/{milk['id']}", headers=CAFE_EMPLOYEE, json={"unit_price": 1}),
        client.delete(f"/api/suppliers/{sid}/products/{milk['id']}", headers=CAFE_EMPLOYEE),
    ]
    assert [response.status_code for response in attempts] == [403] * 6

    # Nothing changed
    segar = detail(client, sid)
    assert segar["lead_time_days"] == 1 and segar["is_active"] is True
    assert price_line(segar, "MILK-1L")["unit_price"] == 7.8
    assert len(suppliers(client)) == 5

    denied = db_session.scalars(select(ActivityLog).where(ActivityLog.action == "access.denied")).all()
    assert len(denied) == 6
    assert all('"suppliers:manage"' in row.new_value for row in denied)


def test_roles_table_lists_supplier_permissions(client):
    matrix = client.get("/api/access/matrix", headers=CAFE_EMPLOYEE).json()
    rules = {row["key"]: row["allowed"] for row in matrix["permissions"]}
    assert rules["suppliers:view"] == {"owner": True, "employee": True}
    assert rules["suppliers:manage"] == {"owner": True, "employee": False}


# ---------------------------------------------------------------- adding and editing suppliers

def test_owner_adds_a_supplier(client):
    response = client.post("/api/suppliers", headers=CAFE_OWNER, json=NEW_SUPPLIER)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["name"] == NEW_SUPPLIER["name"]
    assert created["email"] == "orders@susuutara.example"  # stored in lower case
    assert created["address"] == NEW_SUPPLIER["address"]
    assert created["lead_time_days"] == 2
    assert created["products"] == [] and created["orders"] == []
    assert len(suppliers(client)) == 6

    log = supplier_logs(client)[0]
    assert log["action"] == "supplier.created"
    assert log["entity_label"] == NEW_SUPPLIER["name"]
    assert log["user_name"] == "Aisyah Rahman"


def test_only_name_is_required(client):
    response = client.post("/api/suppliers", headers=CAFE_OWNER, json={"name": "Kedai Ais (demo)"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["lead_time_days"] == 3
    assert body["phone"] is None and body["email"] is None


def test_duplicate_supplier_name_is_refused(client):
    response = client.post("/api/suppliers", headers=CAFE_OWNER, json={"name": SEGAR.upper()})
    assert response.status_code == 409
    # The same name in ANOTHER business is fine
    assert client.post("/api/suppliers", headers=SHOP_OWNER, json={"name": SEGAR}).status_code == 201


def test_supplier_input_is_validated(client):
    bad_bodies = [
        {"name": ""},
        {"name": "   "},
        {"name": "X", "email": "not-an-email"},
        {"name": "X", "phone": "call me"},
        {"name": "X", "lead_time_days": -1},
        {"name": "X", "lead_time_days": 366},
        {"name": "X", "unknown_field": 1},
        {"name": "X" * 121},
    ]
    for body in bad_bodies:
        assert client.post("/api/suppliers", headers=CAFE_OWNER, json=body).status_code == 422, body
    assert len(suppliers(client)) == 5


def test_edit_supplier_and_rename_updates_product_labels(client):
    sid = supplier_id(client, SEGAR)
    new_name = "Segar Dairy Berhad (demo)"
    response = client.patch(
        f"/api/suppliers/{sid}", headers=CAFE_OWNER, json={"name": new_name, "lead_time_days": 2}
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == new_name
    assert response.json()["lead_time_days"] == 2
    # The products that showed the old name now show the new one
    assert find_item(client, CAFE_OWNER, "MILK-1L")["supplier_name"] == new_name
    assert find_item(client, CAFE_OWNER, "OATM-1L")["supplier_name"] == new_name

    log = supplier_logs(client)[0]
    assert log["action"] == "supplier.updated"
    changes = {row["field"]: (row["old"], row["new"]) for row in log["changes"]}
    assert changes["name"] == (SEGAR, new_name)
    assert changes["lead_time_days"] == (1, 2)
    assert changes["products_relabelled"] == (None, 2)


def test_edit_with_no_change_writes_no_log(client):
    sid = supplier_id(client, SEGAR)
    before = len(supplier_logs(client))
    assert client.patch(f"/api/suppliers/{sid}", headers=CAFE_OWNER, json={"lead_time_days": 1}).status_code == 200
    assert len(supplier_logs(client)) == before


def test_clearing_fields(client):
    sid = supplier_id(client, SEGAR)
    response = client.patch(f"/api/suppliers/{sid}", headers=CAFE_OWNER, json={"email": None, "notes": ""})
    assert response.status_code == 200, response.text
    assert response.json()["email"] is None
    assert response.json()["notes"] is None
    # Name and delivery time cannot be cleared
    assert client.patch(f"/api/suppliers/{sid}", headers=CAFE_OWNER, json={"name": None}).status_code == 422
    assert client.patch(f"/api/suppliers/{sid}", headers=CAFE_OWNER, json={"lead_time_days": None}).status_code == 422


def test_rename_to_an_existing_name_is_refused(client):
    sid = supplier_id(client, SEGAR)
    response = client.patch(f"/api/suppliers/{sid}", headers=CAFE_OWNER, json={"name": PASAR.lower()})
    assert response.status_code == 409
    assert detail(client, sid)["name"] == SEGAR


# ---------------------------------------------------------------- price list

def test_price_change_decides_the_supplier_of_new_drafts(client):
    pasar = detail(client, supplier_id(client, PASAR))
    milk_at_pasar = price_line(pasar, "MILK-1L")
    response = client.patch(
        f"/api/suppliers/{pasar['id']}/products/{milk_at_pasar['id']}", headers=CAFE_OWNER, json={"unit_price": 7.00}
    )
    assert response.status_code == 200, response.text
    assert price_line(response.json(), "MILK-1L")["chosen_for_auto_orders"] is True

    remove_milk(client)  # 20 -> 5: a draft is prepared with the now-cheapest supplier
    order = client.get("/api/purchase-orders", headers=CAFE_OWNER).json()[0]
    assert order["supplier"]["name"] == PASAR
    assert order["lines"][0]["unit_price"] == 7.0
    assert order["lines"][0]["quantity_ordered"] == 15

    log = supplier_logs(client)[0]
    assert log["action"] == "supplier.price_changed"
    assert {row["field"]: (row["old"], row["new"]) for row in log["changes"]}["unit_price"] == (8.5, 7.0)


def test_existing_orders_keep_their_price(client):
    remove_milk(client)  # draft from Segar at RM 7.80
    segar = detail(client, supplier_id(client, SEGAR))
    milk = price_line(segar, "MILK-1L")
    client.patch(f"/api/suppliers/{segar['id']}/products/{milk['id']}", headers=CAFE_OWNER, json={"unit_price": 9.9})
    order = client.get("/api/purchase-orders", headers=CAFE_OWNER).json()[0]
    assert order["lines"][0]["unit_price"] == 7.8
    assert order["total"] == 117.0


def test_adding_a_price_for_a_low_product_prepares_a_draft(client):
    created = client.post(
        "/api/inventory",
        headers=CAFE_OWNER,
        json={"name": "Frozen Yoghurt 1L", "sku": "FROYO-1L", "category": "Dairy", "unit": "tubs",
              "quantity": 2, "reorder_threshold": 5},
    )
    assert created.status_code == 201, created.text
    item = created.json()

    # Low, but nobody sells it: no draft could be made
    assert client.get("/api/purchase-orders", headers=CAFE_OWNER).json() == []
    missing = client.get("/api/suppliers/products-without-supplier", headers=CAFE_EMPLOYEE).json()
    assert [row["sku"] for row in missing] == ["FROYO-1L"]
    assert client.get("/api/suppliers/summary", headers=CAFE_OWNER).json()["low_without_supplier"] == 1

    roti = supplier_id(client, ROTI)
    response = client.post(
        f"/api/suppliers/{roti}/products", headers=CAFE_OWNER,
        json={"item_id": item["id"], "unit_price": 12.5, "min_order_qty": 4},
    )
    assert response.status_code == 201, response.text
    result = response.json()
    line = price_line(result["supplier"], "FROYO-1L")
    assert line["unit_price"] == 12.5 and line["min_order_qty"] == 4
    assert line["chosen_for_auto_orders"] is True
    assert result["draft_purchase_order"] is not None

    order = client.get("/api/purchase-orders", headers=CAFE_OWNER).json()[0]
    assert order["po_number"] == result["draft_purchase_order"]["po_number"]
    assert order["supplier"]["name"] == ROTI
    assert order["status"] == "draft"  # never approved automatically
    assert order["lines"][0]["quantity_ordered"] == 8  # refill to 2 x 5 = 10, minus 2 on hand
    assert client.get("/api/suppliers/products-without-supplier", headers=CAFE_OWNER).json() == []
    # The product now shows the supplier in Inventory
    assert find_item(client, CAFE_OWNER, "FROYO-1L")["supplier_name"] == ROTI


def test_adding_a_price_for_a_stocked_product_makes_no_draft(client):
    croissant = find_item(client, CAFE_OWNER, "CROI-FRZ")
    segar = supplier_id(client, SEGAR)
    response = client.post(
        f"/api/suppliers/{segar}/products", headers=CAFE_OWNER, json={"item_id": croissant["id"], "unit_price": 45}
    )
    assert response.status_code == 201, response.text
    assert response.json()["draft_purchase_order"] is None
    assert price_line(response.json()["supplier"], "CROI-FRZ")["min_order_qty"] == 1
    # The product already had a supplier label: it is not overwritten
    assert find_item(client, CAFE_OWNER, "CROI-FRZ")["supplier_name"] == ROTI


def test_price_list_input_rules(client):
    segar = supplier_id(client, SEGAR)
    milk = find_item(client, CAFE_OWNER, "MILK-1L")
    croissant = find_item(client, CAFE_OWNER, "CROI-FRZ")
    rice_other_business = find_item(client, SHOP_OWNER, "RICE-10KG")

    def add(body):
        return client.post(f"/api/suppliers/{segar}/products", headers=CAFE_OWNER, json=body)

    assert add({"item_id": milk["id"], "unit_price": 7}).status_code == 409             # already listed
    assert add({"item_id": rice_other_business["id"], "unit_price": 7}).status_code == 404
    assert add({"item_id": 99999, "unit_price": 7}).status_code == 404
    assert add({"item_id": croissant["id"], "unit_price": 7.805}).status_code == 422     # half a sen
    assert add({"item_id": croissant["id"], "unit_price": -1}).status_code == 422
    assert add({"item_id": croissant["id"], "unit_price": 100001}).status_code == 422
    assert add({"item_id": croissant["id"], "unit_price": 7, "min_order_qty": 0}).status_code == 422

    client.post(f"/api/inventory/{croissant['id']}/archive", headers=CAFE_OWNER)
    assert add({"item_id": croissant["id"], "unit_price": 7}).status_code == 409         # archived

    line = price_line(detail(client, segar), "MILK-1L")
    path = f"/api/suppliers/{segar}/products/{line['id']}"
    assert client.patch(path, headers=CAFE_OWNER, json={}).status_code == 422
    assert client.patch(path, headers=CAFE_OWNER, json={"unit_price": None}).status_code == 422
    assert client.patch(f"/api/suppliers/{segar}/products/99999", headers=CAFE_OWNER, json={"unit_price": 1}).status_code == 404
    # A price list entry of ANOTHER supplier cannot be edited through this supplier
    pasar = detail(client, supplier_id(client, PASAR))
    other_line = price_line(pasar, "SUGR-1KG")
    assert client.patch(
        f"/api/suppliers/{segar}/products/{other_line['id']}", headers=CAFE_OWNER, json={"unit_price": 1}
    ).status_code == 404


def test_minimum_order_change(client):
    segar = detail(client, supplier_id(client, SEGAR))
    milk = price_line(segar, "MILK-1L")
    response = client.patch(
        f"/api/suppliers/{segar['id']}/products/{milk['id']}", headers=CAFE_OWNER, json={"min_order_qty": 24}
    )
    assert response.status_code == 200, response.text
    assert price_line(response.json(), "MILK-1L")["min_order_qty"] == 24
    remove_milk(client)
    order = client.get("/api/purchase-orders", headers=CAFE_OWNER).json()[0]
    assert order["lines"][0]["quantity_ordered"] == 24  # never below the supplier's minimum


def test_removing_a_product_from_the_price_list(client):
    segar = detail(client, supplier_id(client, SEGAR))
    milk = price_line(segar, "MILK-1L")
    path = f"/api/suppliers/{segar['id']}/products/{milk['id']}"
    response = client.delete(path, headers=CAFE_OWNER)
    assert response.status_code == 200, response.text
    assert "MILK-1L" not in [p["sku"] for p in response.json()["products"]]
    assert client.delete(path, headers=CAFE_OWNER).status_code == 404

    # Milk is still sold by Pasar Borong, which is now chosen
    pasar = detail(client, supplier_id(client, PASAR))
    assert price_line(pasar, "MILK-1L")["chosen_for_auto_orders"] is True
    assert supplier_logs(client)[0]["action"] == "supplier.product_removed"


# ---------------------------------------------------------------- deactivating

def test_supplier_with_unfinished_order_cannot_be_deactivated(client):
    remove_milk(client)  # draft for Segar Dairy
    order = client.get("/api/purchase-orders", headers=CAFE_OWNER).json()[0]
    segar = supplier_id(client, SEGAR)
    response = client.post(f"/api/suppliers/{segar}/deactivate", headers=CAFE_OWNER)
    assert response.status_code == 409
    assert order["po_number"] in response.json()["detail"]

    reject = client.post(f"/api/purchase-orders/{order['id']}/reject", headers=CAFE_OWNER, json={"reason": "Too dear"})
    assert reject.status_code == 200
    response = client.post(f"/api/suppliers/{segar}/deactivate", headers=CAFE_OWNER)
    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False


def test_inactive_supplier_is_not_used_for_new_orders(client):
    segar = supplier_id(client, SEGAR)
    assert client.post(f"/api/suppliers/{segar}/deactivate", headers=CAFE_OWNER).status_code == 200
    assert client.post(f"/api/suppliers/{segar}/deactivate", headers=CAFE_OWNER).status_code == 409

    assert SEGAR not in [row["name"] for row in suppliers(client)]
    assert SEGAR in [row["name"] for row in suppliers(client, include_inactive=True)]
    summary = client.get("/api/suppliers/summary", headers=CAFE_OWNER).json()
    assert summary["active"] == 4 and summary["inactive"] == 1
    # Oat milk was only sold by Segar Dairy, so it now has no supplier
    assert "OATM-1L" in [r["sku"] for r in client.get("/api/suppliers/products-without-supplier", headers=CAFE_OWNER).json()]

    remove_milk(client)
    order = client.get("/api/purchase-orders", headers=CAFE_OWNER).json()[0]
    assert order["supplier"]["name"] == PASAR  # the dearer but active supplier
    assert order["lines"][0]["unit_price"] == 8.5

    response = client.post(f"/api/suppliers/{segar}/activate", headers=CAFE_OWNER)
    assert response.status_code == 200 and response.json()["is_active"] is True
    actions = [row["action"] for row in supplier_logs(client)]
    assert actions[:2] == ["supplier.activated", "supplier.deactivated"]


def test_there_is_no_delete_endpoint(client):
    segar = supplier_id(client, SEGAR)
    assert client.delete(f"/api/suppliers/{segar}", headers=CAFE_OWNER).status_code == 405


# ---------------------------------------------------------------- order history

def _deliver_milk_order(client, received=15):
    remove_milk(client)
    order_id = client.get("/api/purchase-orders", headers=CAFE_OWNER).json()[0]["id"]
    assert client.post(f"/api/purchase-orders/{order_id}/approve", headers=CAFE_OWNER).status_code == 200
    assert client.post(f"/api/supplier-orders/{order_id}/place", headers=CAFE_OWNER).status_code == 200
    lines = client.get(f"/api/supplier-orders/{order_id}", headers=CAFE_OWNER).json()["lines"]
    response = client.post(
        f"/api/supplier-orders/{order_id}/receive",
        headers=CAFE_EMPLOYEE,
        json={"lines": [{"line_id": lines[0]["id"], "received_quantity": received}]},
    )
    assert response.status_code == 200, response.text
    return order_id


def test_order_history_and_delivery_statistics(client):
    order_id = _deliver_milk_order(client)
    segar = detail(client, supplier_id(client, SEGAR), CAFE_EMPLOYEE)
    row = segar["orders"][0]
    assert row["id"] == order_id
    assert row["status"] == "delivered"
    assert row["total"] == 117.0
    assert row["received_value"] == 117.0
    assert row["placed_at"] is not None and row["delivered_at"] is not None
    assert row["delivery_days"] == 0  # placed and delivered on the same day in the test
    assert row["late"] is False

    stats = segar["stats"]
    assert stats["total_orders"] == 1
    assert stats["delivered"] == 1
    assert stats["delivered_value"] == 117.0
    assert stats["average_delivery_days"] == 0.0
    assert stats["late_deliveries"] == 0

    listed = next(s for s in suppliers(client) if s["name"] == SEGAR)
    assert listed["delivered_orders"] == 1
    assert listed["delivered_value"] == 117.0
    assert listed["last_order_at"] is not None


def test_late_delivery_is_counted(client, db_session):
    order_id = _deliver_milk_order(client, received=10)
    # Pretend the order was placed 3 days before it arrived (Segar usually needs 1 day)
    placed = db_session.scalar(
        select(OrderStatusHistory).where(
            OrderStatusHistory.purchase_order_id == order_id, OrderStatusHistory.to_status == "ordered"
        )
    )
    db_session.execute(
        update(OrderStatusHistory)
        .where(OrderStatusHistory.id == placed.id)
        .values(created_at=placed.created_at - timedelta(days=3))
    )
    db_session.commit()

    segar = detail(client, supplier_id(client, SEGAR))
    row = next(o for o in segar["orders"] if o["id"] == order_id)
    assert row["delivery_days"] == 3
    assert row["late"] is True
    assert row["received_value"] == 78.0  # only 10 of 15 arrived
    assert segar["stats"]["late_deliveries"] == 1
    assert segar["stats"]["average_delivery_days"] == 3.0


def test_supplier_log_filter(client):
    client.post("/api/suppliers", headers=CAFE_OWNER, json=NEW_SUPPLIER)
    rows = supplier_logs(client)
    assert rows and all(row["category"] == "supplier" for row in rows)
    options = client.get("/api/activity-logs/filters", headers=CAFE_OWNER).json()
    assert any(c["value"] == "supplier" for c in options["categories"])


# ---------------------------------------------------------------- database upgrade

def test_schema_upgrade_adds_new_columns_to_an_old_database(tmp_path):
    old_engine = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with old_engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE suppliers (id INTEGER PRIMARY KEY, business_id INTEGER, name VARCHAR(120), "
            "typical_lead_time_days INTEGER, is_active BOOLEAN, created_at DATETIME)"
        ))
        connection.execute(text(
            "INSERT INTO suppliers (business_id, name, typical_lead_time_days, is_active) VALUES (1, 'Old', 2, 1)"
        ))
    assert sorted(upgrade_schema(old_engine)) == ["suppliers.address", "suppliers.notes", "suppliers.updated_at"]
    assert upgrade_schema(old_engine) == []  # safe to repeat
    with old_engine.connect() as connection:
        row = connection.execute(text("SELECT name, address, notes FROM suppliers")).one()
    assert tuple(row) == ("Old", None, None)  # existing data kept
    old_engine.dispose()
