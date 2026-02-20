#!/usr/bin/env python3
"""
R1: Label 对比实验
==================

验证 A1/A2/B/C 四种 Label 的预测能力

Author: FcstLabPro
Date: 2026-02-20
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import yaml
import json
from scipy.stats import spearmanr, ttest_1samp
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
import warnings
warnings.filterwarnings('ignore')

# Import label factory
sys.path.insert(0, str(Path(__file__).parent.parent))
from label_factory import get_label, get_label_info, LABEL_STRATEGIES

from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns


# ============================================================================
# Configuration
# ============================================================================

print("=" * 60)
print("R1: Label 对比实验")
print("=" * 60)

DATA_PATH = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"
BASE_CONFIG_PATH = PROJECT_ROOT / "configs" / "experiments" / "weekly" / "exp_weekly_bull_v27_orion_v4_extended_oos.yaml"
OUTPUT_DIR = Path(__file__).parent.parent / "results"

# Experiment config
T = 21  # 预测期限
LABEL_STRATEGIES_TO_TEST = ['simple', 'excess', 'dip_recovery']  # Skip regression for now


# ============================================================================
# Data Loading
# ============================================================================

with open(BASE_CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)

print(f"\n加载数据...")
df = load_csv(str(DATA_PATH))
print(f"原始数据: {len(df)} 行")

# Build features
print("构建特征...")
df = build_features(
    df,
    feature_sets=config['features']['sets'],
    drop_na_method=config['features'].get('drop_na_method', 'ffill_then_drop'),
)

# Get features
feature_cols = get_feature_columns(df)
X = df[feature_cols].values
close_prices = df['close'].values

print(f"特征: {len(feature_cols)} 个")


# ============================================================================
# Walk-Forward Prediction Function
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

        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Train model
        if len(np.unique(y_train)) < 2:
            # Handle edge case
            preds = np.zeros(len(X_test))
        else:
            model = RandomForestClassifier(
                n_estimators=100,
                max_depth=6,
                random_state=42,
                n_jobs=-1
            )
            model.fit(X_train_scaled, y_train)

            if len(model.classes_) == 2:
                preds = model.predict_proba(X_test_scaled)[:, 1]
            else:
                preds = np.zeros(len(X_test))

        predictions.extend(preds)
        true_labels.extend(y[:t+oos_window][-oos_window:])
        valid_indices.extend(range(t, t+oos_window))

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
        return 0.0, 1.0, 0

    ic, p_val = spearmanr(preds_no, labels_no)
    return ic, p_val, n_no


def calc_ic_tstat(predictions, labels, step=21):
    """Calculate IC t-statistic."""
    n = len(predictions)
    n_no = n // step

    if n_no < 5:
        return 0.0, 0.0

    preds_no = predictions[:n_no*step:step]
    labels_no = labels[:n_no*step:step]

    if len(set(preds_no)) < 2 or len(set(labels_no)) < 2:
        return 0.0, 0.0

    # Calculate IC for each period
    ics = []
    for i in range(n_no):
        p = preds_no[i*step:(i+1)*step]
        l = labels_no[i*step:(i+1)*step]
        if len(set(p)) > 1 and len(set(l)) > 1:
            ic, _ = spearmanr(p, l)
            ics.append(ic)

    if len(ics) < 5:
        return 0.0, 0.0

    # T-test
    t_stat, p_val = ttest_1samp(ics, 0)
    return t_stat, p_val


def calc_sharpe(predictions, labels, close_prices, valid_indices, step=21):
    """Calculate Sharpe ratio without MA filter."""
    # Convert to positions
    positions = (predictions > 0.5).astype(int)

    # Align prices
    aligned_prices = []
    for idx in valid_indices:
        if idx < len(close_prices):
            aligned_prices.append(close_prices[idx])
    aligned_prices = np.array(aligned_prices)

    # Calculate returns
    returns = []
    for i in range(len(positions) - 1):
        if i + 1 < len(aligned_prices):
            ret = (aligned_prices[i+1] - aligned_prices[i]) / aligned_prices[i]
            returns.append(positions[i] * ret)

    returns = np.array(returns)

    if len(returns) == 0 or np.std(returns) == 0:
        return 0.0

    sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252 / step)
    return sharpe


# ============================================================================
# Run Experiments
# ============================================================================

results = []

print("\n" + "=" * 60)
print("运行 Label 对比实验...")
print("=" * 60)

for strategy in LABEL_STRATEGIES_TO_TEST:
    print(f"\n--- Testing: {strategy} ---")

    # Generate labels
    label = get_label(strategy, df, T=T)
    label = label.dropna()

    # Align data
    valid_idx = label.index
    X_valid = df.loc[valid_idx, feature_cols].values
    y_valid = label.values

    print(f"  样本数: {len(y_valid)}")
    print(f"  Label 分布: {np.unique(y_valid, return_counts=True)}")

    # Run walk-forward
    predictions, true_labels = run_walk_forward(X_valid, y_valid)

    # Calculate metrics
    ic, p_ic, n_samples = calc_non_overlap_ic(predictions, true_labels)
    t_stat, t_pval = calc_ic_tstat(predictions, true_labels)
    sharpe = calc_sharpe(predictions, true_labels, close_prices, list(range(len(X_valid))))

    # Get label info
    info = get_label_info(strategy)

    result = {
        'strategy': strategy,
        'name': info.get('name', strategy),
        'description': info.get('description', ''),
        'semantic': info.get('semantic', ''),
        'task': info.get('task', 'binary'),
        'n_samples': int(n_samples),
        'ic': float(ic),
        'ic_p_value': float(p_ic),
        't_stat': float(t_stat),
        't_p_value': float(t_pval),
        'sharpe': float(sharpe),
    }

    print(f"  IC: {ic:.4f} (p={p_ic:.6f})")
    print(f"  t-stat: {t_stat:.4f} (p={t_pval:.6f})")
    print(f"  Sharpe: {sharpe:.4f}")

    results.append(result)


# ============================================================================
# Results Summary
# ============================================================================

print("\n" + "=" * 60)
print("结果汇总")
print("=" * 60)

print(f"\n| Label | IC | p-value | t-stat | Sharpe |")
print(f"|-------|-----|---------|--------|--------|")

for r in results:
    sig = "*" if r['ic_p_value'] < 0.05 else ""
    print(f"| {r['strategy']:12} | {r['ic']:.4f} | {r['ic_p_value']:.6f} | {r['t_stat']:.4f} | {r['sharpe']:.4f} |")


# ============================================================================
# Analysis
# ============================================================================

print("\n" + "=" * 60)
print("分析")
print("=" * 60)

# Filter binary tasks only
binary_results = [r for r in results if r['task'] == 'binary']

if binary_results:
    # Sort by t-stat
    sorted_results = sorted(binary_results, key=lambda x: x['t_stat'], reverse=True)

    print("\n按 t-stat 排序:")
    for i, r in enumerate(sorted_results, 1):
        status = "✓" if r['t_stat'] > 1.5 else "✗"
        print(f"  {i}. {r['strategy']}: t-stat={r['t_stat']:.4f} {status}")

    # Best result
    best = sorted_results[0]
    print(f"\n最佳 Label: {best['strategy']}")
    print(f"  t-stat: {best['t_stat']:.4f}")
    print(f"  Sharpe: {best['sharpe']:.4f}")

    # Check success criteria
    has_valid = any(r['t_stat'] > 1.5 for r in binary_results)
    has_sharpe = any(r['sharpe'] > 0.3 for r in binary_results)

    print(f"\n验收标准:")
    print(f"  IC t-stat > 1.5: {'✓ PASS' if has_valid else '✗ FAIL'}")
    print(f"  Sharpe > 0.3: {'✓ PASS' if has_sharpe else '✗ FAIL'}")


# ============================================================================
# Save Results
# ============================================================================

output_data = {
    'experiment': 'R1: Label 对比实验',
    'config': {
        'T': T,
        'init_train': 800,
        'oos_window': 63,
        'step': 21,
    },
    'results': results,
    'best_strategy': best['strategy'] if binary_results else None,
}

with open(OUTPUT_DIR / 'results.json', 'w') as f:
    json.dump(output_data, f, indent=2, default=str)

print(f"\n结果已保存到 {OUTPUT_DIR}/")
