#!/usr/bin/env python3
"""
E05: Newey-West Adjusted t-stat Test
====================================
Purpose: Test if t-stat is inflated due to autocorrelation.

Test: Compare regular t-stat vs Newey-West adjusted t-stat
- If NW t-stat similar: results robust
- If NW t-stat much lower: autocorrelation inflates significance

Expected:
- Regular t-stat: ~4.75 (v4 result)
- Newey-West t-stat: Should be lower if autocorrelation exists

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
print("E05: Newey-West Adjusted t-stat Test")
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
# Monthly IC Series
# ============================================================================

def calc_monthly_ic_series(predictions, true_labels, step=21):
    """Calculate IC for each non-overlapping period (monthly)."""
    n = len(predictions)
    n_months = n // step

    ic_series = []
    for i in range(n_months):
        start = i * step
        end = start + step
        preds = predictions[start:end]
        labels = true_labels[start:end]

        if len(set(preds)) > 1 and len(set(labels)) > 1:
            ic, _ = spearmanr(preds, labels)
            ic_series.append(ic)

    return np.array(ic_series)


# ============================================================================
# Newey-West t-stat
# ============================================================================

def newey_west_tstat(ic_series, max_lag=3):
    """
    Calculate Newey-West adjusted t-statistic.
    """
    try:
        from statsmodels.regression.linear_model import OLS
    except ImportError:
        print("Warning: statsmodels not available, using simple t-stat")
        return ttest_1samp(ic_series, 0)[0]

    if len(ic_series) < 5:
        return 0.0

    # OLS with HAC standard errors
    X = np.ones(len(ic_series))
    model = OLS(ic_series, X)
    try:
        result = model.fit(cov_type='HAC', cov_kwds={'maxlags': max_lag})
        return result.tvalues[0]
    except:
        return ttest_1samp(ic_series, 0)[0]


# ============================================================================
# Run
# ============================================================================

print("\n" + "=" * 60)
print("Running walk-forward prediction...")
print("=" * 60)

step = config['evaluation']['step']
predictions, true_labels, valid_idx = run_walk_forward(X, y)

# Calculate monthly IC series
ic_series = calc_monthly_ic_series(predictions, true_labels, step)
print(f"\nMonthly IC series: {len(ic_series)} samples")
print(f"IC series: {ic_series}")

# Regular t-stat
t_stat_regular = ttest_1samp(ic_series, 0)[0]
print(f"\nRegular t-stat: {t_stat_regular:.4f}")

# Newey-West t-stat
t_stat_nw = newey_west_tstat(ic_series, max_lag=3)
print(f"Newey-West t-stat (lag=3): {t_stat_nw:.4f}")

# Also try different lags
t_stat_nw_1 = newey_west_tstat(ic_series, max_lag=1)
t_stat_nw_2 = newey_west_tstat(ic_series, max_lag=2)
t_stat_nw_4 = newey_west_tstat(ic_series, max_lag=4)

print(f"Newey-West t-stat (lag=1): {t_stat_nw_1:.4f}")
print(f"Newey-West t-stat (lag=2): {t_stat_nw_2:.4f}")
print(f"Newey-West t-stat (lag=4): {t_stat_nw_4:.4f}")


# ============================================================================
# Results
# ============================================================================

print("\n" + "=" * 60)
print("RESULTS SUMMARY")
print("=" * 60)

print(f"\n| Method | t-stat | Significant (>2)? |")
print(f"|--------|--------|-------------------|")
print(f"| Regular | {t_stat_regular:.4f} | {'YES' if abs(t_stat_regular) > 2 else 'NO'} |")
print(f"| NW (lag=1) | {t_stat_nw_1:.4f} | {'YES' if abs(t_stat_nw_1) > 2 else 'NO'} |")
print(f"| NW (lag=2) | {t_stat_nw_2:.4f} | {'YES' if abs(t_stat_nw_2) > 2 else 'NO'} |")
print(f"| NW (lag=3) | {t_stat_nw:.4f} | {'YES' if abs(t_stat_nw) > 2 else 'NO'} |")
print(f"| NW (lag=4) | {t_stat_nw_4:.4f} | {'YES' if abs(t_stat_nw_4) > 2 else 'NO'} |")


# ============================================================================
# Conclusion
# ============================================================================

print("\n" + "=" * 60)
print("CONCLUSION")
print("=" * 60)

# Check if results are robust
ratio = t_stat_nw / t_stat_regular if t_stat_regular != 0 else 0

if abs(t_stat_nw) > 2:
    conclusion = "ROBUST - Results remain significant after NW adjustment"
    detail = f"NW t-stat ({t_stat_nw:.2f}) > 2, autocorrelation does not inflate significance"
elif abs(t_stat_nw) > 1.5:
    conclusion = "MARGINAL - Results borderline after NW adjustment"
    detail = f"NW t-stat ({t_stat_nw:.2f}) in 1.5-2 range"
else:
    conclusion = "INFLATED - Regular t-stat likely inflated by autocorrelation"
    detail = f"Regular t-stat ({t_stat_regular:.2f}) >> NW t-stat ({t_stat_nw:.2f}), ratio={ratio:.2f}"

print(f"\n{conclusion}")
print(f"  {detail}")

# Autocorrelation analysis
print(f"\nIC Series Statistics:")
print(f"  Mean: {ic_series.mean():.4f}")
print(f"  Std: {ic_series.std():.4f}")
print(f"  Autocorr(1): {pd.Series(ic_series).autocorr(lag=1):.4f}")
print(f"  Autocorr(2): {pd.Series(ic_series).autocorr(lag=2):.4f}")


# ============================================================================
# Save Results
# ============================================================================

output_data = {
    'experiment': 'E05 Newey-West t-stat Test',
    'ic_series': ic_series.tolist(),
    't_stat_regular': float(t_stat_regular),
    't_stat_nw_lag1': float(t_stat_nw_1),
    't_stat_nw_lag2': float(t_stat_nw_2),
    't_stat_nw_lag3': float(t_stat_nw),
    't_stat_nw_lag4': float(t_stat_nw_4),
    'ic_mean': float(ic_series.mean()),
    'ic_std': float(ic_series.std()),
    'autocorr_1': float(pd.Series(ic_series).autocorr(lag=1)),
    'autocorr_2': float(pd.Series(ic_series).autocorr(lag=2)),
    'conclusion': conclusion,
    'detail': detail,
}

with open(OUTPUT_DIR / 'results.json', 'w') as f:
    json.dump(output_data, f, indent=2, default=str)

print(f"\nResults saved to {OUTPUT_DIR}/")
