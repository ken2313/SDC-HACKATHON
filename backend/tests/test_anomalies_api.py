"""Feature 9: AI anomaly detection. Uses a FAKE AI, so no RunPod / GPU is needed.

Run from the backend folder:  python -m pytest tests/test_anomalies_api.py -v
"""
import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models import ActivityLog, AnomalyFlag, InventoryItem, StockMovement
from app.seed.history_data import seed_history_if_missing
from app.services import anomaly_service
from tests.conftest import CAFE_EMPLOYEE, CAFE_OWNER, SHOP_OWNER

TOP_FEATURES = ["size of movement compared with recent average", "day of the week"]


@pytest.fixture()
def fake_ai(monkeypatch):
    """Switch the AI 'on' and replace the network call with a fake answer."""
    calls = []
    answer = {
        "status": "Highly Unusual", "anomaly_score": 9.99,
        "top_contributing_features": TOP_FEATURES, "expected_range": [4.0, 16.0],
        "device": "cuda", "model_version": "autoencoder-v1", "inference_ms": 1.5,
    }

    def fake_score(payload):
        calls.append(payload)
        if answer.get("raise"):
            raise RuntimeError("boom")
        return {**answer, "request_id": payload["request_id"]}

    monkeypatch.setenv("AI_BASE_URL", "http://fake-ai.test")
    monkeypatch.setattr(anomaly_service, "score_movement", fake_score)
    return {"calls": calls, "answer": answer}


@pytest.fixture()
def milk_with_history(db_session):
    seed_history_if_missing(db_session)
    return db_session.scalars(select(InventoryItem).where(InventoryItem.sku == "MILK-1L")).one()


def add_movement(db, item, quantity, kind="out"):
    """Record a movement directly (same fields the inventory service writes)."""
    change = -quantity if kind == "out" else quantity
    if item.quantity + change < 0:
        item.quantity += 100  # give the test enough stock
    movement = StockMovement(
        business_id=item.business_id, item_id=item.id, user_id=2, movement_type=kind,
        quantity_change=change, quantity_before=item.quantity, quantity_after=item.quantity + change,
        reason="test",
    )
    item.quantity += change
    db.add(movement)
    db.commit()
    return movement.id


def flags_for(movement_id):
    with SessionLocal() as db:
        return db.scalars(select(AnomalyFlag).where(AnomalyFlag.movement_id == movement_id)).all()


def logs(action):
    with SessionLocal() as db:
        return db.scalars(select(ActivityLog).where(ActivityLog.action == action)).all()


# ---------------------------------------------------------------- normal

def test_usage_stats_use_the_30_day_history(db_session, milk_with_history):
    movement_id = add_movement(db_session, milk_with_history, 15)
    stats = anomaly_service.compute_usage_stats(db_session, db_session.get(StockMovement, movement_id))
    assert stats["day_total_out"] == 15
    assert stats["history_days"] >= 25          # ~30 days of synthetic usage
    assert 7 <= stats["recent_avg_usage"] <= 14  # milk is about 10 cartons a day
    assert stats["usage_std"] > 0
    assert 0 <= stats["day_of_week"] <= 6


def test_flag_is_saved_and_logged_as_system(db_session, milk_with_history, fake_ai):
    movement_id = add_movement(db_session, milk_with_history, 40)
    anomaly_service.check_movement_for_anomaly(movement_id)

    sent = fake_ai["calls"][0]
    assert sent["product_id"] == "MILK-1L"
    assert sent["quantity"] == 40
    assert sent["movement_type"] == "OUT"
    assert sent["request_id"] == f"mov-{movement_id}"

    [flag] = flags_for(movement_id)
    assert flag.status == "Highly Unusual"
    assert flag.device == "cuda"
    assert flag.top_feature == TOP_FEATURES[0]  # only the top one is kept
    [log] = logs("anomaly.flagged")
    assert log.user_id is None                   # shown as "System"
    assert log.entity_id == flag.id


def test_normal_result_is_kept_but_not_listed_as_a_flag(client, db_session, milk_with_history, fake_ai):
    fake_ai["answer"]["status"] = "Normal"
    movement_id = add_movement(db_session, milk_with_history, 10)
    anomaly_service.check_movement_for_anomaly(movement_id)

    assert flags_for(movement_id)[0].status == "Normal"
    assert logs("anomaly.flagged") == []
    assert client.get("/api/anomalies", headers=CAFE_OWNER).json() == []
    every_check = client.get("/api/anomalies", headers=CAFE_OWNER, params={"results": "all"}).json()
    assert len(every_check) == 1


# ---------------------------------------------------------------- edge cases

def test_checking_twice_never_duplicates(db_session, milk_with_history, fake_ai):
    movement_id = add_movement(db_session, milk_with_history, 40)
    anomaly_service.check_movement_for_anomaly(movement_id)
    anomaly_service.check_movement_for_anomaly(movement_id)
    assert len(flags_for(movement_id)) == 1
    assert len(fake_ai["calls"]) == 1


def test_ai_not_configured_does_nothing(db_session, milk_with_history, fake_ai, monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", "")
    movement_id = add_movement(db_session, milk_with_history, 40)
    anomaly_service.check_movement_for_anomaly(movement_id)
    assert flags_for(movement_id) == []
    assert fake_ai["calls"] == []


def test_ai_unavailable_is_recorded_and_not_listed(client, db_session, milk_with_history, fake_ai):
    fake_ai["answer"].update(status="AI unavailable", anomaly_score=None, reason="HTTP 403")
    movement_id = add_movement(db_session, milk_with_history, 40)
    anomaly_service.check_movement_for_anomaly(movement_id)
    [flag] = flags_for(movement_id)
    assert flag.status == "AI unavailable"
    assert flag.reason == "HTTP 403"
    assert client.get("/api/anomalies", headers=CAFE_OWNER).json() == []


def test_a_crash_in_the_ai_never_raises(db_session, milk_with_history, fake_ai):
    fake_ai["answer"]["raise"] = True
    movement_id = add_movement(db_session, milk_with_history, 40)
    anomaly_service.check_movement_for_anomaly(movement_id)  # must not raise
    assert flags_for(movement_id) == []


def test_stock_in_is_not_checked(db_session, milk_with_history, fake_ai):
    movement_id = add_movement(db_session, milk_with_history, 30, kind="in")
    anomaly_service.check_movement_for_anomaly(movement_id)
    assert flags_for(movement_id) == []
    assert fake_ai["calls"] == []


# ---------------------------------------------------------------- API + permissions

def flagged_movement(db_session, milk):
    movement_id = add_movement(db_session, milk, 40)
    anomaly_service.check_movement_for_anomaly(movement_id)
    return flags_for(movement_id)[0].id


def test_employee_can_list_and_review_and_it_is_logged(client, db_session, milk_with_history, fake_ai):
    flag_id = flagged_movement(db_session, milk_with_history)

    listed = client.get("/api/anomalies", headers=CAFE_EMPLOYEE).json()
    assert [f["id"] for f in listed] == [flag_id]
    assert listed[0]["product_name"] == "Fresh Milk 1L"
    assert "human review" in listed[0]["note"]

    response = client.post(f"/api/anomalies/{flag_id}/review", headers=CAFE_EMPLOYEE,
                           json={"note": "Catering order for 40 people, usage was real."})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reviewed"] is True
    assert body["reviewed_by_name"] == "Hafiz Ismail"

    [log] = logs("anomaly.reviewed")
    assert log.user_id == 2
    assert client.get("/api/anomalies", headers=CAFE_EMPLOYEE).json() == []  # no longer open
    reviewed = client.get("/api/anomalies", headers=CAFE_EMPLOYEE, params={"state": "reviewed"}).json()
    assert [f["id"] for f in reviewed] == [flag_id]


def test_cannot_review_twice(client, db_session, milk_with_history, fake_ai):
    flag_id = flagged_movement(db_session, milk_with_history)
    first = client.post(f"/api/anomalies/{flag_id}/review", headers=CAFE_OWNER, json={"note": "Checked."})
    second = client.post(f"/api/anomalies/{flag_id}/review", headers=CAFE_EMPLOYEE, json={"note": "Again."})
    assert first.status_code == 200
    assert second.status_code == 409


def test_other_business_cannot_see_or_review(client, db_session, milk_with_history, fake_ai):
    flag_id = flagged_movement(db_session, milk_with_history)
    assert client.get("/api/anomalies", headers=SHOP_OWNER).json() == []
    response = client.post(f"/api/anomalies/{flag_id}/review", headers=SHOP_OWNER, json={"note": "Not mine."})
    assert response.status_code == 404


def test_blank_note_and_missing_user_are_rejected(client, db_session, milk_with_history, fake_ai):
    flag_id = flagged_movement(db_session, milk_with_history)
    blank = client.post(f"/api/anomalies/{flag_id}/review", headers=CAFE_OWNER, json={"note": "   "})
    no_user = client.get("/api/anomalies")
    assert blank.status_code == 422
    assert no_user.status_code == 401


def test_ai_status_endpoint(client, monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", "")
    assert client.get("/api/anomalies/status", headers=CAFE_OWNER).json() == {"ai_configured": False}
    monkeypatch.setenv("AI_BASE_URL", "http://fake-ai.test")
    assert client.get("/api/anomalies/status", headers=CAFE_OWNER).json() == {"ai_configured": True}