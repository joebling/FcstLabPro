#!/usr/bin/env python3
"""快速 Walk-Forward 验证脚本.

测试 Scaler 每步重新 fit 是否正常工作
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


def main():
    print("=" * 60)
    print("快速 Walk-Forward 测试")
    print("=" * 60)

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

    print(f"数据: {len(X)} 样本, {len(feature_cols)} 特征")

    # Walk-Forward 参数
    init_train = config['evaluation']['init_train']
    oos_window = config['evaluation']['oos_window']
    step = config['evaluation']['step']

    print(f"Walk-Forward: init_train={init_train}, oos={oos_window}, step={step}")

    # 只测试前 3 个 fold
    n_folds = min(3, (len(X) - init_train) // step)

    for i in range(n_folds):
        train_end = init_train + i * step
        test_start = train_end
        test_end = min(train_end + oos_window, len(X))

        print(f"\nFold {i+1}: train=[0:{train_end}], test=[{test_start}:{test_end}]")

        # 每步重新 fit scaler
        fold_scaler = StandardScaler()
        X_train = fold_scaler.fit_transform(X[:train_end])
        y_train = y[:train_end]
        X_test = fold_scaler.transform(X[test_start:test_end])
        y_test = y[test_start:test_end]

        print(f"  X_train shape: {X_train.shape}")
        print(f"  X_test shape: {X_test.shape}")

        # 训练
        model = OrionBixClassifier(
            n_estimators=config['model']['params']['n_estimators'],
            random_state=config['model']['params']['random_state'],
        )
        model.fit(X_train, y_train)

        # 预测
        y_pred = model.predict(X_test)
        print(f"  预测完成: {len(y_pred)} 样本")

    print("\n✅ 快速测试完成!")


if __name__ == '__main__':
    main()
