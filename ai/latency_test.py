import json
import os
import statistics
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
TOKEN = os.environ.get("INFERENCE_TOKEN", "")
N = 20

def score(qty, i):
    payload = {"request_id": f"latency-{i}", "product_id": "milk",
               "movement_type": "OUT", "quantity": qty, "day_of_week": 2,
               "recent_avg_usage": 10, "usage_std": 2, "history_days": 30}
    req = urllib.request.Request(BASE + "/score", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "x-api-token": TOKEN,
                                          "User-Agent": "siso-ai-test-client/1.0"})
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.loads(r.read())
    total_ms = (time.perf_counter() - start) * 1000
    return total_ms, body["inference_ms"], body["device"]

totals, infers, devices = [], [], set()
for i in range(N):
    t, inf, dev = score(40, i)
    totals.append(t)
    infers.append(inf)
    devices.add(dev)

totals.sort()
infers.sort()
print(f"Requests: {N}, device(s): {devices}")
print(f"Server inference_ms  median {statistics.median(infers):.2f}  max {infers[-1]:.2f}")
print(f"End-to-end ms        median {statistics.median(totals):.1f}  p95 {totals[int(0.95 * N) - 1]:.1f}")