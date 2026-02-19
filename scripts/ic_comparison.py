#!/usr/bin/env python3
"""IC 分析 - 使用修复后的模型 (Scaler 每步重新 fit).

比较 v2 和 v3_fixed 的 IC 差异
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


def calculate_ic_t_stat(ic_series):
    """基于 IC 时间序列计算 t-stat."""
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


def analyze_model(model_dir, model_name):
    """分析单个模型."""
    print(f"\n{'='*60}")
    print(f"模型: {model_name}")
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

    # 加载模型
    model = joblib.load(f'{model_dir}/model.joblib')
    scaler = joblib.load(f'{model_dir}/scaler.joblib')

    # 预测
    init_train = config['evaluation'].get('init_train', 1500)
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
    spearman_ic, p_val = spearmanr(returns, signals)

    # 月度 IC + t-stat
    df_monthly = pd.DataFrame({'signal': signals, 'return': returns, 'date': pd.DatetimeIndex(dates)})
    df_monthly['month'] = df_monthly['date'].dt.to_period('M')

    monthly_ic = []
    for month in df_monthly['month'].unique():
        m = df_monthly[df_monthly['month'] == month]
        if len(m) >= 2:
            ic, _ = spearmanr(m['return'], m['signal'])
            monthly_ic.append(ic)

    ic_mean, t_stat = calculate_ic_t_stat(monthly_ic)

    print(f"\n数据概况:")
    print(f"  Non-overlapping 样本数: {len(signals)}")
    print(f"  时间范围: {pd.Timestamp(dates[0])} ~ {pd.Timestamp(dates[-1])}")

    print(f"\nIC 统计 (Non-overlapping):")
    print(f"  Spearman IC: {spearman_ic:.4f} (p={p_val:.4f})")
    print(f"  月度 IC 数量: {len(monthly_ic)}")
    print(f"  IC 均值: {ic_mean:.4f}")
    print(f"  IC t-stat: {t_stat:.4f}")

    return {
        'model': model_name,
        'ic': spearman_ic,
        'p_val': p_val,
        'ic_mean': ic_mean,
        't_stat': t_stat,
        'n_samples': len(signals),
        'n_months': len(monthly_ic)
    }


def main():
    """主函数."""
    print("="*60)
    print("IC 对比分析: v2 vs v3_fixed")
    print("="*60)

    # 分析 v2 (原始模型)
    result_v2 = analyze_model('experiments/weekly/weekly_bull_v27_orion_v2', 'v2 (原始)')

    # 分析 v3_fixed (修复后)
    result_v3 = analyze_model('experiments/weekly/weekly_bull_v27_orion_v3_fixed', 'v3_fixed (Scaler修复)')

    # 对比
    print(f"\n{'='*60}")
    print("对比总结")
    print(f"{'='*60}")

    print(f"\n| 指标 | v2 (原始) | v3_fixed (修复) | 变化 |")
    print(f"|------|-----------|-----------------|------|")
    print(f"| Spearman IC | {result_v2['ic']:.4f} | {result_v3['ic']:.4f} | {result_v3['ic'] - result_v2['ic']:+.4f} |")
    print(f"| p-value | {result_v2['p_val']:.4f} | {result_v3['p_val']:.4f} | {result_v3['p_val'] - result_v2['p_val']:+.4f} |")
    print(f"| IC t-stat | {result_v2['t_stat']:.4f} | {result_v3['t_stat']:.4f} | {result_v3['t_stat'] - result_v2['t_stat']:+.4f} |")

    # 结论
    print(f"\n结论:")
    if abs(result_v3['ic']) > 0.05 and result_v3['p_val'] < 0.05:
        print(f"  ✅ IC 仍然显著: {result_v3['ic']:.4f} (p={result_v3['p_val']:.4f})")
    else:
        print(f"  ⚠️ IC 不显著")

    if abs(result_v3['ic']) < abs(result_v2['ic']):
        print(f"  📉 IC 下降: {result_v2['ic']:.4f} → {result_v3['ic']:.4f}")
        print(f"  说明之前的 IC 可能包含 scaler 泄露")
    else:
        print(f"  📈 IC 上升或持平")


if __name__ == '__main__':
    main()
