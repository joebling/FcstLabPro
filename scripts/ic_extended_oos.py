#!/usr/bin/env python3
"""扩展 OOS 版本的 IC 分析."""

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


def calculate_ic_t_stat(ic_series):
    ic_series = np.array(ic_series)
    ic_series = ic_series[~np.isnan(ic_series)]
    if len(ic_series) < 2:
        return 0, 0
    ic_mean = np.mean(ic_series)
    ic_std = np.std(ic_series, ddof=1)
    if ic_std == 0:
        return ic_mean, 0
    t_stat = ic_mean / (ic_std / np.sqrt(len(ic_series)))
    return ic_mean, t_stat


def main():
    print("="*60)
    print("扩展 OOS 版本 IC 分析")
    print("="*60)

    # 加载配置
    config = yaml.safe_load(open('experiments/weekly/weekly_bull_v27_orion_v4_extended_oos/config.yaml'))

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

    # 加载模型
    model = joblib.load('experiments/weekly/weekly_bull_v27_orion_v4_extended_oos/model.joblib')
    scaler = joblib.load('experiments/weekly/weekly_bull_v27_orion_v4_extended_oos/scaler.joblib')

    # 预测
    init_train = config['evaluation']['init_train']
    X_test = df[feature_cols].values[init_train:]
    timestamps = df.index[init_train:].values
    close_prices = df['close'].values[init_train:]

    X_test_scaled = scaler.transform(X_test)
    proba = model.predict_proba(X_test_scaled)[:, 1]

    # Non-overlapping returns
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

    # IC
    ic, p_val = spearmanr(returns, signals)

    # 月度 IC
    df_monthly = pd.DataFrame({'signal': signals, 'return': returns, 'date': pd.DatetimeIndex(dates)})
    df_monthly['month'] = df_monthly['date'].dt.to_period('M')

    monthly_ic = []
    for month in df_monthly['month'].unique():
        m = df_monthly[df_monthly['month'] == month]
        if len(m) >= 2:
            ic_m, _ = spearmanr(m['return'], m['signal'])
            monthly_ic.append(ic_m)

    ic_mean, t_stat = calculate_ic_t_stat(monthly_ic)

    print(f"\n数据概况:")
    print(f"  Non-overlapping 样本数: {len(signals)}")
    print(f"  测试集时间范围: {pd.Timestamp(dates[0])} ~ {pd.Timestamp(dates[-1])}")
    print(f"  月度 IC 数量: {len(monthly_ic)}")

    print(f"\nIC 统计:")
    print(f"  Spearman IC: {ic:.4f} (p={p_val:.4f})")
    print(f"  IC 均值: {ic_mean:.4f}")
    print(f"  IC t-stat: {t_stat:.4f}")

    print(f"\n结论:")
    if abs(ic) > 0.05:
        if p_val < 0.05:
            print(f"  ✅ IC 显著: {ic:.4f} (p={p_val:.4f})")
        else:
            print(f"  ⚠️ IC > 0.05 但 p > 0.05")
    else:
        print(f"  ⚠️ IC 不显著: {ic:.4f}")

    if abs(t_stat) > 2:
        print(f"  ✅ t-stat > 2")
    else:
        print(f"  ⚠️ t-stat < 2 (样本量: {len(monthly_ic)})")


if __name__ == '__main__':
    main()
