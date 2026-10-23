# AI & Orbyte Integration Guide (feature/ai-anomaly)

Owner: Tati (AI & Integration). This explains how the backend uses the AI
anomaly service and the simulated Orbyte layer.

## What's in this branch
| Path | Purpose |
|---|---|
| `ai/server.py` | FastAPI inference server (runs on RunPod GPU) |
| `ai/ai_client.py` | Backend client: timeout, retry, validation, fallback |
| `ai/start_server.sh` | One-command server start on the Pod |
| `ai/test_ai_client.py` | 11 tests (fake server, no GPU needed) |
| `integration/orbyte_mock.py` | **Simulated** Orbyte: business, roles, permissions, action log |
| `integration/test_orbyte_mock.py` | 12 tests |

## Environment variables (never commit values)
| Name | Example | Notes |
|---|---|---|
| `AI_BASE_URL` | `https://<pod-id>-8000.proxy.runpod.net` | Changes if the Pod is redeployed |
| `INFERENCE_TOKEN` | *(secret)* | Sent as `x-api-token`. Set in Replit Secrets, never in code |
| `AI_TIMEOUT_S` | `2.5` | Optional |
| `ORBYTE_MOCK_LOG` | `integration/data/orbyte_actions.jsonl` | Optional, git-ignored |

## Calling the AI
```python
from ai.ai_client import score_movement   # if the backend runs from the repo root

result = score_movement({
    "request_id": "mov-123",        # store this with the movement
    "product_id": "milk",
    "movement_type": "OUT",
    "quantity": 40,                 # the day's total OUT for this product
    "day_of_week": 2,               # 0 = Monday ... 6 = Sunday
    "recent_avg_usage": 10,         # mean daily OUT, last 30 days
    "usage_std": 2,                 # std dev of daily OUT, last 30 days
    "history_days": 30,             # days of history available
})
```
`score_movement()` **never raises** and **never changes stock** (read-only).

| `status` | Backend should |
|---|---|
| `Normal` | Nothing |
| `Unusual` / `Highly Unusual` | Flag on dashboard for **human review** (not a confirmed error) |
| `Insufficient data` | Show "not enough history" (< 7 days) |
| `Not supported` | IN movements are not scored |
| `Invalid input` | Bug in our request; see `errors` |
| `AI unavailable` | Continue normally; show "AI unavailable" (see `reason`) |

Show only the **first** item of `top_contributing_features`; later items can be noise.

## Suggested wiring (Demo scenario 2)
1. Employee records stock OUT → backend saves the movement first (inside a transaction).
2. Backend calls `score_movement()` with the movement's `request_id`.
3. Store the result (status, score, request_id). A retry with the same `request_id` must not create a second record.
4. Dashboard shows flagged items. Employee reviews → backend checks `anomaly.review` permission → logs the review.

The AI call happens **after** the stock update, so stock never depends on RunPod.

## Orbyte (simulated)
```python
from integration.orbyte_mock import has_permission, require_permission, log_completed_action

require_permission(user_id, business_id, "po.approve")   # raises PermissionDenied
log_completed_action(business_id, user_id, "po.approve", {"po_id": "PO-001"}, request_id)
```
Demo users: `u-owner-1` (owner), `u-mgr-1` (manager), `u-emp-1` (employee) in `BIZ-CAFE-001`;
`u-owner-2` owns `BIZ-MART-002` (used to show business isolation). Only the owner can `po.approve`.
Everything returned is labelled `source: "orbyte-simulated"`. We have no real Orbyte API access.

## Running tests (from repo root)
```
python ai\test_ai_client.py -v
python integration\test_orbyte_mock.py -v
```

## RunPod (demo day)
1. Start the Pod (on a network without SSL inspection; campus Wi-Fi blocked the proxy).
2. Web terminal: `bash /workspace/SDC-HACKATHON/ai/start_server.sh` → must print `"device":"cuda"`.
3. Update `AI_BASE_URL` if the Pod ID changed. Send one warm-up request.
4. **Stop the Pod afterwards** (billed per hour while running).

## Verified so far (2026-10-23)
- `/health` on the Pod: `device: cuda`, NVIDIA RTX 2000 Ada Generation, torch 2.8.0+cu128.
- Milk OUT 40 → `Highly Unusual` on `cuda`, from laptop via public URL and via `ai_client.py`.
- 20 requests: server inference median 1.57 ms; end-to-end median ~378-415 ms (almost all network).
- Not yet wired into the backend.