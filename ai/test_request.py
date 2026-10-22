import json
import os
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
TOKEN = os.environ.get("INFERENCE_TOKEN", "")

def call(path, payload=None):
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json",
                                          "x-api-token": TOKEN})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

print("HEALTH:", json.dumps(call("/health"), indent=2))
milk = {"product_id": "milk", "movement_type": "OUT", "day_of_week": 2,
        "recent_avg_usage": 10, "usage_std": 2, "history_days": 30}
for qty in (10, 40):
    result = call("/score", {**milk, "request_id": f"test-{qty}", "quantity": qty})
    print(f"\nMILK OUT {qty}:", json.dumps(result, indent=2))