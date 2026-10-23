import json
import os
import time
from typing import Literal

import pandas as pd
import torch
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from features import FEATURE_NAMES, build_features, apply_scaler, load_scaler
from model import Autoencoder, reconstruction_error

MIN_HISTORY_DAYS = 7
API_TOKEN = os.environ.get("INFERENCE_TOKEN", "")  # shared secret, set on the Pod
device = "cuda" if torch.cuda.is_available() else "cpu"

# ---------- load the trained model once at startup ----------
with open("config.json") as f:
    config = json.load(f)
scaler = load_scaler("scaler.json")
model = Autoencoder(n_features=len(FEATURE_NAMES)).to(device)
model.load_state_dict(torch.load("model.pt", map_location=device, weights_only=True))
model.eval()

LABELS = {
    "usage_ratio": "size of movement compared with recent average",
    "z_score": "distance from the normal usage range",
    "variation": "how unstable recent usage has been",
    "dow_sin": "day of the week",
    "dow_cos": "day of the week",
}

def run_model(df: pd.DataFrame):
    """Feature building on CPU, model forward pass on the device (GPU if available)."""
    x = torch.tensor(apply_scaler(build_features(df), scaler)).to(device)
    score, per_feature = reconstruction_error(model, x)
    if device == "cuda":
        torch.cuda.synchronize()
    return float(score[0].item()), per_feature[0].cpu().tolist()

# warm-up so the first real request isn't slow
run_model(pd.DataFrame([{"quantity": 10, "recent_avg": 10, "usage_std": 2, "day_of_week": 2}]))

app = FastAPI(title="Inventory anomaly inference (autoencoder)")

class MovementRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    product_id: str = Field(min_length=1, max_length=64)
    movement_type: Literal["OUT", "IN"]
    quantity: float = Field(ge=0, le=1_000_000)
    day_of_week: int = Field(ge=0, le=6)
    recent_avg_usage: float = Field(ge=0, le=1_000_000)
    usage_std: float = Field(ge=0, le=1_000_000)
    history_days: int = Field(ge=0, le=3650)

@app.get("/health")
def health():
    return {
        "status": "ok",
        "device": device,
        "cuda_available": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "torch_version": torch.__version__,
        "model_version": config["model_version"],
    }

@app.post("/score")
def score_movement(req: MovementRequest, x_api_token: str = Header(default="")):
    if API_TOKEN and x_api_token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid API token")

    base = {"request_id": req.request_id, "product_id": req.product_id,
            "model_version": config["model_version"], "anomaly_score": None,
            "top_contributing_features": [], "expected_range": None,
            "inference_ms": None, "device": device}

    if req.movement_type != "OUT":
        return {**base, "status": "Not supported",
                "reason": "This model only scores stock-out movements."}
    if req.history_days < MIN_HISTORY_DAYS:
        return {**base, "status": "Insufficient data",
                "reason": f"Needs at least {MIN_HISTORY_DAYS} days of history."}

    df = pd.DataFrame([{"quantity": req.quantity, "recent_avg": req.recent_avg_usage,
                        "usage_std": req.usage_std, "day_of_week": req.day_of_week}])
    start = time.perf_counter()
    score, per_feature = run_model(df)
    inference_ms = (time.perf_counter() - start) * 1000

    if score >= config["highly_unusual_threshold"]:
        status = "Highly Unusual"
    elif score >= config["unusual_threshold"]:
        status = "Unusual"
    else:
        status = "Normal"

    ranked = sorted(zip(FEATURE_NAMES, per_feature), key=lambda p: p[1], reverse=True)
    top = []
    for name, _ in ranked:
        label = LABELS[name]
        if label not in top:
            top.append(label)
    low = max(0.0, req.recent_avg_usage - 2 * req.usage_std)
    high = req.recent_avg_usage + 2 * req.usage_std

    return {**base, "status": status, "anomaly_score": round(score, 4),
            "top_contributing_features": top[:2],
            "expected_range": [round(low, 1), round(high, 1)],
            "inference_ms": round(inference_ms, 2),
            "note": "Potential anomaly for human review, not a confirmed error."}