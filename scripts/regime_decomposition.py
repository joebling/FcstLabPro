#!/usr/bin/env python3
"""Regime 分解分析 (Layer 4).

分析不同市场状态下的 IC 表现:
- Bull (price > MA200)
- Bear (price < MA200)
- Sideway

如果信号在 bull 正，在 bear 负，必须显式建模。
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
from scipy.stats import spearmanr


def regime_decomposition():
    """Regime 分解分析."""

    print("=" * 60)
    print("Regime 分解分析 (Layer 4)")
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

    # 加载模型
    import joblib
    model = joblib.load('experiments/weekly/weekly_bull_v27_orion_v2/model.joblib')
    scaler = joblib.load('experiments/weekly/weekly_bull_v27_orion_v2/scaler.joblib')

    # 预测
    init_train = config['evaluation'].get('init_train', 1500)
    X_test = df[feature_cols].values[init_train:]
    timestamps = df.index[init_train:].values
    close_prices = df['close'].values[init_train:]

    X_test_scaled = scaler.transform(X_test)
    proba = model.predict_proba(X_test_scaled)[:, 1]

    # 创建分析 DataFrame
    df_analysis = pd.DataFrame({
        'close': close_prices,
        'proba': proba,
        'date': timestamps
    })

    # 计算 MA200 (需要更多历史数据)
    full_close = df['close'].values
    ma_period = 200
    ma = pd.Series(full_close).rolling(window=ma_period).mean().values

    # 取测试期间的 MA
    ma_test = ma[init_train:]

    # Regime 定义
    df_analysis['MA200'] = ma_test
    df_analysis['regime'] = np.where(
        df_analysis['close'] > df_analysis['MA200'] * 1.02, 'bull',
        np.where(df_analysis['close'] < df_analysis['MA200'] * 0.98, 'bear', 'sideway')
    )

    # 计算实际收益 (non-overlapping)
    step = 21
    signals = []
    returns = []
    regimes = []
    dates = []

    for i in range(0, len(proba) - step, step):
        signals.append(proba[i])
        ret = (close_prices[i + step] - close_prices[i]) / close_prices[i]
        returns.append(ret)
        regimes.append(df_analysis['regime'].iloc[i])
        dates.append(timestamps[i])

    signals = np.array(signals)
    returns = np.array(returns)
    regimes = np.array(regimes)

    print(f"\n数据概况:")
    print(f"  Non-overlapping 样本数: {len(signals)}")
    print(f"  时间范围: {pd.Timestamp(dates[0])} ~ {pd.Timestamp(dates[-1])}")

    # Regime 分布
    unique, counts = np.unique(regimes, return_counts=True)
    print(f"\nRegime 分布:")
    for regime, count in zip(unique, counts):
        print(f"  {regime}: {count} ({count/len(regimes)*100:.1f}%)")

    # 按 Regime 计算 IC
    print(f"\n" + "=" * 60)
    print("分 Regime IC 分析")
    print("=" * 60)

    regime_results = {}

    for regime in ['bull', 'bear', 'sideway']:
        mask = regimes == regime
        if mask.sum() >= 3:  # 至少 3 个样本
            regime_signals = signals[mask]
            regime_returns = returns[mask]

            ic, p_val = spearmanr(regime_returns, regime_signals)

            regime_results[regime] = {
                'ic': ic,
                'p_val': p_val,
                'n_samples': mask.sum(),
                'mean_return': regime_returns.mean(),
                'std_return': regime_returns.std()
            }

            print(f"\n{regime.upper()} (n={mask.sum()}):")
            print(f"  Spearman IC: {ic:.4f} (p={p_val:.4f})")
            print(f"  平均收益: {regime_returns.mean()*100:.2f}%")
            print(f"  收益标准差: {regime_returns.std()*100:.2f}%")

    # 整体 IC (用于对比)
    overall_ic, overall_p = spearmanr(returns, signals)
    print(f"\n" + "-" * 40)
    print(f"整体 IC: {overall_ic:.4f} (p={overall_p:.4f})")

    # 结论
    print(f"\n" + "=" * 60)
    print("结论")
    print("=" * 60)

    # 检查符号一致性
    if 'bull' in regime_results and 'bear' in regime_results:
        bull_ic = regime_results['bull']['ic']
        bear_ic = regime_results['bear']['ic']

        print(f"\n符号检查:")
        print(f"  Bull IC: {bull_ic:.4f}")
        print(f"  Bear IC: {bear_ic:.4f}")

        if bull_ic * bear_ic > 0:
            print("  ✅ 符号一致 - 信号在不同 regime 稳定")
        else:
            print("  ⚠️ 符号相反 - 需要 Regime Switching 建模")

    # 检查 IC 强度
    print(f"\nIC 强度检查:")
    for regime, result in regime_results.items():
        if abs(result['ic']) > 0.1:
            strength = "强"
        elif abs(result['ic']) > 0.05:
            strength = "中等"
        else:
            strength = "弱"

        print(f"  {regime}: {strength} (IC={result['ic']:.4f})")

    # 保存结果
    output_dir = Path('experiments/weekly/regime_decomposition')
    output_dir.mkdir(parents=True, exist_ok=True)

    # 保存 regime 结果
    regime_df = pd.DataFrame(regime_results).T
    regime_df.to_csv(output_dir / 'regime_ic.csv')

    # 生成报告
    report = f"""# Regime 分解分析报告 (Layer 4)

## 数据概况
- Non-overlapping 样本数: {len(signals)}
- 时间范围: {pd.Timestamp(dates[0])} ~ {pd.Timestamp(dates[-1])}

## Regime 分布
"""

    for regime, count in zip(unique, counts):
        report += f"- {regime}: {count} ({count/len(regimes)*100:.1f}%)\n"

    report += f"""
## 分 Regime IC 分析

| Regime | IC | p-value | 样本数 | 平均收益 |
|--------|-----|---------|--------|----------|
"""

    for regime, result in regime_results.items():
        report += f"| {regime} | {result['ic']:.4f} | {result['p_val']:.4f} | {result['n_samples']} | {result['mean_return']*100:.2f}% |\n"

    report += f"""
## 整体 IC
- IC: {overall_ic:.4f} (p={overall_p:.4f})

## 结论
"""

    # 符号一致性
    if 'bull' in regime_results and 'bear' in regime_results:
        bull_ic = regime_results['bull']['ic']
        bear_ic = regime_results['bear']['ic']
        if bull_ic * bear_ic > 0:
            report += "- ✅ 符号一致 - 信号在不同 regime 稳定\n"
        else:
            report += "- ⚠️ 符号相反 - 需要 Regime Switching 建模\n"

    with open(output_dir / 'report.md', 'w') as f:
        f.write(report)

    print(f"\n报告已保存到: {output_dir}")

    return regime_results


if __name__ == '__main__':
    regime_decomposition()
