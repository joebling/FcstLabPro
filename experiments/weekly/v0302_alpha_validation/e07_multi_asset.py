#!/usr/bin/env python3
"""
E07: Multi-Asset Validation Test (ETH)
======================================
Purpose: Test if model generalizes to other assets.

Test: Run same model on ETHUSDT
- If IC similar: model has real alpha
- If IC near zero: alpha is BTC-specific

Expected:
- BTC IC: ~0.35
- ETH IC: Should be positive if model generalizes

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
print("E07: Multi-Asset Validation Test (ETH)")
print("=" * 60)

DATA_PATH_BTC = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"
DATA_PATH_ETH = PROJECT_ROOT / "data" / "raw" / "eth_binance_ETHUSDT_1d.csv"
CONFIG_PATH = PROJECT_ROOT / "configs" / "experiments" / "weekly" / "exp_weekly_bull_v27_orion_v4_extended_oos.yaml"
OUTPUT_DIR = Path(__file__).parent


# ============================================================================
# Load BTC Data (Baseline)
# ============================================================================

with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)

print("\n--- Loading BTC Data (Baseline) ---")
df_btc = load_csv(str(DATA_PATH_BTC))

df_btc = build_features(
    df_btc,
    feature_sets=config['features']['sets'],
    drop_na_method=config['features'].get('drop_na_method', 'ffill_then_drop'),
)

label_func = get_label_strategy(config['label']['strategy'])
labels_btc = label_func(df_btc, T=config['label']['T'], X=config['label']['X'])

if 'map' in config['label']:
    mapping = {int(k): int(v) for k, v in config['label']['map'].items()}
    labels_btc = labels_btc.map(mapping)

df_btc['label'] = labels_btc
df_btc = df_btc.dropna(subset=['label'])
df_btc['label'] = df_btc['label'].astype(int)

feature_cols = get_feature_columns(df_btc)
X_btc = df_btc[feature_cols].values
y_btc = df_btc['label'].values

print(f"BTC: {len(X_btc)} samples, {len(feature_cols)} features")


# ============================================================================
# Load ETH Data
# ============================================================================

print("\n--- Loading ETH Data ---")

# Check if ETH data exists
if not DATA_PATH_ETH.exists():
    # Try alternative path
    DATA_PATH_ETH = PROJECT_ROOT / "data" / "raw" / "eth_binance_ETHUSDT_1d.csv"
    if not DATA_PATH_ETH.exists():
        print(f"ETH data not found at {DATA_PATH_ETH}")
        print("Searching for ETH data...")

        # Search for ETH data files
        eth_files = list(PROJECT_ROOT.glob("data/**/*ETH*.csv"))
        if eth_files:
            print(f"Found: {eth_files}")
            DATA_PATH_ETH = eth_files[0]
        else:
            print("ETH data not found. Creating placeholder result.")
            output_data = {
                'experiment': 'E07 Multi-Asset Validation',
                'status': 'SKIPPED',
                'reason': 'ETH data not found',
                'btc_ic': None,
                'eth_ic': None,
            }
            with open(OUTPUT_DIR / 'results.json', 'w') as f:
                json.dump(output_data, f, indent=2)
            print(f"Results saved to {OUTPUT_DIR}/")
            sys.exit(0)

print(f"Loading ETH from: {DATA_PATH_ETH}")

try:
    df_eth = load_csv(str(DATA_PATH_ETH))
    print(f"ETH raw data: {len(df_eth)} rows")

    df_eth = build_features(
        df_eth,
        feature_sets=config['features']['sets'],
        drop_na_method=config['features'].get('drop_na_method', 'ffill_then_drop'),
    )

    labels_eth = label_func(df_eth, T=config['label']['T'], X=config['label']['X'])

    if 'map' in config['label']:
        labels_eth = labels_eth.map(mapping)

    df_eth['label'] = labels_eth
    df_eth = df_eth.dropna(subset=['label'])
    df_eth['label'] = df_eth['label'].astype(int)

    X_eth = df_eth[feature_cols].values
    y_eth = df_eth['label'].values

    print(f"ETH: {len(X_eth)} samples")

except Exception as e:
    print(f"Error loading ETH data: {e}")
    output_data = {
        'experiment': 'E07 Multi-Asset Validation',
        'status': 'ERROR',
        'error': str(e),
    }
    with open(OUTPUT_DIR / 'results.json', 'w') as f:
        json.dump(output_data, f, indent=2)
    sys.exit(0)


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
        return 0.0, 1.0, 0
    preds_no = predictions[:n_no*step:step]
    labels_no = labels[:n_no*step:step]
    if len(set(preds_no)) < 2 or len(set(labels_no)) < 2:
        return 0.0, 1.0, n_no
    ic, p_val = spearmanr(preds_no, labels_no)
    return ic, p_val, n_no


# ============================================================================
# Run BTC
# ============================================================================

print("\n--- Running BTC Walk-Forward ---")
preds_btc, labels_btc_test = run_walk_forward(X_btc, y_btc)
ic_btc, p_btc, n_btc = calc_non_overlap_ic(preds_btc, labels_btc_test, step=config['evaluation']['step'])

print(f"BTC IC: {ic_btc:.4f}, p={p_btc:.6f}, n={n_btc}")


# ============================================================================
# Run ETH
# ============================================================================

print("\n--- Running ETH Walk-Forward ---")
preds_eth, labels_eth_test = run_walk_forward(X_eth, y_eth)
ic_eth, p_eth, n_eth = calc_non_overlap_ic(preds_eth, labels_eth_test, step=config['evaluation']['step'])

print(f"ETH IC: {ic_eth:.4f}, p={p_eth:.6f}, n={n_eth}")


# ============================================================================
# Results
# ============================================================================

print("\n" + "=" * 60)
print("RESULTS SUMMARY")
print("=" * 60)

print(f"\n| Asset | IC | p-value | N samples | Significant |")
print(f"|-------|-----|---------|-----------|------------|")
print(f"| BTC   | {ic_btc:.4f} | {p_btc:.6f} | {n_btc} | {'YES' if p_btc < 0.05 else 'NO'} |")
print(f"| ETH   | {ic_eth:.4f} | {p_eth:.6f} | {n_eth} | {'YES' if p_eth < 0.05 else 'NO'} |")


# ============================================================================
# Conclusion
# ============================================================================

print("\n" + "=" * 60)
print("CONCLUSION")
print("=" * 60)

if ic_eth > 0.05 and p_eth < 0.05:
    conclusion = "GENERALIZES - Model works on ETH"
    detail = f"ETH IC ({ic_eth:.4f}) significant, model generalizes to other assets"
elif ic_eth > 0:
    conclusion = "PARTIAL - Model has limited generalization"
    detail = f"ETH IC ({ic_eth:.4f}) positive but not significant"
else:
    conclusion = "BTC-SPECIFIC - Model does not generalize"
    detail = f"ETH IC ({ic_eth:.4f}) negative, alpha is BTC-specific"

print(f"\n{conclusion}")
print(f"  {detail}")

print(f"\nGeneralization:")
print(f"  BTC -> ETH IC drop: {ic_btc:.4f} - {ic_eth:.4f} = {ic_btc - ic_eth:.4f}")


# ============================================================================
# Save Results
# ============================================================================

output_data = {
    'experiment': 'E07 Multi-Asset Validation',
    'status': 'COMPLETE',
    'btc': {
        'ic': float(ic_btc),
        'p_value': float(p_btc),
        'n_samples': int(n_btc),
    },
    'eth': {
        'ic': float(ic_eth),
        'p_value': float(p_eth),
        'n_samples': int(n_eth),
    },
    'ic_drop': float(ic_btc - ic_eth),
    'conclusion': conclusion,
    'detail': detail,
}

with open(OUTPUT_DIR / 'results.json', 'w') as f:
    json.dump(output_data, f, indent=2)

print(f"\nResults saved to {OUTPUT_DIR}/")
