#!/usr/bin/env python3
"""Hybrid A/B Test (Layer 5).

对比不同 MA 过滤策略:
- Triple MA
- MA200
- Volatility Filter
- No Filter (baseline)

符合 CLAUDE.md 规范，保存到 experiments/weekly/
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import yaml
import json

from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns
import src.labels.reversal
from src.labels.registry import get_label_strategy


def calculate_metrics(returns):
    """计算回测指标."""
    if len(returns) == 0:
        return {
            'total_return': 0, 'annualized': 0, 'max_drawdown': 0,
            'sharpe': 0, 'calmar': 0, 'n_trades': 0
        }

    # 复利计算
    total_return = np.prod(1 + returns) - 1
    n_days = len(returns) * 21  # 假设每次持仓21天
    annualized = (1 + total_return) ** (365 / n_days) - 1

    # 最大回撤
    cumulative = np.cumprod(1 + returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = abs(drawdown.min()) if len(drawdown) > 0 else 0

    # Sharpe
    sharpe = np.mean(returns) / (np.std(returns) + 1e-10) * np.sqrt(365 / 21) if np.std(returns) > 0 else 0

    # Calmar
    calmar = annualized / (max_drawdown + 1e-10) if max_drawdown > 0 else 0

    return {
        'total_return': total_return,
        'annualized': annualized,
        'max_drawdown': max_drawdown,
        'sharpe': sharpe,
        'calmar': calmar,
        'n_trades': len(returns),
    }


def run_strategy(df, proba, holding_days=21, transaction_cost=0.0004, slippage=0.001, filter_func=None):
    """策略回测.

    Args:
        df: 特征数据
        proba: 预测概率
        holding_days: 持仓天数
        transaction_cost: 交易成本
        slippage: 滑点
        filter_func: 过滤函数 (可选)
    """
    close = df['close'].values
    dates = df.index

    # 信号: prob < 0.5 时买入 (反转)
    base_signal = (proba < 0.5).astype(int)

    # 应用过滤
    if filter_func is not None:
        filter_mask = filter_func(df)
        base_signal = base_signal & filter_mask

    returns = []
    position = 0
    entry_price = 0
    entry_idx = 0
    trade_log = []

    for i in range(len(base_signal)):
        if position == 0 and base_signal[i]:
            # 买入 - 添加滑点
            position = 1
            entry_price = close[i] * (1 + slippage)
            entry_idx = i

        elif position == 1:
            days_held = i - entry_idx
            if days_held >= holding_days:
                # 卖出 - 添加滑点
                ret = (close[i] * (1 - slippage) - entry_price) / entry_price - transaction_cost * 2
                returns.append(ret)
                trade_log.append({
                    'entry_date': str(dates[entry_idx]),
                    'exit_date': str(dates[i]),
                    'return': ret
                })
                position = 0

    return np.array(returns) if returns else np.array([0]), trade_log


def run_ab_test():
    """A/B 测试主函数."""

    print("=" * 60)
    print("Hybrid A/B Test (Layer 5)")
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
    df_test = df.iloc[init_train:].copy()
    X_test_scaled = scaler.transform(X_test)
    proba = model.predict_proba(X_test_scaled)[:, 1]

    print(f"测试集: {len(proba)} 样本")

    # 定义过滤函数
    def triple_ma_filter(df):
        """三重 MA 过滤."""
        close = df['close'].values
        ma50 = pd.Series(close).rolling(50).mean().values
        ma100 = pd.Series(close).rolling(100).mean().values
        ma200 = pd.Series(close).rolling(200).mean().values

        # 价格 > MA50 > MA100 > MA200 (上升趋势)
        trend = (close > ma50) & (ma50 > ma100) & (ma100 > ma200)

        # MA50 向上
        ma50_up = pd.Series(ma50).diff() > 0

        return (trend | ma50_up).astype(int)

    def ma200_filter(df):
        """MA200 过滤."""
        close = df['close'].values
        ma200 = pd.Series(close).rolling(200).mean().values
        return (close > ma200).astype(int)

    def vol_filter(df, threshold=0.6):
        """波动率过滤."""
        close = df['close'].values
        vol = pd.Series(close).pct_change().rolling(21).std()
        vol_percentile = vol.rolling(63).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False)
        return (vol_percentile < threshold).astype(int)

    def no_filter(df):
        """无过滤."""
        return np.ones(len(df), dtype=int)

    # 运行测试
    strategies = {
        'A: Triple MA': triple_ma_filter,
        'B: MA200': ma200_filter,
        'C: Vol Filter': lambda df: vol_filter(df, threshold=0.6),
        'D: No Filter': no_filter,
    }

    results = []

    print(f"\n" + "=" * 60)
    print("A/B 测试结果")
    print("=" * 60)

    for name, filter_func in strategies.items():
        returns, trades = run_strategy(
            df_test, proba,
            holding_days=21,
            transaction_cost=0.0004,
            slippage=0.001,
            filter_func=filter_func
        )

        metrics = calculate_metrics(returns)
        results.append({
            'strategy': name,
            **metrics,
            'trades': trades
        })

        print(f"\n{name}:")
        print(f"  交易次数: {metrics['n_trades']}")
        print(f"  总收益: {metrics['total_return']:.2%}")
        print(f"  年化收益: {metrics['annualized']:.2%}")
        print(f"  Sharpe: {metrics['sharpe']:.2f}")
        print(f"  Calmar: {metrics['calmar']:.2f}")
        print(f"  最大回撤: {metrics['max_drawdown']:.2%}")

    # 保存结果
    output_dir = Path('experiments/weekly/hybrid_ab_test')
    output_dir.mkdir(parents=True, exist_ok=True)

    # 简化结果 (不保存 trades)
    results_simple = []
    for r in results:
        result_simple = {
            'strategy': r['strategy'],
            'n_trades': r['n_trades'],
            'total_return': r['total_return'],
            'annualized': r['annualized'],
            'sharpe': r['sharpe'],
            'calmar': r['calmar'],
            'max_drawdown': r['max_drawdown'],
        }
        results_simple.append(result_simple)

    # 保存为 CSV
    results_df = pd.DataFrame(results_simple)
    results_df.to_csv(output_dir / 'ab_test_results.csv', index=False)

    # 保存为 JSON
    with open(output_dir / 'ab_test_results.json', 'w') as f:
        json.dump(results_simple, f, indent=2)

    # 生成报告
    report = f"""# Hybrid A/B Test 报告 (Layer 5)

## 测试时间
- 测试集: {len(proba)} 样本
- 持仓期: 21 天
- 滑点: 0.1%
- 交易成本: 0.04%

## 结果对比

| 策略 | 交易次数 | 年化收益 | Sharpe | Calmar | 最大回撤 |
|------|----------|----------|--------|--------|----------|
"""

    for r in results_simple:
        report += f"| {r['strategy']} | {r['n_trades']} | {r['annualized']:.2%} | {r['sharpe']:.2f} | {r['calmar']:.2f} | {r['max_drawdown']:.2%} |\n"

    # 找出最佳策略
    best = max(results_simple, key=lambda x: x['sharpe'])
    report += f"""
## 最佳策略
- {best['strategy']}: Sharpe={best['sharpe']:.2f}

## 结论
"""

    if best['annualized'] > 0:
        report += f"- ✅ 年化收益为正: {best['annualized']:.2%}\n"
    else:
        report += f"- ⚠️ 年化收益为负\n"

    if best['max_drawdown'] < 0.25:
        report += f"- ✅ 最大回撤可控: {best['max_drawdown']:.2%}\n"
    else:
        report += f"- ⚠️ 最大回撤过大\n"

    if best['sharpe'] > 1.0:
        report += f"- ✅ Sharpe > 1.0\n"
    else:
        report += f"- ⚠️ Sharpe < 1.0\n"

    with open(output_dir / 'report.md', 'w') as f:
        f.write(report)

    print(f"\n结果已保存到: {output_dir}")

    return results_simple


if __name__ == '__main__':
    run_ab_test()
