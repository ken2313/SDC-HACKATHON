"""Client for the SISO AI anomaly service (PyTorch autoencoder on RunPod GPU).

Rules:
- score_movement() NEVER raises. If the AI is down, slow or returns junk,
  it returns status "AI unavailable" so the core inventory app keeps working.
- Scoring is read-only: it never changes stock. The backend stores request_id,
  so a retried request can never double-change stock.
- Config comes from environment variables, never hard-coded:
    AI_BASE_URL      e.g. https://<pod-id>-8000.proxy.runpod.net
    INFERENCE_TOKEN  secret, sent as the x-api-token header
    AI_TIMEOUT_S     optional, default 2.5 seconds
"""
import json
import os
import time
import urllib.error
import urllib.request
import uuid

MAX_RETRIES = 1  # 1 retry -> at most 2 attempts (~5.5 s worst case)
VALID_STATUSES = {"Normal", "Unusual", "Highly Unusual",
                  "Insufficient data", "Not supported"}
CONTRACT_FIELDS = ["request_id", "product_id", "movement_type", "quantity",
                   "day_of_week", "recent_avg_usage", "usage_std", "history_days"]


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _validate_input(m):
    errors = []
    if not isinstance(m.get("request_id"), str) or not m["request_id"].strip():
        errors.append("request_id must be a non-empty string")
    if not isinstance(m.get("product_id"), str) or not m["product_id"].strip():
        errors.append("product_id must be a non-empty string")
    if m.get("movement_type") not in ("OUT", "IN"):
        errors.append("movement_type must be 'OUT' or 'IN'")
    if not _is_number(m.get("quantity")) or m["quantity"] <= 0:
        errors.append("quantity must be a number > 0")
    dow = m.get("day_of_week")
    if not isinstance(dow, int) or isinstance(dow, bool) or not 0 <= dow <= 6:
        errors.append("day_of_week must be an integer 0-6")
    for f in ("recent_avg_usage", "usage_std"):
        if not _is_number(m.get(f)) or m[f] < 0:
            errors.append(f"{f} must be a number >= 0")
    hd = m.get("history_days")
    if not isinstance(hd, int) or isinstance(hd, bool) or hd < 0:
        errors.append("history_days must be an integer >= 0")
    return errors


def _validate_output(body, request_id):
    if not isinstance(body, dict):
        return "response is not a JSON object"
    if body.get("status") not in VALID_STATUSES:
        return f"unknown status {body.get('status')!r}"
    if body.get("request_id") != request_id:
        return "request_id in response does not match"
    return None


def _result(status, request_id, reason, errors=None):
    out = {"status": status, "request_id": request_id, "anomaly_score": None,
           "top_contributing_features": [], "expected_range": None,
           "device": None, "reason": reason}
    if errors:
        out["errors"] = errors
    return out


def score_movement(movement):
    """Score one stock movement. Always returns a dict; never raises."""
    m = dict(movement or {})
    m.setdefault("request_id", str(uuid.uuid4()))
    rid = m["request_id"]

    errors = _validate_input(m)
    if errors:
        return _result("Invalid input", rid, "input failed validation", errors)

    base_url = os.environ.get("AI_BASE_URL", "").rstrip("/")
    token = os.environ.get("INFERENCE_TOKEN", "")
    try:
        timeout = float(os.environ.get("AI_TIMEOUT_S", "2.5"))
    except ValueError:
        timeout = 2.5
    if not base_url:
        return _result("AI unavailable", rid, "AI_BASE_URL is not configured")

    payload = json.dumps({f: m[f] for f in CONTRACT_FIELDS}).encode()
    headers = {"Content-Type": "application/json",
               "x-api-token": token,
               "User-Agent": "siso-ai-client/1.0"}  # RunPod proxy blocks default urllib agent

    reason = "unknown error"
    for attempt in range(MAX_RETRIES + 1):
        start = time.perf_counter()
        try:
            req = urllib.request.Request(base_url + "/score", data=payload,
                                         headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = json.loads(r.read())
        except urllib.error.HTTPError as e:
            reason = f"HTTP {e.code}"
            if e.code < 500:
                break  # 4xx (bad token, Pod stopped, bad request): retrying won't help
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            reason = f"{type(e).__name__}: {e}"
        else:
            problem = _validate_output(body, rid)
            if problem is None:
                body["round_trip_ms"] = round((time.perf_counter() - start) * 1000, 1)
                return body
            reason = f"invalid AI response: {problem}"
            break
        if attempt < MAX_RETRIES:
            time.sleep(0.5)

    return _result("AI unavailable", rid, reason)


if __name__ == "__main__":
    demo = {"request_id": "demo-milk-40", "product_id": "milk", "movement_type": "OUT",
            "quantity": 40, "day_of_week": 2, "recent_avg_usage": 10,
            "usage_std": 2, "history_days": 30}
    print(json.dumps(score_movement(demo), indent=2))