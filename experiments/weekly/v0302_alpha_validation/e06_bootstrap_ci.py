#!/usr/bin/env python3
"""
E06: Bootstrap Confidence Interval Test
========================================
Purpose: Quantify uncertainty in IC estimate.

Test: Calculate bootstrap CI for IC
- If CI narrow: IC estimate precise
- If CI wide: IC estimate uncertain

Expected:
- IC: ~0.35
- 95% CI should show range of plausible values

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
from sklearn.ensemble import RandomForestClassifier
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
print("E06: Bootstrap Confidence Interval Test")
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

# Get features
feature_cols = get_feature_columns(df)
X = df[feature_cols].values
y = df['label'].values

print(f"Data: {len(X)} samples, {len(feature_cols)} features")


# ============================================================================
# Walk-Forward Prediction
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

        model = RandomForestClassifier(
            n_estimators=100, max_depth=6, random_state=42, n_jobs=-1
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


# ============================================================================
# Non-overlapping IC
# ============================================================================

def calc_non_overlap_ic(predictions, labels, step=21):
    """Calculate non-overlapping IC."""
    n = len(predictions)
    n_no = n // step
    preds_no = predictions[:n_no*step:step]
    labels_no = labels[:n_no*step:step]
    ic, p_val = spearmanr(preds_no, labels_no)
    return ic, p_val, n_no


# ============================================================================
# Bootstrap
# ============================================================================

print("\nRunning walk-forward prediction...")
predictions, true_labels = run_walk_forward(X, y)
step = config['evaluation']['step']
ic_orig, p_orig, n_samples = calc_non_overlap_ic(predictions, true_labels, step)

print(f"Original IC: {ic_orig:.4f}, p={p_orig:.6f}, n={n_samples}")

# IID Bootstrap
print("\nRunning IID Bootstrap (1000 samples)...")
n_boot = 1000
iid_ics = []
np.random.seed(42)

pairs = list(zip(predictions, true_labels))
for _ in range(n_boot):
    idx = np.random.choice(len(pairs), size=len(pairs), replace=True)
    boot_preds = [pairs[i][0] for i in idx]
    boot_labels = [pairs[i][1] for i in idx]

    if len(set(boot_preds)) > 1 and len(set(boot_labels)) > 1:
        ic, _ = spearmanr(boot_preds, boot_labels)
        iid_ics.append(ic)

iid_ics = np.array(iid_ics)

# Block Bootstrap
print("Running Block Bootstrap (1000 samples)...")
block_size = 4
n_blocks = len(pairs) // block_size
block_ics = []

for _ in range(n_boot):
    block_idx = np.random.choice(n_blocks, size=n_blocks, replace=True)
    boot_idx = []
    for b in block_idx:
        boot_idx.extend(range(b * block_size, min((b + 1) * block_size, len(pairs))))

    boot_preds = [pairs[i][0] for i in boot_idx if i < len(pairs)]
    boot_labels = [pairs[i][1] for i in boot_idx if i < len(pairs)]

    if len(set(boot_preds)) > 1 and len(set(boot_labels)) > 1:
        ic, _ = spearmanr(boot_preds, boot_labels)
        block_ics.append(ic)

block_ics = np.array(block_ics)


# ============================================================================
# Results
# ============================================================================

print("\n" + "=" * 60)
print("RESULTS SUMMARY")
print("=" * 60)

iid_mean = np.mean(iid_ics)
iid_std = np.std(iid_ics)
iid_ci_lower = np.percentile(iid_ics, 2.5)
iid_ci_upper = np.percentile(iid_ics, 97.5)

block_mean = np.mean(block_ics)
block_std = np.std(block_ics)
block_ci_lower = np.percentile(block_ics, 2.5)
block_ci_upper = np.percentile(block_ics, 97.5)

print(f"\nOriginal IC: {ic_orig:.4f}")
print(f"\nIID Bootstrap (n={n_boot}):")
print(f"  Mean: {iid_mean:.4f}")
print(f"  Std: {iid_std:.4f}")
print(f"  95% CI: [{iid_ci_lower:.4f}, {iid_ci_upper:.4f}]")

print(f"\nBlock Bootstrap (block_size={block_size}, n={n_boot}):")
print(f"  Mean: {block_mean:.4f}")
print(f"  Std: {block_std:.4f}")
print(f"  95% CI: [{block_ci_lower:.4f}, {block_ci_upper:.4f}]")

# Check if CI includes zero
includes_zero_iid = (iid_ci_lower <= 0 <= iid_ci_upper)
includes_zero_block = (block_ci_lower <= 0 <= block_ci_upper)

print(f"\n95% CI includes zero:")
print(f"  IID: {'YES' if includes_zero_iid else 'NO'}")
print(f"  Block: {'YES' if includes_zero_block else 'NO'}")


# ============================================================================
# Conclusion
# ============================================================================

print("\n" + "=" * 60)
print("CONCLUSION")
print("=" * 60)

if includes_zero_iid or includes_zero_block:
    conclusion = "UNCERTAIN - CI includes zero, IC may not be reliable"
    detail = "95% CI includes zero, cannot reject null hypothesis"
else:
    conclusion = "PRECISE - CI excludes zero, IC is reliable"
    detail = "95% CI excludes zero, IC is statistically significant"

print(f"\n{conclusion}")
print(f"  {detail}")

# Additional analysis
print(f"\nInterpretation:")
print(f"  We are 95% confident the true IC is between:")
print(f"    IID:   [{iid_ci_lower:.4f}, {iid_ci_upper:.4f}]")
print(f"    Block: [{block_ci_lower:.4f}, {block_ci_upper:.4f}]")


# ============================================================================
# Save Results
# ============================================================================

output_data = {
    'experiment': 'E06 Bootstrap CI Test',
    'original_ic': float(ic_orig),
    'original_p_value': float(p_orig),
    'n_non_overlap_samples': int(n_samples),
    'iid_bootstrap': {
        'mean': float(iid_mean),
        'std': float(iid_std),
        'ci_95_lower': float(iid_ci_lower),
        'ci_95_upper': float(iid_ci_upper),
        'includes_zero': includes_zero_iid,
    },
    'block_bootstrap': {
        'block_size': block_size,
        'mean': float(block_mean),
        'std': float(block_std),
        'ci_95_lower': float(block_ci_lower),
        'ci_95_upper': float(block_ci_upper),
        'includes_zero': includes_zero_block,
    },
    'conclusion': conclusion,
    'detail': detail,
}

with open(OUTPUT_DIR / 'results.json', 'w') as f:
    json.dump(output_data, f, indent=2, default=str)

print(f"\nResults saved to {OUTPUT_DIR}/")
