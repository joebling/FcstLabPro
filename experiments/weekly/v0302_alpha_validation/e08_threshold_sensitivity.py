#!/usr/bin/env python3
"""
E08: Threshold Sensitivity Test
================================
Purpose: Test if IC is sensitive to label threshold (X parameter).

Test: Run with different X values (3%, 5%, 8%)
- If IC similar: model robust to threshold
- If IC changes significantly: results depend on threshold choice

Expected:
- X=3%: More extreme labels
- X=5%: Baseline (v4)
- X=8%: Fewer, more extreme labels
- IC should be relatively stable

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
print("E08: Threshold Sensitivity Test")
print("=" * 60)

DATA_PATH = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"
CONFIG_PATH = PROJECT_ROOT / "configs" / "experiments" / "weekly" / "exp_weekly_bull_v27_orion_v4_extended_oos.yaml"
OUTPUT_DIR = Path(__file__).parent


# ============================================================================
# Data Loading
# ============================================================================

with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)

T = config['label']['T']  # Keep T fixed
X_values = [0.03, 0.05, 0.08]  # Test different thresholds

# Load data
print("\nLoading data...")
df = load_csv(str(DATA_PATH))
print(f"Raw data: {len(df)} rows")

# Build features (only once)
print("Building features...")
df = build_features(
    df,
    feature_sets=config['features']['sets'],
    drop_na_method=config['features'].get('drop_na_method', 'ffill_then_drop'),
)

# Get feature columns
feature_cols = get_feature_columns(df)
X_base = df[feature_cols].values
dates = df.index.tolist()

print(f"Features: {len(feature_cols)}")


# ============================================================================
# Walk-Forward Prediction Function
# ============================================================================

def run_walk_forward(X, y, init_train=800, oos_window=63, step=21):
    """Run walk-forward prediction."""
    n_samples = len(X)
    predictions = []
    true_labels = []

    t = init_train
    while t + oos_window <= n_samples:
        X_train = X[:t]
        y_train = y[:t]
        X_test = X[t:t+oos_window]
        y_test = y[t:t+oos_window]

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        model = OrionBixClassifier(
            n_estimators=4,
            random_state=42,
        )
        model.fit(X_train_scaled, y_train)

        if len(model.classes_) == 2:
            preds = model.predict_proba(X_test_scaled)[:, 1]
        else:
            preds = np.zeros(len(X_test))

        predictions.extend(preds)
        true_labels.extend(y_test)
        t += step

    return np.array(predictions), np.array(true_labels)


def calc_non_overlap_ic(predictions, labels, step=21):
    """Calculate non-overlapping IC."""
    n = len(predictions)
    n_no = n // step
    if n_no < 2:
        return 0.0, 1.0, 0, 0
    preds_no = predictions[:n_no*step:step]
    labels_no = labels[:n_no*step:step]
    if len(set(preds_no)) < 2 or len(set(labels_no)) < 2:
        return 0.0, 1.0, n_no, 0
    ic, p_val = spearmanr(preds_no, labels_no)
    return ic, p_val, n_no, len(labels_no)


# ============================================================================
# Run for different X values
# ============================================================================

results = []

for X in X_values:
    print(f"\n--- Testing X = {X*100:.0f}% ---")

    # Generate labels with different X
    label_func = get_label_strategy(config['label']['strategy'])
    labels = label_func(df, T=T, X=X)

    # Apply mapping for binary classification
    if 'map' in config['label']:
        mapping = {int(k): int(v) for k, v in config['label']['map'].items()}
        labels = labels.map(mapping)

    df_test = df.copy()
    df_test['label'] = labels
    df_test = df_test.dropna(subset=['label'])
    df_test['label'] = df_test['label'].astype(int)

    X_test = df_test[feature_cols].values
    y_test = df_test['label'].values

    print(f"  Samples: {len(X_test)}, Label dist: {np.bincount(y_test)}")

    # Run walk-forward
    preds, labels_test = run_walk_forward(X_test, y_test)
    ic, p_val, n_samples, label_1_pct = calc_non_overlap_ic(preds, labels_test, step=config['evaluation']['step'])

    print(f"  IC: {ic:.4f}, p={p_val:.6f}, n={n_samples}")

    results.append({
        'X': X,
        'X_pct': X * 100,
        'ic': ic,
        'p_value': p_val,
        'n_samples': n_samples,
        'label_1_pct': label_1_pct / n_samples if n_samples > 0 else 0,
    })


# ============================================================================
# Results
# ============================================================================

print("\n" + "=" * 60)
print("RESULTS SUMMARY")
print("=" * 60)

print(f"\n| X (%) | IC | p-value | N | Label=1 % |")
print(f"|-------|-----|---------|---|-----------|")

for r in results:
    print(f"| {r['X_pct']:>5.0f} | {r['ic']:.4f} | {r['p_value']:.6f} | {r['n_samples']} | {r['label_1_pct']*100:>8.1f}% |")


# ============================================================================
# Conclusion
# ============================================================================

print("\n" + "=" * 60)
print("CONCLUSION")
print("=" * 60)

ics = [r['ic'] for r in results]
ic_std = np.std(ics)
ic_range = max(ics) - min(ics)

print(f"\nIC range: {min(ics):.4f} to {max(ics):.4f}")
print(f"IC std: {ic_std:.4f}")
print(f"IC range: {ic_range:.4f}")

# Check stability
if ic_std < 0.1 and ic_range < 0.15:
    conclusion = "ROBUST - IC stable across thresholds"
    detail = f"IC std ({ic_std:.4f}) < 0.1, model robust to threshold choice"
elif ic_std < 0.2:
    conclusion = "MARGINAL - IC somewhat sensitive to threshold"
    detail = f"IC std ({ic_std:.4f}) in 0.1-0.2 range"
else:
    conclusion = "SENSITIVE - IC depends heavily on threshold"
    detail = f"IC std ({ic_std:.4f}) > 0.2, threshold choice matters"

print(f"\n{conclusion}")
print(f"  {detail}")


# ============================================================================
# Save Results
# ============================================================================

output_data = {
    'experiment': 'E08 Threshold Sensitivity Test',
    'results': results,
    'ic_std': float(ic_std),
    'ic_range': float(ic_range),
    'conclusion': conclusion,
    'detail': detail,
}

with open(OUTPUT_DIR / 'results.json', 'w') as f:
    json.dump(output_data, f, indent=2, default=str)

print(f"\nResults saved to {OUTPUT_DIR}/")
