#!/usr/bin/env python3
"""Walk-Forward 过程中收集真实 OOS 预测并计算 IC.

这才是正确的 IC 计算方式
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import yaml

from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns
import src.labels.reversal
from src.labels.registry import get_label_strategy
from sklearn.preprocessing import StandardScaler
from orion_bix import OrionBixClassifier
from scipy.stats import spearmanr


def main():
    print("="*60)
    print("Walk-Forward 真实 OOS IC 分析")
    print("="*60)

    # 加载配置
    config = yaml.safe_load(open('experiments/weekly/weekly_bull_v27_orion_v2/config.yaml'))

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

    X = df[feature_cols].values
    y = df['label'].values
    close_prices = df['close'].values
    timestamps = df.index.values

    # Walk-Forward 参数
    init_train = config['evaluation']['init_train']
    oos_window = config['evaluation']['oos_window']
    step = config['evaluation']['step']

    print(f"Walk-Forward: init_train={init_train}, oos={oos_window}, step={step}")

    # 收集每个 fold 的 OOS 预测
    all_preds = []
    all_returns = []
    all_dates = []

    n_folds = (len(X) - init_train) // step

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

        # 训练
        model = OrionBixClassifier(
            n_estimators=config['model']['params']['n_estimators'],
            random_state=config['model']['params']['random_state'],
        )
        model.fit(X_train, y_train)

        # 预测 - 用第一个预测点
        proba = model.predict_proba(X_test)[:, 1]

        if len(proba) > 0:
            # 计算该 fold 的收益 (21天后)
            ret = (close_prices[test_end-1] - close_prices[test_start]) / close_prices[test_start]
            all_preds.append(proba[0])
            all_returns.append(ret)
            all_dates.append(timestamps[test_start])

        if (i + 1) % 5 == 0:
            print(f"  Fold {i+1}/{n_folds} 完成")

    # 转数组
    all_preds = np.array(all_preds)
    all_returns = np.array(all_returns)

    print(f"\n收集了 {len(all_preds)} 个 OOS 预测")

    # IC - 由于 step=21 和 oos_window=63 有重叠，我们取子集
    # 每 3 个 fold 取一个
    step = 3
    signals = all_preds[::step]
    returns = all_returns[::step]

    print(f"  Non-overlapping 样本数: {len(signals)}")

    # Spearman IC
    ic, p_val = spearmanr(returns, signals)

    print(f"\n结果:")
    print(f"  Spearman IC: {ic:.4f} (p={p_val:.4f})")

    print(f"\n结论:")
    if abs(ic) > 0.05 and p_val < 0.05:
        print(f"  ✅ IC 显著: {ic:.4f}")
    else:
        print(f"  ⚠️ IC 不显著")


if __name__ == '__main__':
    main()
