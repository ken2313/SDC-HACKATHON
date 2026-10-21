import os
import numpy as np
import pandas as pd

# name: (daily mean, std, weekend multiplier)
PRODUCTS = {
    "Fresh Milk (carton)": (10, 2.0, 1.3),
    "Coffee Beans (kg)": (4, 0.8, 1.2),
    "Sugar (kg)": (3, 0.6, 1.1),
    "Paper Cups (sleeve)": (6, 1.2, 1.3),
    "Croissants (pcs)": (25, 5.0, 1.4),
}

def generate(days=120, seed=42):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-06-01", periods=days)
    rows = []
    for name, (mean, std, weekend) in PRODUCTS.items():
        mult = np.where(dates.dayofweek >= 5, weekend, 1.0)
        qty = np.maximum(0, np.round(rng.normal(mean * mult, std)))
        df = pd.DataFrame({"product": name, "date": dates,
                           "day_of_week": dates.dayofweek,
                           "movement_type": "OUT", "quantity": qty})
        # history = previous 7 days only (excludes today)
        hist = df["quantity"].shift(1).rolling(7)
        df["recent_avg"] = hist.mean()
        df["usage_std"] = hist.std()
        rows.append(df.dropna())  # first 7 days = insufficient history
    return pd.concat(rows, ignore_index=True)

def inject_anomalies(df, fraction=0.08, seed=7):
    rng = np.random.default_rng(seed)
    df = df.copy()
    df["is_anomaly"] = 0
    idx = rng.choice(df.index, int(len(df) * fraction), replace=False)
    for i in idx:
        if rng.random() < 0.8:  # big spike
            df.loc[i, "quantity"] = round(df.loc[i, "recent_avg"] * rng.uniform(3, 5))
        else:                   # suspiciously low
            df.loc[i, "quantity"] = 0
        df.loc[i, "is_anomaly"] = 1
    return df

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    data = generate()
    cutoff = data["date"].sort_values().iloc[int(len(data) * 0.75)]
    train = data[data["date"] < cutoff].assign(is_anomaly=0)
    test = inject_anomalies(data[data["date"] >= cutoff])
    train.to_csv("data/train.csv", index=False)
    test.to_csv("data/test.csv", index=False)
    print("train rows:", len(train), "| test rows:", len(test),
          "| test anomalies:", int(test["is_anomaly"].sum()))