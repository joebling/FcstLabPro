#!/usr/bin/env python3
"""
E04: Init Train Sensitivity Test
================================
Purpose: Test if reducing init_train artificially inflates t-stat.

Test: Run with different init_train values and compare IC/t-stat
- If IC stable as init_train changes: t-stat inflation not from sample size
- If IC changes significantly: sample size affects results

Expected:
- init_train=1500: Lower t-stat (more training, less test samples)
- init_train=800: Higher t-stat (less training, more test samples)
- If IC remains similar: results are robust

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
from scipy.stats import spearmanr, ttest_1samp
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
print("E04: Init Train Sensitivity Test")
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

print(f"Data: {len(X)} samples, {len(feature_cols)} features")
print(f"Label distribution: {np.bincount(y)}")


# ============================================================================
# Walk-Forward Prediction with different init_train
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


def calc_non_overlap_ic(predictions, true_labels, step=21):
    """Calculate non-overlapping IC."""
    n = len(predictions)
    n_no = n // step

    if n_no < 2:
        return 0.0, 1.0, 0

    preds_no = predictions[:n_no*step:step]
    labels_no = true_labels[:n_no*step:step]

    if len(set(preds_no)) < 2 or len(set(labels_no)) < 2:
        return 0.0, 1.0, n_no

    ic, p_val = spearmanr(preds_no, labels_no)
    return ic, p_val, n_no


# ============================================================================
# Run with different init_train values
# ============================================================================

init_train_values = [1500, 1200, 1000, 800, 600]
step = config['evaluation']['step']
oos_window = config['evaluation']['oos_window']

results = []

print("\n" + "=" * 60)
print("Running sensitivity tests...")
print("=" * 60)

for init_train in init_train_values:
    print(f"\n--- init_train = {init_train} ---")

    predictions, true_labels, valid_idx = run_walk_forward(
        X, y, init_train=init_train, oos_window=oos_window, step=step
    )

    ic, p_val, n_samples = calc_non_overlap_ic(predictions, true_labels, step)

    # Calculate t-stat from IC
    # IC = correlation, need to transform for t-test
    # Using Fisher z-transform
    if abs(ic) < 1:
        z = 0.5 * np.log((1 + ic) / (1 - ic))
        se = 1 / np.sqrt(n_samples - 3)
        t_stat = z / se
    else:
        t_stat = 0

    results.append({
        'init_train': init_train,
        'n_train': init_train,
        'n_oos_samples': len(predictions),
        'n_non_overlap': n_samples,
        'ic': ic,
        'p_value': p_val,
        't_stat': t_stat,
    })

    print(f"  OOS samples: {len(predictions)}")
    print(f"  Non-overlap samples: {n_samples}")
    print(f"  IC: {ic:.4f}")
    print(f"  p-value: {p_val:.6f}")
    print(f"  t-stat: {t_stat:.4f}")


# ============================================================================
# Results Summary
# ============================================================================

print("\n" + "=" * 60)
print("RESULTS SUMMARY")
print("=" * 60)

print(f"\n| init_train | OOS samples | Non-overlap | IC | p-value | t-stat |")
print(f"|------------|-------------|-------------|-----|---------|--------|")

for r in results:
    print(f"| {r['init_train']:>10} | {r['n_oos_samples']:>11} | {r['n_non_overlap']:>10} | {r['ic']:.4f} | {r['p_value']:.6f} | {r['t_stat']:>6.2f} |")


# ============================================================================
# Analysis
# ============================================================================

print("\n" + "=" * 60)
print("ANALYSIS")
print("=" * 60)

# Extract IC and t-stat values
ics = [r['ic'] for r in results]
t_stats = [r['t_stat'] for r in results]

print(f"\nIC range: {min(ics):.4f} to {max(ics):.4f}")
print(f"IC std: {np.std(ics):.4f}")

print(f"\nt-stat range: {min(t_stats):.2f} to {max(t_stats):.2f}")

# Check if t-stat changes are due to sample size
print("\n--- Interpretation ---")

# Compare extreme values
ic_at_1500 = results[0]['ic']
ic_at_800 = results[3]['ic']
t_at_1500 = results[0]['t_stat']
t_at_800 = results[3]['t_stat']

print(f"\ninit_train=1500 vs init_train=800:")
print(f"  IC change: {ic_at_1500:.4f} -> {ic_at_800:.4f} (diff: {ic_at_800 - ic_at_1500:.4f})")
print(f"  t-stat change: {t_at_1500:.2f} -> {t_at_800:.2f}")

# Conclusion
ic_variance = np.var(ics)
if ic_variance < 0.01:
    conclusion = "ROBUST - IC stable across init_train values"
    detail = f"IC variance = {ic_variance:.6f}, results not artificially inflated"
else:
    conclusion = "UNSTABLE - IC varies significantly with init_train"
    detail = f"IC variance = {ic_variance:.6f}, sample size may affect results"

# Check if t-stat increases as init_train decreases
if t_stats[-1] > t_stats[0] * 1.5:
    detail += " - WARNING: t-stat increases as init_train decreases"
    conclusion += " (SUSPICIOUS)"

print(f"\n{conclusion}")
print(f"  {detail}")


# ============================================================================
# Save Results
# ============================================================================

output_data = {
    'experiment': 'E04 Init Train Sensitivity Test',
    'results': results,
    'conclusion': conclusion,
    'detail': detail,
    'ic_variance': float(ic_variance),
}

with open(OUTPUT_DIR / 'results.json', 'w') as f:
    json.dump(output_data, f, indent=2, default=str)

print(f"\nResults saved to {OUTPUT_DIR}/")
