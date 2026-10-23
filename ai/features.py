import json
import numpy as np
import pandas as pd

FEATURE_NAMES = ["usage_ratio", "z_score", "variation", "dow_sin", "dow_cos"]

def build_features(df: pd.DataFrame) -> np.ndarray:
    avg = df["recent_avg"].to_numpy(dtype=float)
    std = df["usage_std"].to_numpy(dtype=float)
    qty = df["quantity"].to_numpy(dtype=float)
    dow = df["day_of_week"].to_numpy(dtype=float)

    # how big is today's movement compared with the recent average
    usage_ratio = np.clip(qty / np.maximum(avg, 1.0), 0, 10)
    # how many "normal wobbles" away from the recent average
    z_score = np.clip((qty - avg) / np.maximum(std, 0.5), -10, 10)
    # how unstable the recent usage has been
    variation = std / np.maximum(avg, 1.0)
    # day of week as a circle, so Sunday and Monday are neighbours
    dow_sin = np.sin(2 * np.pi * dow / 7)
    dow_cos = np.cos(2 * np.pi * dow / 7)

    return np.column_stack(
        [usage_ratio, z_score, variation, dow_sin, dow_cos]
    ).astype(np.float32)

def fit_scaler(x: np.ndarray) -> dict:
    return {"mean": x.mean(axis=0).tolist(),
            "std": np.maximum(x.std(axis=0), 1e-6).tolist()}

def apply_scaler(x: np.ndarray, scaler: dict) -> np.ndarray:
    return ((x - np.array(scaler["mean"])) / np.array(scaler["std"])).astype(np.float32)

def save_scaler(scaler: dict, path: str):
    with open(path, "w") as f:
        json.dump(scaler, f)

def load_scaler(path: str) -> dict:
    with open(path) as f:
        return json.load(f)

if __name__ == "__main__":
    df = pd.read_csv("data/train.csv")
    x = build_features(df)
    print("feature matrix shape:", x.shape)
    print("features:", FEATURE_NAMES)
    print("first row:", x[0])