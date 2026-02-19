#!/usr/bin/env python3
"""使用 Walk-Forward 过程中的预测计算 IC.

这才是正确的 IC 计算方式 - 使用每个 fold 的 OOS 预测
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import yaml
import joblib

from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns
import src.labels.reversal
from src.labels.registry import get_label_strategy
from scipy.stats import spearmanr


def calculate_ic_with_wf_predictions(model_dir, model_name):
    """使用 walk-forward 预测计算 IC."""
    print(f"\n{'='*60}")
    print(f"Walk-Forward IC: {model_name}")
    print(f"{'='*60}")

    # 加载配置
    config = yaml.safe_load(open(f'{model_dir}/config.yaml'))

    # 加载数据
    df = load_csv(config['data']['path'])
    df = build_features(df, config['features']['sets'])
    feature_cols = get_feature_columns(df)

    # 标签
    label_func = get_label_strategy(config['label']['strategy'])
    labels = label_func(df, T=config['label']['T'], X=config['label']['X'])
    if 'map' in config['label']:
        labels = labels.map({int(k): int(v) for k, v in config['label']['map'].items()})
    df['label'] = labels
    df = df.dropna(subset=['label'])

    # Walk-Forward 参数
    init_train = config['evaluation']['init_train']
    oos_window = config['evaluation']['oos_window']
    step = config['evaluation']['step']

    # 收集每个 fold 的预测
    from sklearn.preprocessing import StandardScaler
    from orion_bix import OrionBixClassifier

    X = df[feature_cols].values
    y = df['label'].values

    all_preds = []
    all_returns = []
    all_dates = []

    n_folds = (len(X) - init_train) // step

    print(f"运行 Walk-Forward 并收集预测...")

    for i in range(n_folds):
        train_end = init_train + i * step
        test_start = train_end
        test_end = min(train_end + oos_window, len(X))

        if test_end <= test_start:
            break

        # 每步重新 fit scaler
        fold_scaler = StandardScaler()
        X_train = fold_scaler.fit_transform(X[:train_end])
        y_train = y[:train_end]
        X_test = fold_scaler.transform(X[test_start:test_end])

        # 训练模型
        model = OrionBixClassifier(
            n_estimators=config['model']['params']['n_estimators'],
            random_state=config['model']['params']['random_state'],
        )
        model.fit(X_train, y_train)

        # 预测概率
        proba = model.predict_proba(X_test)[:, 1]

        # 获取实际标签和价格
        close_prices = df['close'].values[test_start:test_end]
        true_labels = y[test_start:test_end]
        timestamps = df.index[test_start:test_end]

        # 对齐: 预测信号 vs 未来收益
        # 使用每个 fold 第一个预测点
        if len(proba) > 0:
            # fold 结束时的价格变化
            ret = (close_prices[-1] - close_prices[0]) / close_prices[0]
            all_preds.append(proba[0])  # 使用第一个预测
            all_returns.append(ret)
            all_dates.append(timestamps[0])

    # 转为数组
    all_preds = np.array(all_preds)
    all_returns = np.array(all_returns)

    # Non-overlapping
    # 由于 oos_window=63 步长=21，有重叠
    # 我们只取每 3 个 fold 一个样本
    step = 3
    signals = []
    returns = []
    dates = []

    for i in range(0, len(all_preds) - step, step):
        signals.append(all_preds[i])
        returns.append(all_returns[i])
        dates.append(all_dates[i])

    signals = np.array(signals)
    returns = np.array(returns)

    # IC
    spearman_ic, p_val = spearmanr(returns, signals)

    print(f"\nWalk-Forward IC 统计:")
    print(f"  样本数: {len(signals)}")
    print(f"  Spearman IC: {spearman_ic:.4f} (p={p_val:.4f})")

    return {
        'model': model_name,
        'ic': spearman_ic,
        'p_val': p_val,
        'n_samples': len(signals)
    }


def main():
    print("="*60)
    print("Walk-Forward IC 分析")
    print("="*60)

    # 只运行 v3_fixed (因为需要每步重新 fit)
    result = calculate_ic_with_wf_predictions(
        'experiments/weekly/weekly_bull_v27_orion_v3_fixed',
        'v3_fixed (每步 scaler refit)'
    )

    print(f"\n结论:")
    if abs(result['ic']) > 0.05:
        print(f"  {'✅' if result['ic'] > 0 else '⚠️'} IC 显著: {result['ic']:.4f}")
    else:
        print(f"  ⚠️ IC 不显著: {result['ic']:.4f}")


if __name__ == '__main__':
    main()
