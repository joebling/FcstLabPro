#!/usr/bin/env python3
"""简化版 IC 修正分析.

修正:
- Non-overlapping returns
- 正确 t-stat (基于月度 IC)
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


def load_config(config_path):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def calculate_ic_t_stat(ic_series):
    """基于 IC 时间序列计算 t-stat."""
    ic_series = np.array(ic_series)
    ic_series = ic_series[~np.isnan(ic_series)]
    if len(ic_series) < 2:
        return 0
    ic_mean = np.mean(ic_series)
    ic_std = np.std(ic_series, ddof=1)
    if ic_std == 0:
        return 0
    return ic_mean / (ic_std / np.sqrt(len(ic_series)))


def main():
    # 加载配置和数据
    config = load_config('experiments/weekly/weekly_bull_v27_orion_v2/config.yaml')
    df = load_csv(config['data']['path'])

    from src.features.builder import build_features, get_feature_columns
    import src.labels.reversal
    from src.labels.registry import get_label_strategy

    df = build_features(df, config['features']['sets'])
    feature_cols = get_feature_columns(df)

    label_func = get_label_strategy(config['label']['strategy'])
    labels = label_func(df, T=config['label']['T'], X=config['label']['X'])
    if 'map' in config['label']:
        labels = labels.map({int(k): int(v) for k, v in config['label']['map'].items()})
    df['label'] = labels
    df = df.dropna(subset=['label'])

    # 加载模型
    import joblib
    model = joblib.load('experiments/weekly/weekly_bull_v27_orion_v2/model.joblib')
    scaler = joblib.load('experiments/weekly/weekly_bull_v27_orion_v2/scaler.joblib')

    # 预测
    init_train = config['evaluation'].get('init_train', 1500)
    X_test = df[feature_cols].values[init_train:]
    timestamps = df.index[init_train:]
    close_prices = df['close'].values[init_train:]

    X_test_scaled = scaler.transform(X_test)
    proba = model.predict_proba(X_test_scaled)[:, 1]

    # === Non-overlapping returns ===
    # 每 21 天取一个样本
    step = 21
    signals = []
    returns = []
    dates = []

    for i in range(0, len(proba) - step, step):
        signals.append(proba[i])
        ret = (close_prices[i + step] - close_prices[i]) / close_prices[i]
        returns.append(ret)
        dates.append(timestamps[i])

    signals = np.array(signals)
    returns = np.array(returns)

    print("="*60)
    print("Non-overlapping IC 分析")
    print("="*60)
    print(f"样本数: {len(signals)}")

    # 整体 IC
    from scipy.stats import spearmanr
    spearman_ic, p_val = spearmanr(returns, signals)
    print(f"\nSpearman IC: {spearman_ic:.4f} (p={p_val:.4f})")

    # 按月 IC 序列 + t-stat
    df_monthly = pd.DataFrame({'signal': signals, 'return': returns, 'date': dates})
    df_monthly['month'] = pd.to_datetime(df_monthly['date']).dt.to_period('M')

    monthly_ic = []
    for month in df_monthly['month'].unique():
        m = df_monthly[df_monthly['month'] == month]
        if len(m) >= 2:
            ic, _ = spearmanr(m['return'], m['signal'])
            monthly_ic.append(ic)

    t_stat = calculate_ic_t_stat(monthly_ic)
    print(f"\n月度 IC 数量: {len(monthly_ic)}")
    print(f"IC 均值: {np.mean(monthly_ic):.4f}")
    print(f"IC t-stat: {t_stat:.4f}")

    print("\n" + "="*60)
    print("结论")
    print("="*60)
    print(f"\n之前: IC=0.54 (虚高 due to overlapping)")
    print(f"现在: IC={spearman_ic:.4f}, t-stat={t_stat:.4f}")

    if abs(spearman_ic) > 0.1:
        level = "强"
    elif abs(spearman_ic) > 0.05:
        level = "中等"
    else:
        level = "弱/无"
    print(f"IC 强度: {level}")

    if t_stat > 2:
        print("✅ 统计显著")
    else:
        print("⚠️ 不显著")


if __name__ == '__main__':
    main()
