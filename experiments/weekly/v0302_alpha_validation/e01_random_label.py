#!/usr/bin/env python3
"""
E01: Random Label Test
======================
Purpose: Detect pipeline leakage by shuffling labels.

If shuffling labels still produces significant IC, the pipeline has leakage.

Expected:
- Real IC: ~0.65 (v4 result)
- Random IC: ≈ 0, not significant

Author: FcstLabPro
Date: 2026-02-20
"""

import sys
from pathlib import Path

# Add project root to path (assuming running from PROJECT_ROOT)
# If running from different location, adjust accordingly
for p in [Path.cwd(), Path(__file__).resolve().parent]:
    PROJECT_ROOT = p
    if (PROJECT_ROOT / "src").exists():
        sys.path.insert(0, str(PROJECT_ROOT))
        break
else:
    # Default to standard location
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
# Import labels module to register strategies
import src.labels.reversal
from src.labels.registry import get_label_strategy


# ============================================================================
# Configuration
# ============================================================================

DATA_PATH = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"
CONFIG_PATH = PROJECT_ROOT / "configs" / "experiments" / "weekly" / "exp_weekly_bull_v27_orion_v4_extended_oos.yaml"
OUTPUT_DIR = Path(__file__).parent

# Parameters
N_PERMUTATIONS = 30  # Number of random label tests
RANDOM_SEED = 42


# ============================================================================
# Data Loading
# ============================================================================

print("=" * 60)
print("E01: Random Label Test")
print("=" * 60)

# Load config
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
y_original = df['label'].values
dates = df.index.tolist()
close_prices = df['close'].values

print(f"Data: {len(X)} samples, {len(feature_cols)} features")
print(f"Label distribution: {np.bincount(y_original)}")


# ============================================================================
# Generate Future Returns
# ============================================================================

T = config['label']['T']
future_returns = []
valid_indices = []

for i in range(len(close_prices)):
    if i + T < len(close_prices):
        ret = (close_prices[i+T] - close_prices[i]) / close_prices[i]
        future_returns.append(ret)
        valid_indices.append(i)

future_returns = np.array(future_returns)
print(f"Future returns: {len(future_returns)} samples")


# ============================================================================
# Walk-Forward Prediction Function
# ============================================================================

def run_walk_forward(X, y, init_train=800, oos_window=63, step=21):
    """
    Run walk-forward prediction with scaler refit (no leakage).
    """
    n_samples = len(X)
    predictions = []
    true_labels = []
    fold_dates = []

    t = init_train
    while t + oos_window <= n_samples:
        # Training data
        X_train = X[:t]
        y_train = y[:t]

        # Test data
        X_test = X[t:t+oos_window]
        y_test = y[t:t+oos_window]

        # Scale features (refit each step - no leakage)
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Train model
        model = OrionBixClassifier(
            n_estimators=4,
            random_state=42,
        )
        model.fit(X_train_scaled, y_train)

        # Predict probabilities
        if len(model.classes_) == 2:
            preds = model.predict_proba(X_test_scaled)[:, 1]
        else:
            preds = np.zeros(len(X_test))

        predictions.extend(preds)
        true_labels.extend(y_test)
        fold_dates.extend(dates[t:t+oos_window])

        t += step

    return np.array(predictions), np.array(true_labels), fold_dates


# ============================================================================
# Calculate Non-overlapping IC
# ============================================================================

def calc_non_overlap_ic(predictions, true_labels, returns, step=21):
    """Calculate IC using non-overlapping samples."""
    n = min(len(predictions), len(returns))
    n_non_overlap = n // step

    if n_non_overlap < 2:
        return 0.0, 1.0

    # Take non-overlapping samples
    preds_no = predictions[:n_non_overlap * step:step]
    rets_no = returns[:n_non_overlap * step:step]

    if len(set(preds_no)) < 2 or len(set(rets_no)) < 2:
        return 0.0, 1.0

    ic, p_val = spearmanr(preds_no, rets_no)
    return ic, p_val


# ============================================================================
# Run Real Labels (Baseline)
# ============================================================================

print("\n" + "=" * 60)
print("Running with REAL labels (baseline)...")
print("=" * 60)

preds_real, labels_real, _ = run_walk_forward(X, y_original)
ic_real, p_real = calc_non_overlap_ic(preds_real, labels_real, future_returns)

print(f"\nReal Label Results:")
print(f"  IC: {ic_real:.4f}")
print(f"  p-value: {p_real:.6f}")
print(f"  Significant: {'YES' if p_real < 0.05 else 'NO'}")


# ============================================================================
# Run Random Labels
# ============================================================================

print("\n" + "=" * 60)
print(f"Running {N_PERMUTATIONS} random label permutations...")
print("=" * 60)

np.random.seed(RANDOM_SEED)
results = []

for i in range(N_PERMUTATIONS):
    # Shuffle labels
    y_shuffled = np.random.permutation(y_original)

    # Run walk-forward
    preds_rand, _, _ = run_walk_forward(X, y_shuffled)

    # Calculate IC
    ic_rand, p_rand = calc_non_overlap_ic(preds_rand, labels_real, future_returns)

    results.append({
        'iteration': i,
        'ic': ic_rand,
        'p_value': p_rand,
        'significant': p_rand < 0.05
    })

    if (i + 1) % 10 == 0:
        print(f"  Completed {i + 1}/{N_PERMUTATIONS}...")

results_df = pd.DataFrame(results)

# Calculate statistics
mean_ic = results_df['ic'].mean()
std_ic = results_df['ic'].std()
max_ic = results_df['ic'].max()
min_ic = results_df['ic'].min()
n_significant = results_df['significant'].sum()

# Empirical p-value
n_extreme = (np.abs(results_df['ic']) >= np.abs(ic_real)).sum()
p_empirical = n_extreme / N_PERMUTATIONS


# ============================================================================
# Print Results
# ============================================================================

print("\n" + "=" * 60)
print("RESULTS SUMMARY")
print("=" * 60)

print(f"\nReal Label (Baseline):")
print(f"  IC: {ic_real:.4f}")
print(f"  p-value: {p_real:.6f}")

print(f"\nRandom Label Statistics (n={N_PERMUTATIONS}):")
print(f"  Mean IC: {mean_ic:.4f}")
print(f"  Std IC: {std_ic:.4f}")
print(f"  Min IC: {min_ic:.4f}")
print(f"  Max IC: {max_ic:.4f}")
print(f"  Significant (p<0.05): {n_significant}/{N_PERMUTATIONS}")
print(f"  Empirical p-value: {p_empirical:.4f}")

print("\nDistribution of Random ICs:")
bins = [-1.0, -0.3, -0.1, 0.0, 0.1, 0.3, 1.0]
hist, _ = np.histogram(results_df['ic'], bins=bins)
for i in range(len(hist)):
    bar = "█" * hist[i]
    print(f"  {bins[i]:5.1f} to {bins[i+1]:5.1f}: {bar} ({hist[i]})")


# ============================================================================
# Conclusion
# ============================================================================

print("\n" + "=" * 60)
print("CONCLUSION")
print("=" * 60)

# FIX: Check if real IC is significant first
# If real IC itself is not significant (p > 0.05), the model has no predictive power
if p_real > 0.05:
    conclusion = "FAIL - Real IC not significant (no predictive power)"
    detail = f"Real IC = {ic_real:.4f}, p = {p_real:.4f}. Model has no significant predictive ability."
elif p_empirical < 0.05:
    conclusion = "FAIL - Pipeline may have leakage"
    detail = f"Random labels produced IC >= real IC in {n_extreme}/{N_PERMUTATIONS} cases (p={p_empirical:.4f})"
else:
    conclusion = "PASS - No significant leakage detected"
    detail = f"Random labels rarely produce IC >= real IC (p={p_empirical:.4f})"

print(f"\n{conclusion}")
print(f"  {detail}")

# Save results
output_data = {
    'experiment': 'E01 Random Label Test',
    'real_ic': float(ic_real),
    'real_p_value': float(p_real),
    'n_permutations': N_PERMUTATIONS,
    'random_ic_mean': float(mean_ic),
    'random_ic_std': float(std_ic),
    'random_ic_min': float(min_ic),
    'random_ic_max': float(max_ic),
    'n_significant': int(n_significant),
    'empirical_p_value': float(p_empirical),
    'conclusion': conclusion,
    'detail': detail,
    'all_results': results
}

with open(OUTPUT_DIR / 'results.json', 'w') as f:
    json.dump(output_data, f, indent=2, default=str)

results_df.to_csv(OUTPUT_DIR / 'random_label_results.csv', index=False)

print(f"\nResults saved to {OUTPUT_DIR}/")
