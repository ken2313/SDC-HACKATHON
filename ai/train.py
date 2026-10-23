import json
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

from features import build_features, fit_scaler, apply_scaler, save_scaler
from model import Autoencoder, reconstruction_error

SEED = 42
EPOCHS = 400
LEARNING_RATE = 5e-3
UNUSUAL_PERCENTILE = 95        # "Unusual" = above 95% of normal validation rows
HIGHLY_UNUSUAL_PERCENTILE = 99 # "Highly Unusual" = above 99% of normal validation rows

torch.manual_seed(SEED)
np.random.seed(SEED)
device = "cuda" if torch.cuda.is_available() else "cpu"

def auc(scores, labels):
    """Probability that a random anomaly scores higher than a random normal row."""
    ranks = pd.Series(scores).rank().to_numpy()
    pos = labels == 1
    n_pos, n_neg = pos.sum(), (~pos).sum()
    return (ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)

def report(name, scores, labels, threshold):
    flagged = scores >= threshold
    tp = int((flagged & (labels == 1)).sum())
    fp = int((flagged & (labels == 0)).sum())
    fn = int((~flagged & (labels == 1)).sum())
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    result = {"auc": round(float(auc(scores, labels)), 3),
              "precision": round(precision, 3), "recall": round(recall, 3),
              "flagged": int(flagged.sum()), "false_alarms": fp, "missed": fn}
    print(f"{name:14s}", result)
    return result

# ---------- 1. Load data and split normal training data ----------
train_df = pd.read_csv("data/train.csv")
test_df = pd.read_csv("data/test.csv")

order = np.random.permutation(len(train_df))
cut = int(len(order) * 0.8)
fit_df = train_df.iloc[order[:cut]]
val_df = train_df.iloc[order[cut:]]   # normal rows used ONLY to choose thresholds

x_fit_raw = build_features(fit_df)
scaler = fit_scaler(x_fit_raw)        # scaler learns from training rows only
x_fit = torch.tensor(apply_scaler(x_fit_raw, scaler)).to(device)
x_val = torch.tensor(apply_scaler(build_features(val_df), scaler)).to(device)
x_test = torch.tensor(apply_scaler(build_features(test_df), scaler)).to(device)
y_test = test_df["is_anomaly"].to_numpy()

# ---------- 2. Train the autoencoder (normal data only) ----------
model = Autoencoder(n_features=x_fit.shape[1]).to(device)
optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)
loss_fn = nn.MSELoss()

for epoch in range(1, EPOCHS + 1):
    model.train()
    optimizer.zero_grad()
    loss = loss_fn(model(x_fit), x_fit)
    loss.backward()
    optimizer.step()
    if epoch % 100 == 0:
        print(f"epoch {epoch}: training loss {loss.item():.4f}")

# ---------- 3. Choose thresholds from NORMAL validation rows ----------
val_scores = reconstruction_error(model, x_val)[0].cpu().numpy()
ae_unusual = float(np.percentile(val_scores, UNUSUAL_PERCENTILE))
ae_highly = float(np.percentile(val_scores, HIGHLY_UNUSUAL_PERCENTILE))

# ---------- 4. Baseline: plain z-score ----------
def zscore(df):
    return (np.abs(df["quantity"] - df["recent_avg"]) /
            np.maximum(df["usage_std"], 0.5)).to_numpy()

z_unusual = float(np.percentile(zscore(val_df), UNUSUAL_PERCENTILE))

# ---------- 5. Compare on the test set ----------
test_scores = reconstruction_error(model, x_test)[0].cpu().numpy()
print("\nTest set:", len(test_df), "rows,", int(y_test.sum()), "injected anomalies")
ae_result = report("autoencoder", test_scores, y_test, ae_unusual)
z_result = report("z-score", zscore(test_df), y_test, z_unusual)

# ---------- 6. Save everything the inference service needs ----------
torch.save(model.state_dict(), "model.pt")
save_scaler(scaler, "scaler.json")
config = {
    "model_version": "autoencoder-v1",
    "seed": SEED,
    "threshold_method": f"percentiles {UNUSUAL_PERCENTILE}/{HIGHLY_UNUSUAL_PERCENTILE} "
                        "of reconstruction error on held-out normal rows",
    "unusual_threshold": ae_unusual,
    "highly_unusual_threshold": ae_highly,
    "test_metrics": {"autoencoder": ae_result, "zscore_baseline": z_result},
}
with open("config.json", "w") as f:
    json.dump(config, f, indent=2)
print("\nSaved model.pt, scaler.json, config.json")
print("Thresholds: unusual =", round(ae_unusual, 4), "| highly unusual =", round(ae_highly, 4))