"""Feature 3 tests: automatic purchase order generation and owner approval.

Run from the backend folder:   pytest -v

Seeded data used here (Kopi Kita Café, user 1 = owner, user 2 = employee):
  MILK-1L   20 cartons, reorder 10   suppliers: Segar Dairy RM7.80 (min 6), Pasar Borong RM8.50 (min 12)
  OATM-1L   12 cartons, reorder 6    supplier:  Segar Dairy RM11.50 (min 6)
  CHOC-500   0 tins,    reorder 4    (already low at start-up)   Pasar Borong RM24.50 (min 2)
  COFB-ROB   4 bags,    reorder 5    (already low at start-up)   Kopi Borneo RM48.00 (min 2)
  LID-12OZ  11 sleeves, reorder 15   (already low at start-up)   PakEco RM9.50 (min 5)
No purchase orders exist until a stock change or "Generate" creates them.
"""
import json

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import ActivityLog, PurchaseOrder, PurchaseOrderItem
from app.services.purchase_order_service import recommended_quantity
from tests.conftest import CAFE_EMPLOYEE, CAFE_OWNER, SHOP_OWNER, find_item


def move(client, headers, item_id, movement_type, quantity):
    return client.post(
        f"/api/inventory/{item_id}/movements",
        headers=headers,
        json={"movement_type": movement_type, "quantity": quantity},
    )


def orders(client, headers, status="all"):
    response = client.get("/api/purchase-orders", headers=headers, params={"status": status})
    assert response.status_code == 200, response.text
    return response.json()


def line_for(order, sku):
    return next(line for line in order["lines"] if line["sku"] == sku)


def milk_order_via_employee(client):
    """The café scenario: the employee removes 15 cartons, 20 -> 5."""
    milk = find_item(client, CAFE_EMPLOYEE, "MILK-1L")
    response = move(client, CAFE_EMPLOYEE, milk["id"], "out", 15)
    assert response.status_code == 201, response.text
    return milk, response.json()


# ---------------------------------------------------------------- reorder rule

@pytest.mark.parametrize(
    "quantity, threshold, min_order, expected",
    [
        (5, 10, 6, 15),    # milk: refill to 2 x 10 = 20
        (0, 4, 2, 8),
        (10, 10, 6, 10),   # exactly at the threshold
        (19, 10, 6, 6),    # rule gives 1, supplier minimum 6 wins
        (0, 0, 1, 1),      # never below 1
    ],
)
def test_recommended_quantity(quantity, threshold, min_order, expected):
    assert recommended_quantity(quantity, threshold, min_order) == expected


# ---------------------------------------------------------------- the café scenario

def test_stock_drop_prepares_a_draft_order(client, db_session):
    milk, body = milk_order_via_employee(client)
    assert body["item"]["quantity"] == 5
    assert body["draft_purchase_order"] is not None

    found = orders(client, CAFE_OWNER)
    assert len(found) == 1
    order = found[0]
    assert order["status"] == "draft"          # NOT approved: a human must decide
    assert order["source"] == "auto"
    assert order["supplier"]["name"] == "Segar Dairy Sdn Bhd (demo)"  # cheapest supplier
    assert len(order["lines"]) == 1
    line = order["lines"][0]
    assert (line["sku"], line["quantity_ordered"], line["unit_price"], line["line_total"]) == ("MILK-1L", 15, 7.8, 117.0)
    assert order["total"] == 117.0
    assert order["is_editable"] is True
    assert order["estimated_delivery_date"] is not None

    entry = db_session.scalars(select(ActivityLog).where(ActivityLog.action == "po.generated")).one()
    assert entry.entity_type == "purchase_order"
    assert json.loads(entry.new_value)["total"] == 117.0


def test_more_stock_changes_do_not_create_a_second_order(client):
    milk, _ = milk_order_via_employee(client)
    assert move(client, CAFE_EMPLOYEE, milk["id"], "out", 2).status_code == 201
    found = orders(client, CAFE_OWNER)
    assert len(found) == 1
    assert len(found[0]["lines"]) == 1


def test_second_product_from_same_supplier_joins_the_open_draft(client, db_session):
    milk_order_via_employee(client)
    oat = find_item(client, CAFE_EMPLOYEE, "OATM-1L")
    assert move(client, CAFE_EMPLOYEE, oat["id"], "out", 8).status_code == 201  # 12 -> 4, reorder 6

    found = orders(client, CAFE_OWNER)
    assert len(found) == 1
    assert {line["sku"] for line in found[0]["lines"]} == {"MILK-1L", "OATM-1L"}
    assert line_for(found[0], "OATM-1L")["quantity_ordered"] == 8  # 12 - 4
    assert found[0]["total"] == round(15 * 7.8 + 8 * 11.5, 2)
    assert db_session.scalars(select(ActivityLog).where(ActivityLog.action == "po.updated")).first() is not None


def test_no_order_when_stock_is_still_fine(client):
    milk = find_item(client, CAFE_EMPLOYEE, "MILK-1L")
    body = move(client, CAFE_EMPLOYEE, milk["id"], "out", 5).json()  # 20 -> 15, above reorder level
    assert body["draft_purchase_order"] is None
    assert orders(client, CAFE_OWNER) == []


# ---------------------------------------------------------------- manual generation

def test_generate_creates_one_draft_per_supplier_and_never_duplicates(client):
    response = client.post("/api/purchase-orders/generate", headers=CAFE_EMPLOYEE)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["created_orders"] == 3          # Pasar Borong, Kopi Borneo, PakEco
    assert result["lines_added"] == 3
    by_sku = {line["sku"]: line for order in result["orders"] for line in order["lines"]}
    assert by_sku["CHOC-500"]["quantity_ordered"] == 8     # 2 x 4 - 0
    assert by_sku["COFB-ROB"]["quantity_ordered"] == 6     # 2 x 5 - 4
    assert by_sku["LID-12OZ"]["quantity_ordered"] == 19    # 2 x 15 - 11

    again = client.post("/api/purchase-orders/generate", headers=CAFE_EMPLOYEE).json()
    assert again["created_orders"] == 0 and again["lines_added"] == 0
    assert len(orders(client, CAFE_OWNER)) == 3


def test_needs_list_shows_recommendation_before_any_order(client):
    needs = client.get("/api/purchase-orders/needs", headers=CAFE_OWNER).json()
    by_sku = {row["sku"]: row for row in needs}
    assert set(by_sku) == {"CHOC-500", "COFB-ROB", "LID-12OZ"}
    assert by_sku["CHOC-500"]["recommended_quantity"] == 8
    assert by_sku["CHOC-500"]["estimated_total"] == 196.0   # 8 x RM24.50
    assert by_sku["CHOC-500"]["urgency"] == "critical"
    client.post("/api/purchase-orders/generate", headers=CAFE_OWNER)
    assert client.get("/api/purchase-orders/needs", headers=CAFE_OWNER).json() == []


def test_product_without_supplier_price_is_skipped_with_a_reason(client):
    created = client.post(
        "/api/inventory", headers=CAFE_OWNER,
        json={"name": "Test Syrup", "sku": "SYR-1", "category": "Syrup", "quantity": 1, "reorder_threshold": 5},
    )
    assert created.status_code == 201
    needs = {row["sku"]: row for row in client.get("/api/purchase-orders/needs", headers=CAFE_OWNER).json()}
    assert needs["SYR-1"]["blocked_reason"] == "No supplier price on file for this product."
    assert needs["SYR-1"]["supplier_id"] is None

    result = client.post("/api/purchase-orders/generate", headers=CAFE_OWNER).json()
    assert "Test Syrup" in {row["item_name"] for row in result["skipped"]}
    skus_ordered = {line["sku"] for order in orders(client, CAFE_OWNER) for line in order["lines"]}
    assert "SYR-1" not in skus_ordered


def test_auto_drafting_can_be_switched_off(client, monkeypatch):
    monkeypatch.setenv("AUTO_GENERATE_PO", "false")
    milk = find_item(client, CAFE_EMPLOYEE, "MILK-1L")
    body = move(client, CAFE_EMPLOYEE, milk["id"], "out", 15).json()
    assert body["item"]["quantity"] == 5            # the stock change still works
    assert body["draft_purchase_order"] is None
    assert orders(client, CAFE_OWNER) == []


# ---------------------------------------------------------------- approval (human in the loop)

def test_owner_approves_and_it_is_logged(client, db_session):
    milk_order_via_employee(client)
    order = orders(client, CAFE_OWNER)[0]

    response = client.post(f"/api/purchase-orders/{order['id']}/approve", headers=CAFE_OWNER)
    assert response.status_code == 200, response.text
    approved = response.json()
    assert approved["status"] == "approved"
    assert approved["decided_by_name"] == "Aisyah Rahman"
    assert approved["decided_at"] is not None
    assert approved["is_editable"] is False

    entry = db_session.scalars(select(ActivityLog).where(ActivityLog.action == "po.approved")).one()
    assert entry.user_id == 1
    assert json.loads(entry.old_value) == {"status": "draft"}
    assert json.loads(entry.new_value)["status"] == "approved"
    assert json.loads(entry.new_value)["decision"] == "approved"


def test_employee_cannot_approve_or_reject(client, db_session):
    milk_order_via_employee(client)
    order_id = orders(client, CAFE_OWNER)[0]["id"]
    assert client.post(f"/api/purchase-orders/{order_id}/approve", headers=CAFE_EMPLOYEE).status_code == 403
    assert client.post(
        f"/api/purchase-orders/{order_id}/reject", headers=CAFE_EMPLOYEE, json={"reason": "just because"}
    ).status_code == 403
    assert orders(client, CAFE_OWNER)[0]["status"] == "draft"   # nothing changed
    assert db_session.scalars(select(ActivityLog).where(ActivityLog.action == "po.approved")).first() is None


def test_an_order_can_only_be_decided_once(client):
    milk_order_via_employee(client)
    order_id = orders(client, CAFE_OWNER)[0]["id"]
    assert client.post(f"/api/purchase-orders/{order_id}/approve", headers=CAFE_OWNER).status_code == 200
    assert client.post(f"/api/purchase-orders/{order_id}/approve", headers=CAFE_OWNER).status_code == 409
    rejected = client.post(f"/api/purchase-orders/{order_id}/reject", headers=CAFE_OWNER, json={"reason": "too late"})
    assert rejected.status_code == 409
    assert client.patch(
        f"/api/purchase-orders/{order_id}", headers=CAFE_OWNER, json={"notes": "late change"}
    ).status_code == 409


def test_reject_needs_a_reason_and_frees_the_product(client, db_session):
    milk, _ = milk_order_via_employee(client)
    order_id = orders(client, CAFE_OWNER)[0]["id"]
    url = f"/api/purchase-orders/{order_id}/reject"

    assert client.post(url, headers=CAFE_OWNER, json={}).status_code == 422
    assert client.post(url, headers=CAFE_OWNER, json={"reason": "  "}).status_code == 422
    assert client.post(url, headers=CAFE_OWNER, json={"reason": "no"}).status_code == 422

    response = client.post(url, headers=CAFE_OWNER, json={"reason": "Supplier too expensive this week"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rejected"
    assert response.json()["decision_note"] == "Supplier too expensive this week"

    entry = db_session.scalars(select(ActivityLog).where(ActivityLog.action == "po.rejected")).one()
    assert json.loads(entry.new_value)["reason"] == "Supplier too expensive this week"

    # The rejected order no longer blocks the product: a new draft can be prepared
    result = client.post("/api/purchase-orders/generate", headers=CAFE_OWNER).json()
    assert "MILK-1L" in {line["sku"] for order in result["orders"] for line in order["lines"]}


def test_approval_is_blocked_if_a_product_was_archived(client):
    milk, _ = milk_order_via_employee(client)
    order_id = orders(client, CAFE_OWNER)[0]["id"]
    assert client.post(f"/api/inventory/{milk['id']}/archive", headers=CAFE_OWNER).status_code == 200
    response = client.post(f"/api/purchase-orders/{order_id}/approve", headers=CAFE_OWNER)
    assert response.status_code == 409
    assert "archived" in response.json()["detail"]


# ---------------------------------------------------------------- editing

def test_owner_edits_quantity_and_total_follows(client, db_session):
    milk_order_via_employee(client)
    order = orders(client, CAFE_OWNER)[0]
    line_id = order["lines"][0]["id"]

    response = client.patch(
        f"/api/purchase-orders/{order['id']}",
        headers=CAFE_OWNER,
        json={"lines": [{"line_id": line_id, "quantity": 24}], "notes": "Need extra for the weekend"},
    )
    assert response.status_code == 200, response.text
    edited = response.json()
    assert edited["lines"][0]["quantity_ordered"] == 24
    assert edited["lines"][0]["recommended_quantity"] == 15   # the original suggestion is kept
    assert edited["total"] == round(24 * 7.8, 2)
    assert edited["notes"] == "Need extra for the weekend"

    entry = db_session.scalars(select(ActivityLog).where(ActivityLog.action == "po.updated")).one()
    assert json.loads(entry.old_value)["lines"] == {"MILK-1L": 15}
    assert json.loads(entry.new_value)["lines"] == {"MILK-1L": 24}


def test_edit_with_no_real_change_writes_no_log(client, db_session):
    milk_order_via_employee(client)
    order = orders(client, CAFE_OWNER)[0]
    client.patch(
        f"/api/purchase-orders/{order['id']}", headers=CAFE_OWNER,
        json={"lines": [{"line_id": order["lines"][0]["id"], "quantity": 15}]},
    )
    assert db_session.scalars(select(ActivityLog).where(ActivityLog.action == "po.updated")).first() is None


def test_edit_validation(client):
    milk_order_via_employee(client)
    order = orders(client, CAFE_OWNER)[0]
    url = f"/api/purchase-orders/{order['id']}"
    line_id = order["lines"][0]["id"]

    assert client.patch(url, headers=CAFE_OWNER, json={"lines": [{"line_id": line_id, "quantity": 0}]}).status_code == 422
    assert client.patch(url, headers=CAFE_OWNER, json={"lines": [{"line_id": line_id, "quantity": -3}]}).status_code == 422
    below_minimum = client.patch(url, headers=CAFE_OWNER, json={"lines": [{"line_id": line_id, "quantity": 5}]})
    assert below_minimum.status_code == 422 and "minimum order" in below_minimum.json()["detail"]
    assert client.patch(url, headers=CAFE_OWNER, json={"lines": [{"line_id": 99999, "quantity": 10}]}).status_code == 404
    assert client.patch(url, headers=CAFE_OWNER, json={"unit_price": 0.01}).status_code == 422  # prices are not editable
    assert orders(client, CAFE_OWNER)[0]["lines"][0]["quantity_ordered"] == 15   # nothing changed


def test_switch_supplier_reprices_and_checks_the_catalogue(client):
    milk_order_via_employee(client)
    order = orders(client, CAFE_OWNER)[0]
    url = f"/api/purchase-orders/{order['id']}"
    eligible = {row["name"]: row for row in order["eligible_suppliers"]}
    assert set(eligible) == {"Segar Dairy Sdn Bhd (demo)", "Pasar Borong Jaya (demo)"}

    segar_id = order["supplier"]["id"]
    pasar_id = eligible["Pasar Borong Jaya (demo)"]["id"]
    switched = client.patch(url, headers=CAFE_OWNER, json={"supplier_id": pasar_id})
    assert switched.status_code == 200, switched.text
    body = switched.json()
    assert body["supplier"]["name"] == "Pasar Borong Jaya (demo)"
    assert body["lines"][0]["unit_price"] == 8.5
    assert body["total"] == round(15 * 8.5, 2)

    # PakEco (packaging) does not sell milk: the switch is refused
    generated = client.post("/api/purchase-orders/generate", headers=CAFE_OWNER).json()
    pakeco = next(o["supplier"]["id"] for o in generated["orders"] if o["supplier"]["name"].startswith("PakEco"))
    refused = client.patch(url, headers=CAFE_OWNER, json={"supplier_id": pakeco})
    assert refused.status_code == 422 and "does not sell" in refused.json()["detail"]
    assert client.patch(url, headers=CAFE_OWNER, json={"supplier_id": 10_000}).status_code == 404
    assert segar_id != pasar_id


def test_cannot_use_another_business_supplier(client):
    milk_order_via_employee(client)
    order = orders(client, CAFE_OWNER)[0]
    shop_needs = client.post("/api/purchase-orders/generate", headers=SHOP_OWNER).json()
    shop_supplier_id = shop_needs["orders"][0]["supplier"]["id"]
    response = client.patch(
        f"/api/purchase-orders/{order['id']}", headers=CAFE_OWNER, json={"supplier_id": shop_supplier_id}
    )
    assert response.status_code == 404


def test_remove_line_but_never_the_last_one(client):
    milk_order_via_employee(client)
    oat = find_item(client, CAFE_EMPLOYEE, "OATM-1L")
    move(client, CAFE_EMPLOYEE, oat["id"], "out", 8)
    order = orders(client, CAFE_OWNER)[0]
    assert len(order["lines"]) == 2
    oat_line = line_for(order, "OATM-1L")
    milk_line = line_for(order, "MILK-1L")

    removed = client.delete(f"/api/purchase-orders/{order['id']}/lines/{oat_line['id']}", headers=CAFE_OWNER)
    assert removed.status_code == 200, removed.text
    assert [line["sku"] for line in removed.json()["lines"]] == ["MILK-1L"]

    last = client.delete(f"/api/purchase-orders/{order['id']}/lines/{milk_line['id']}", headers=CAFE_OWNER)
    assert last.status_code == 409


# ---------------------------------------------------------------- safety nets

def test_database_refuses_a_second_outstanding_line_for_the_same_product(client, db_session):
    milk_order_via_employee(client)
    order = db_session.scalars(select(PurchaseOrder)).one()
    existing = db_session.scalars(select(PurchaseOrderItem)).one()
    db_session.add(
        PurchaseOrderItem(
            business_id=order.business_id, purchase_order_id=order.id, item_id=existing.item_id,
            quantity_ordered=3, recommended_quantity=3, unit_price_sen=780, outstanding=True,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ---------------------------------------------------------------- access control and separation

def test_unknown_user_is_rejected(client):
    assert client.get("/api/purchase-orders").status_code == 401
    assert client.post("/api/purchase-orders/generate", headers={"X-User-Id": "999"}).status_code == 401


def test_other_business_cannot_see_or_touch_the_order(client):
    milk_order_via_employee(client)
    order_id = orders(client, CAFE_OWNER)[0]["id"]
    assert orders(client, SHOP_OWNER) == []
    assert client.get(f"/api/purchase-orders/{order_id}", headers=SHOP_OWNER).status_code == 404
    assert client.post(f"/api/purchase-orders/{order_id}/approve", headers=SHOP_OWNER).status_code == 404
    assert client.patch(f"/api/purchase-orders/{order_id}", headers=SHOP_OWNER, json={"notes": "x"}).status_code == 404


def test_summary_counts_follow_the_workflow(client):
    summary = client.get("/api/purchase-orders/summary", headers=CAFE_OWNER).json()
    assert summary == {
        "awaiting_approval": 0, "approved": 0, "rejected": 0, "awaiting_value": 0.0,
        "needs_ordering": 3, "no_supplier": 0,
    }
    milk_order_via_employee(client)
    summary = client.get("/api/purchase-orders/summary", headers=CAFE_OWNER).json()
    assert summary["awaiting_approval"] == 1
    assert summary["awaiting_value"] == 117.0
    assert summary["needs_ordering"] == 3

    order_id = orders(client, CAFE_OWNER)[0]["id"]
    client.post(f"/api/purchase-orders/{order_id}/approve", headers=CAFE_OWNER)
    summary = client.get("/api/purchase-orders/summary", headers=CAFE_OWNER).json()
    assert (summary["awaiting_approval"], summary["approved"], summary["awaiting_value"]) == (0, 1, 0.0)


def test_status_filter(client):
    milk_order_via_employee(client)
    assert len(orders(client, CAFE_OWNER, "awaiting")) == 1
    assert len(orders(client, CAFE_OWNER, "draft")) == 1
    assert orders(client, CAFE_OWNER, "approved") == []
    assert client.get("/api/purchase-orders", headers=CAFE_OWNER, params={"status": "bogus"}).status_code == 422
