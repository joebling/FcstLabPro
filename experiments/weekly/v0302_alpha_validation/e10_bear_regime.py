#!/usr/bin/env python3
"""
E10: Bear Regime Analysis
=========================
Purpose: Analyze model performance in bear market vs bull market.

Test: Split data by market regime and compare IC
- If bear IC similar to bull: model works in all regimes
- If bear IC different: model may be regime-dependent

Expected:
- Bull regime: IC ~0.35
- Bear regime: May have different IC (smaller sample)

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
print("E10: Bear Regime Analysis")
print("=" * 60)

DATA_PATH = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"
CONFIG_PATH = PROJECT_ROOT / "configs" / "experiments" / "weekly" / "exp_weekly_bull_v27_orion_v4_extended_oos.yaml"
OUTPUT_DIR = Path(__file__).parent


# ============================================================================
# Data Loading
# ============================================================================

with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)

# Load data
print("\nLoading data...")
df = load_csv(str(DATA_PATH))
print(f"Raw data: {len(df)} rows")

# Build features
df = build_features(
    df,
    feature_sets=config['features']['sets'],
    drop_na_method=config['features'].get('drop_na_method', 'ffill_then_drop'),
)

# Generate labels
label_func = get_label_strategy(config['label']['strategy'])
labels = label_func(df, T=config['label']['T'], X=config['label']['X'])

if 'map' in config['label']:
    mapping = {int(k): int(v) for k, v in config['label']['map'].items()}
    labels = labels.map(mapping)

df['label'] = labels
df = df.dropna(subset=['label'])
df['label'] = df['label'].astype(int)

feature_cols = get_feature_columns(df)
X = df[feature_cols].values
y = df['label'].values
dates = df.index.tolist()
close_prices = df['close'].values

print(f"Data: {len(X)} samples")


# ============================================================================
# Define Bear/Bull Regimes
# ============================================================================

# Simple regime definition: use 200-day SMA
sma200 = pd.Series(close_prices).rolling(200).mean()
regimes = pd.Series(index=df.index, dtype=str)

# Bull: price > SMA200, Bear: price < SMA200
regimes[close_prices > sma200.values] = 'bull'
regimes[close_prices <= sma200.values] = 'bear'
regimes = regimes.fillna('unknown')

df['regime'] = regimes

print(f"\nRegime distribution:")
print(df['regime'].value_counts())


# ============================================================================
# Walk-Forward Prediction
# ============================================================================

def run_walk_forward(X, y, dates, regimes, init_train=800, oos_window=63, step=21):
    """Run walk-forward prediction with regime tracking."""
    n_samples = len(X)
    predictions = []
    true_labels = []
    regime_labels = []
    valid_indices = []  # Track original indices

    t = init_train
    while t + oos_window <= n_samples:
        X_train = X[:t]
        y_train = y[:t]
        X_test = X[t:t+oos_window]
        y_test = y[t:t+oos_window]
        regimes_test = regimes[t:t+oos_window]

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
        regime_labels.extend(regimes_test.tolist())
        valid_indices.extend(range(t, t+oos_window))

        t += step

    return np.array(predictions), np.array(true_labels), regime_labels, valid_indices


def calc_regime_ic(predictions, true_labels, regimes, valid_indices, target_regime, step=21):
    """
    Calculate IC for specific regime.

    FIX: First do non-overlapping sampling, then filter by regime.
    This ensures samples are properly spaced in time before regime filtering.
    """
    # First: non-overlapping sampling on original data
    n = len(predictions)
    n_no = n // step
    if n_no < 2:
        return 0.0, 1.0, 0

    # Get non-overlapping indices
    no_indices = list(range(0, n_no * step, step))

    # Filter by regime using non-overlapping samples
    regime_preds = []
    regime_labels = []

    for idx in no_indices:
        if regimes[idx] == target_regime:
            regime_preds.append(predictions[idx])
            regime_labels.append(true_labels[idx])

    if len(regime_preds) < 10:
        return 0.0, 1.0, 0

    if len(set(regime_preds)) < 2 or len(set(regime_labels)) < 2:
        return 0.0, 1.0, len(regime_preds)

    ic, p_val = spearmanr(regime_preds, regime_labels)
    return ic, p_val, len(regime_preds)


# ============================================================================
# Run
# ============================================================================

print("\nRunning walk-forward prediction...")
predictions, true_labels, regime_labels, valid_indices = run_walk_forward(
    X, y, dates, df['regime'].values
)

# Overall IC
step = 21
n = len(predictions)
n_no = n // step
preds_no = predictions[:n_no*step:step]
labels_no = true_labels[:n_no*step:step]
ic_overall, p_overall = spearmanr(preds_no, labels_no)

print(f"\nOverall IC: {ic_overall:.4f}, p={p_overall:.6f}, n={n_no}")

# Bull regime IC (FIX: pass valid_indices)
ic_bull, p_bull, n_bull = calc_regime_ic(predictions, true_labels, regime_labels, valid_indices, 'bull')
print(f"Bull IC: {ic_bull:.4f}, p={p_bull:.6f}, n={n_bull}")

# Bear regime IC (FIX: pass valid_indices)
ic_bear, p_bear, n_bear = calc_regime_ic(predictions, true_labels, regime_labels, valid_indices, 'bear')
print(f"Bear IC: {ic_bear:.4f}, p={p_bear:.6f}, n={n_bear}")


# ============================================================================
# Results
# ============================================================================

print("\n" + "=" * 60)
print("RESULTS SUMMARY")
print("=" * 60)

print(f"\n| Regime | IC | p-value | N (non-overlap) |")
print(f"|--------|-----|---------|-----------------|")
print(f"| Overall | {ic_overall:.4f} | {p_overall:.6f} | {n_no} |")
print(f"| Bull | {ic_bull:.4f} | {p_bull:.6f} | {n_bull} |")
print(f"| Bear | {ic_bear:.4f} | {p_bear:.6f} | {n_bear} |")


# ============================================================================
# Conclusion
# ============================================================================

print("\n" + "=" * 60)
print("CONCLUSION")
print("=" * 60)

# Analyze bear regime
if n_bear < 10:
    conclusion = "INSUFFICIENT DATA - Bear regime has too few samples"
    detail = f"Bear regime only has {n_bear} non-overlap samples"
elif p_bear > 0.05:
    conclusion = "REGIME-DEPENDENT - Model fails in bear market"
    detail = f"Bear IC ({ic_bear:.4f}) not significant (p={p_bear:.4f})"
else:
    # Both significant
    diff = abs(ic_bull - ic_bear)
    if diff < 0.2:
        conclusion = "REGIME-INDEPENDENT - Model works in both markets"
        detail = f"Bull and Bear ICs similar (diff={diff:.4f})"
    else:
        conclusion = "REGIME-DEPENDENT - Model works better in one regime"
        detail = f"Bull IC ({ic_bull:.4f}) vs Bear IC ({ic_bear:.4f}), diff={diff:.4f}"

print(f"\n{conclusion}")
print(f"  {detail}")

# Sample warnings
print(f"\nNote: Bear regime sample size is {n_bear} (vs Bull {n_bull})")
if n_bear < 20:
    print("  WARNING: Bear regime sample size is small, results may be unreliable")


# ============================================================================
# Save Results
# ============================================================================

output_data = {
    'experiment': 'E10 Bear Regime Analysis',
    'overall': {
        'ic': float(ic_overall),
        'p_value': float(p_overall),
        'n_samples': int(n_no),
    },
    'bull': {
        'ic': float(ic_bull),
        'p_value': float(p_bull),
        'n_samples': int(n_bull),
    },
    'bear': {
        'ic': float(ic_bear),
        'p_value': float(p_bear),
        'n_samples': int(n_bear),
    },
    'conclusion': conclusion,
    'detail': detail,
}

with open(OUTPUT_DIR / 'results.json', 'w') as f:
    json.dump(output_data, f, indent=2)

print(f"\nResults saved to {OUTPUT_DIR}/")
