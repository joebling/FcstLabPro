#!/usr/bin/env python3
"""
R1: Label 对比实验
==================

验证 simple_return/excess_return/dip_recovery 三种 Label 的预测能力

修复:
- C1: dip_recovery 使用正确的未来低点计算 recovery
- C2: Sharpe 计算正确对齐预测和价格
- M1: IC t-stat 按 OOS fold 计算

Author: FcstLabPro
Date: 2026-02-20
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
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

from src.labels.registry import get_label_strategy, list_label_strategies
from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns


print("=" * 60)
print("R1: Label 对比实验 (v2 - 修复版)")
print("=" * 60)

DATA_PATH = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"
BASE_CONFIG_PATH = PROJECT_ROOT / "configs" / "experiments" / "weekly" / "exp_weekly_bull_v27_orion_v4_extended_oos.yaml"
OUTPUT_DIR = Path(__file__).parent

T = 21
LABEL_STRATEGIES_TO_TEST = ['simple_return', 'excess_return', 'dip_recovery']


with open(BASE_CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)

print(f"\n加载数据...")
df = load_csv(str(DATA_PATH))
print(f"原始数据: {len(df)} 行")

print("构建特征...")
df = build_features(
    df,
    feature_sets=config['features']['sets'],
    drop_na_method=config['features'].get('drop_na_method', 'ffill_then_drop'),
)

feature_cols = get_feature_columns(df)
close_prices = df['close'].values

print(f"特征: {len(feature_cols)} 个")


def run_walk_forward(X, y, init_train=800, oos_window=63, step=21, purge_gap=0):
    """Run walk-forward prediction with proper index tracking."""
    n_samples = len(X)
    predictions = []
    true_labels = []
    valid_indices = []
    fold_ics = []
    
    t = init_train
    fold_id = 0
    while t + oos_window <= n_samples:
        train_end = t - purge_gap
        if train_end <= 0:
            t += step
            continue
            
        X_train = X[:train_end]
        y_train = y[:train_end]
        X_test = X[t:t+oos_window]
        y_test = y[t:t+oos_window]

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        if len(np.unique(y_train)) < 2:
            preds = np.zeros(len(X_test))
            proba = np.zeros(len(X_test))
        else:
            model = RandomForestClassifier(
                n_estimators=100,
                max_depth=6,
                random_state=42,
                n_jobs=-1
            )
            model.fit(X_train_scaled, y_train)

            if len(model.classes_) == 2:
                proba = model.predict_proba(X_test_scaled)[:, 1]
            else:
                proba = np.zeros(len(X_test))
            preds = (proba > 0.5).astype(int)

        predictions.extend(proba)
        true_labels.extend(y_test)
        valid_indices.extend(range(t, t + oos_window))

        if len(np.unique(y_test)) > 1 and len(np.unique(preds)) > 1:
            ic, _ = spearmanr(proba, y_test)
            fold_ics.append({'fold': fold_id, 'ic': ic})

        t += step
        fold_id += 1

    return np.array(predictions), np.array(true_labels), np.array(valid_indices), fold_ics


def calc_ic_metrics(predictions, true_labels, fold_ics):
    """Calculate IC metrics properly."""
    if len(fold_ics) < 3:
        return {'ic': 0.0, 'ic_p_value': 1.0, 't_stat': 0.0, 't_p_value': 1.0, 'n_folds': 0}
    
    ics = [f['ic'] for f in fold_ics]
    overall_ic, overall_p = spearmanr(predictions, true_labels)
    t_stat, t_p_value = ttest_1samp(ics, 0)
    
    return {
        'ic': overall_ic,
        'ic_p_value': overall_p,
        't_stat': t_stat,
        't_p_value': t_p_value,
        'n_folds': len(fold_ics),
        'fold_ics': ics,
    }


def calc_sharpe(predictions, close_prices, valid_indices, step=21):
    """Calculate Sharpe ratio with proper price alignment."""
    aligned_prices = close_prices[valid_indices]
    positions = (predictions > 0.5).astype(int)
    
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


results = []

print("\n" + "=" * 60)
print("运行 Label 对比实验...")
print("=" * 60)

for strategy in LABEL_STRATEGIES_TO_TEST:
    print(f"\n--- Testing: {strategy} ---")

    label_func = get_label_strategy(strategy)
    label_kwargs = {'T': T}
    if strategy == 'dip_recovery':
        label_kwargs['dip_threshold'] = 0.05
        label_kwargs['recovery_threshold'] = 0.03
    elif strategy == 'excess_return':
        label_kwargs['rolling_window'] = 63
    
    label = label_func(df, **label_kwargs)
    label = label.dropna()

    valid_idx = label.index
    X_valid = df.loc[valid_idx, feature_cols].values
    y_valid = label.values

    print(f"  样本数: {len(y_valid)}")
    print(f"  Label 分布: {np.unique(y_valid, return_counts=True)}")

    predictions, true_labels, valid_indices, fold_ics = run_walk_forward(
        X_valid, y_valid, purge_gap=T
    )

    ic_metrics = calc_ic_metrics(predictions, true_labels, fold_ics)
    sharpe = calc_sharpe(predictions, close_prices, valid_indices)

    result = {
        'strategy': strategy,
        'n_samples': len(y_valid),
        'n_folds': ic_metrics['n_folds'],
        'ic': ic_metrics['ic'],
        'ic_p_value': ic_metrics['ic_p_value'],
        't_stat': ic_metrics['t_stat'],
        't_p_value': ic_metrics['t_p_value'],
        'sharpe': sharpe,
    }

    print(f"  IC: {ic_metrics['ic']:.4f} (p={ic_metrics['ic_p_value']:.6f})")
    print(f"  t-stat: {ic_metrics['t_stat']:.4f} (p={ic_metrics['t_p_value']:.6f}, n_folds={ic_metrics['n_folds']})")
    print(f"  Sharpe: {sharpe:.4f}")

    results.append(result)


print("\n" + "=" * 60)
print("结果汇总")
print("=" * 60)

print(f"\n| Label | IC | p-value | t-stat | n_folds | Sharpe |")
print(f"|-------|-----|---------|--------|---------|--------|")

for r in results:
    print(f"| {r['strategy']:15} | {r['ic']:.4f} | {r['ic_p_value']:.6f} | {r['t_stat']:.4f} | {r['n_folds']:7} | {r['sharpe']:.4f} |")


print("\n" + "=" * 60)
print("分析")
print("=" * 60)

sorted_results = sorted(results, key=lambda x: x['t_stat'], reverse=True)

print("\n按 t-stat 排序:")
for i, r in enumerate(sorted_results, 1):
    status = "✓" if r['t_stat'] > 1.5 else "✗"
    print(f"  {i}. {r['strategy']}: t-stat={r['t_stat']:.4f}, n_folds={r['n_folds']} {status}")

best = sorted_results[0]
print(f"\n最佳 Label: {best['strategy']}")
print(f"  t-stat: {best['t_stat']:.4f}")
print(f"  Sharpe: {best['sharpe']:.4f}")

has_valid = any(r['t_stat'] > 1.5 for r in results)
has_sharpe = any(r['sharpe'] > 0.3 for r in results)

print(f"\n验收标准:")
print(f"  IC t-stat > 1.5: {'✓ PASS' if has_valid else '✗ FAIL'}")
print(f"  Sharpe > 0.3: {'✓ PASS' if has_sharpe else '✗ FAIL'}")


output_data = {
    'experiment': 'R1: Label 对比实验 (v2 - 修复版)',
    'config': {
        'T': T,
        'init_train': 800,
        'oos_window': 63,
        'step': 21,
        'purge_gap': T,
    },
    'results': results,
    'best_strategy': best['strategy'],
}

with open(OUTPUT_DIR / 'results.json', 'w') as f:
    json.dump(output_data, f, indent=2, default=str)

print(f"\n结果已保存到 {OUTPUT_DIR}/results.json")
