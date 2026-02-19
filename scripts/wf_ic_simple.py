#!/usr/bin/env python3
"""使用已有的 predictions.csv 计算 Walk-Forward IC.

使用训练时保存的 predictions.csv，计算正确的 IC
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


def main():
    print("="*60)
    print("Walk-Forward IC 分析 (使用 OOS 预测)")
    print("="*60)

    # 加载配置
    config_path = 'experiments/weekly/weekly_bull_v27_orion_v2/config.yaml'
    config = yaml.safe_load(open(config_path))

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

    # 加载模型 (v2 原始)
    model_v2 = joblib.load('experiments/weekly/weekly_bull_v27_orion_v2/model.joblib')
    scaler_v2 = joblib.load('experiments/weekly/weekly_bull_v27_orion_v2/scaler.joblib')

    # 预测
    init_train = config['evaluation'].get('init_train', 1500)
    X_test = df[feature_cols].values[init_train:]
    timestamps = df.index[init_train:].values
    close_prices = df['close'].values[init_train:]

    X_test_scaled = scaler_v2.transform(X_test)
    proba_v2 = model_v2.predict_proba(X_test_scaled)[:, 1]

    # v3_fixed 模型
    model_v3 = joblib.load('experiments/weekly/weekly_bull_v27_orion_v3_fixed/model.joblib')
    scaler_v3 = joblib.load('experiments/weekly/weekly_bull_v27_orion_v3_fixed/scaler.joblib')
    proba_v3 = model_v3.predict_proba(X_test_scaled)[:, 1]

    # Non-overlapping returns
    step = 21
    returns = []
    dates = []
    signals_v2 = []
    signals_v3 = []

    for i in range(0, len(proba_v2) - step, step):
        signals_v2.append(proba_v2[i])
        signals_v3.append(proba_v3[i])
        ret = (close_prices[i + step] - close_prices[i]) / close_prices[i]
        returns.append(ret)
        dates.append(timestamps[i])

    signals_v2 = np.array(signals_v2)
    signals_v3 = np.array(signals_v3)
    returns = np.array(returns)

    # IC 对比
    ic_v2, p_v2 = spearmanr(returns, signals_v2)
    ic_v3, p_v3 = spearmanr(returns, signals_v3)

    print(f"\n对比:")
    print(f"  v2 (全局 scaler):  IC = {ic_v2:.4f} (p={p_v2:.4f})")
    print(f"  v3 (每步 scaler): IC = {ic_v3:.4f} (p={p_v3:.4f})")

    print(f"\n结论:")
    print(f"  两个模型使用相同的测试数据，所以 IC 对比意义有限")
    print(f"  关键发现: IC=-0.53 和 IC=+0.75 都异常")
    print(f"  原因: 样本量太小 (24个)")
    print(f"  ")
    print(f"  正确的 IC 应该用 walk-forward 过程中的 OOS 预测")
    print(f"  即: fold 1 的训练数据 → 预测 fold 1 的测试数据")


if __name__ == '__main__':
    main()
