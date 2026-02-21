#!/usr/bin/env python3
"""
E02: Continuous IC Test
=======================
Purpose: Distinguish between "crash timing" vs "continuous alpha".

Test: Calculate IC using continuous future returns (not binary labels).
- If continuous IC >> binary IC: model is crash timing only
- If continuous IC ~ binary IC: model has real sorting ability

Expected:
- Binary IC: ~0.65 (v4 result with binary labels)
- Continuous IC: Should be much lower if model only predicts "crash vs no crash"

Author: FcstLabPro
Date: 2026-02-20
"""

import sys
from pathlib import Path

# Add project root to path
for p in [Path.cwd(), Path(__file__).resolve().parent]:
    PROJECT_ROOT = p
    if (PROJECT_ROOT / "src").exists():
        sys.path.insert(0, str(PROJECT_ROOT))
        break
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import yaml
import json
from scipy.stats import spearmanr
from sklearn.preprocessing import StandardScaler
from orion_bix import OrionBixClassifier
import warnings
warnings.filterwarnings('ignore')

from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns
import src.labels.reversal
from src.labels.registry import get_label_strategy


# ============================================================================
# Configuration
# ============================================================================

print("=" * 60)
print("E02: Continuous IC Test")
print("=" * 60)

DATA_PATH = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"
CONFIG_PATH = PROJECT_ROOT / "configs" / "experiments" / "weekly" / "exp_weekly_bull_v27_orion_v4_extended_oos.yaml"
OUTPUT_DIR = Path(__file__).parent


# ============================================================================
# Data Loading
# ============================================================================

with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)

print(f"\nConfig: {config['experiment']['name']}")
print(f"Label: T={config['label']['T']}, X={config['label']['X']}")

# Load data
print("\nLoading data...")
df = load_csv(str(DATA_PATH))
print(f"Raw data: {len(df)} rows")

# Build features
print("Building features...")
df = build_features(
    df,
    feature_sets=config['features']['sets'],
    drop_na_method=config['features'].get('drop_na_method', 'ffill_then_drop'),
)

# Generate labels
label_func = get_label_strategy(config['label']['strategy'])
labels = label_func(df, T=config['label']['T'], X=config['label']['X'])

# Apply label mapping
if 'map' in config['label']:
    mapping = {int(k): int(v) for k, v in config['label']['map'].items()}
    labels = labels.map(mapping)

df['label'] = labels
df = df.dropna(subset=['label'])
df['label'] = df['label'].astype(int)

# Get features
feature_cols = get_feature_columns(df)
X = df[feature_cols].values
y = df['label'].values
dates = df.index.tolist()
close_prices = df['close'].values

print(f"Data: {len(X)} samples, {len(feature_cols)} features")
print(f"Label distribution: {np.bincount(y)}")


# ============================================================================
# Generate Continuous Future Returns
# ============================================================================

T = config['label']['T']
step = config['evaluation']['step']

# Calculate future returns (T days ahead)
future_returns = []
return_dates = []

for i in range(len(close_prices) - T):
    ret = (close_prices[i+T] - close_prices[i]) / close_prices[i]
    future_returns.append(ret)
    return_dates.append(dates[i])

future_returns = np.array(future_returns)
print(f"\nFuture returns: {len(future_returns)} samples")
print(f"Return stats: mean={future_returns.mean():.4f}, std={future_returns.std():.4f}")


# ============================================================================
# Walk-Forward Prediction
# ============================================================================

def run_walk_forward(X, y, init_train=800, oos_window=63, step=21):
    """Run walk-forward prediction."""
    n_samples = len(X)
    predictions = []
    true_labels = []
    valid_indices = []

    t = init_train
    while t + oos_window <= n_samples:
        X_train = X[:t]
        y_train = y[:t]

        X_test = X[t:t+oos_window]
        y_test = y[t:t+oos_window]

        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Train model
        model = OrionBixClassifier(
            n_estimators=4,
            random_state=42,
        )
        model.fit(X_train_scaled, y_train)

        # Predict
        if len(model.classes_) == 2:
            preds = model.predict_proba(X_test_scaled)[:, 1]
        else:
            preds = np.zeros(len(X_test))

        predictions.extend(preds)
        true_labels.extend(y_test)
        valid_indices.extend(range(t, t+oos_window))

        t += step

    return np.array(predictions), np.array(true_labels), np.array(valid_indices)


# ============================================================================
# Run Prediction
# ============================================================================

print("\n" + "=" * 60)
print("Running walk-forward prediction...")
print("=" * 60)

predictions, true_labels, valid_idx = run_walk_forward(X, y)

# Get corresponding future returns
# valid_idx are the START indices of each OOS period
# We need to align predictions with returns

# For each prediction, get the future return
aligned_returns = []
for idx in valid_idx:
    if idx + T < len(close_prices):
        # Correct: return from prediction point (idx) to T days later (idx+T)
        ret = (close_prices[idx + T] - close_prices[idx]) / close_prices[idx]
        aligned_returns.append(ret)
    else:
        aligned_returns.append(0)

aligned_returns = np.array(aligned_returns)

print(f"Predictions: {len(predictions)}")
print(f"Aligned returns: {len(aligned_returns)}")


# ============================================================================
# Calculate ICs
# ============================================================================

print("\n" + "=" * 60)
print("Calculating ICs...")
print("=" * 60)

# 1. Binary IC (using labels as binary)
binary_ic, binary_p = spearmanr(predictions, true_labels)

# 2. Continuous IC (using actual returns)
continuous_ic, continuous_p = spearmanr(predictions, aligned_returns)

# 3. Non-overlapping IC (step=21)
n = len(predictions)
n_no = n // step
preds_no = predictions[:n_no*step:step]
rets_no = aligned_returns[:n_no*step:step]
labels_no = true_labels[:n_no*step:step]

if len(set(preds_no)) > 1 and len(set(rets_no)) > 1:
    no_ic, no_p = spearmanr(preds_no, rets_no)
else:
    no_ic, no_p = 0.0, 1.0


# ============================================================================
# Results
# ============================================================================

print("\n" + "=" * 60)
print("RESULTS")
print("=" * 60)

print(f"\n1. Binary Classification IC:")
print(f"   IC: {binary_ic:.4f}")
print(f"   p-value: {binary_p:.6f}")

print(f"\n2. Continuous Return IC:")
print(f"   IC: {continuous_ic:.4f}")
print(f"   p-value: {continuous_p:.6f}")

print(f"\n3. Non-overlapping Continuous IC (step={step}):")
print(f"   IC: {no_ic:.4f}")
print(f"   p-value: {no_p:.6f}")

print(f"\nComparison:")
print(f"   Binary IC:     {binary_ic:.4f}")
print(f"   Continuous IC:  {continuous_ic:.4f}")
print(f"   Difference:    {binary_ic - continuous_ic:.4f}")


# ============================================================================
# Conclusion
# ============================================================================

print("\n" + "=" * 60)
print("CONCLUSION")
print("=" * 60)

if continuous_ic < 0.05:
    conclusion = "WEAK - Model mainly does crash timing, not continuous alpha"
    detail = "Continuous IC is very low, suggesting model only predicts binary events"
elif continuous_ic < 0.10:
    conclusion = "MARGINAL - Some continuous alpha, but mainly crash timing"
    detail = "Continuous IC is moderate, model has some sorting ability"
else:
    conclusion = "STRONG - Model has real continuous alpha"
    detail = "Continuous IC is high, model predicts beyond binary events"

print(f"\n{conclusion}")
print(f"  {detail}")


# ============================================================================
# Save Results
# ============================================================================

output_data = {
    'experiment': 'E02 Continuous IC Test',
    'binary_ic': float(binary_ic),
    'binary_p_value': float(binary_p),
    'continuous_ic': float(continuous_ic),
    'continuous_p_value': float(continuous_p),
    'non_overlap_ic': float(no_ic),
    'non_overlap_p_value': float(no_p),
    'ic_difference': float(binary_ic - continuous_ic),
    'conclusion': conclusion,
    'detail': detail,
}

with open(OUTPUT_DIR / 'results.json', 'w') as f:
    json.dump(output_data, f, indent=2, default=str)

print(f"\nResults saved to {OUTPUT_DIR}/")
