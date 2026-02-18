#!/usr/bin/env python3
"""优化实验: 测试不同后处理策略.

测试:
1. 不同持仓冷却期 (7, 14, 21 天)
2. 不同信号阈值 (0.05, 0.08, 0.10, 0.12)
3. 仓位调节器 (连续仓位)
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import json
import numpy as np
import pandas as pd
from src.evaluation.pnl import calculate_pnl_metrics


def load_predictions(exp_dir):
    pred_df = pd.read_csv(f'{exp_dir}/predictions.csv')
    return pred_df


def load_prices_with_regime():
    prices_df = pd.read_csv('data/raw/btc_binance_BTCUSDT_1d.csv')
    prices_df['date'] = pd.to_datetime(prices_df['date'])
    prices_df = prices_df.sort_values('date').reset_index(drop=True)
    sma_200 = prices_df['close'].rolling(200).mean()
    prices_df['regime_bull'] = (prices_df['close'] > sma_200).astype(int)
    return prices_df


def run_backtest(y_pred, prices):
    pnl = calculate_pnl_metrics(
        y_true=np.zeros(len(y_pred)),
        y_pred=y_pred,
        prices=prices,
        position_size=1.0,
        transaction_cost=0.001,
    )
    return {'cagr': pnl.cagr, 'max_drawdown': pnl.max_drawdown, 'calmar': pnl.calmar, 'num_trades': pnl.num_trades}


def apply_hold_period(y_pred, min_hold_days):
    """应用持仓冷却期."""
    n = len(y_pred)
    result = np.zeros(n)
    current_pos = 0
    days_hold = 0

    for i in range(n):
        if days_hold < min_hold_days and current_pos != 0:
            result[i] = current_pos
            days_hold += 1
        else:
            result[i] = y_pred[i]
            current_pos = y_pred[i]
            days_hold = 0 if y_pred[i] != 0 else days_hold

    return result


def apply_position_sizer(y_pred, prices):
    """仓位调节器: 概率越高仓位越大."""
    n = len(y_pred)
    # 这里用 y_pred 本身作为概率近似
    # 1 -> 100%, 0 -> 0%
    return y_pred.astype(float)


def apply_regime_and_full(y_pred, prices, regime_bull):
    """完整优化: Regime + 冷却 + 50%仓位."""
    n = len(y_pred)
    result = np.zeros(n)
    current_pos = 0
    days_hold = 0

    for i in range(n):
        target = y_pred[i]

        # Regime 过滤
        if target == 1 and regime_bull[i] == 0:
            target = 0

        # 冷却 + 50%仓位
        if days_hold < 7 and current_pos != 0:
            result[i] = current_pos * 0.5
            days_hold += 1
        else:
            result[i] = target * 0.5
            current_pos = target
            days_hold = 0 if target != 0 else days_hold

    return result


def main():
    print("="*70)
    print("优化实验: 后处理策略对比")
    print("="*70)

    # 加载基准预测
    pred_df = load_predictions('experiments/weekly/weekly_bull_v27_orion_0218')
    prices_df = load_prices_with_regime()

    n = 1481
    y_bull = pred_df['y_pred'].values[:n]
    prices = prices_df['close'][:n]
    regime_bull = prices_df['regime_bull'].values[:n]

    results = {}

    # 基准
    print("\n[基准] 纯 Bull (1=多, 0=空)")
    r = run_backtest(y_bull, prices)
    print(f"    年化: {r['cagr']:>7.2%} | 回撤: {r['max_drawdown']:>8.2%} | 卡玛: {r['calmar']:.2f}")
    results['baseline'] = r

    # 1. 持仓冷却期
    print("\n[1] 持仓冷却期对比")
    for days in [7, 14, 21]:
        y = apply_hold_period(y_bull, days)
        r = run_backtest(y, prices)
        print(f"    {days}天: 年化 {r['cagr']:>7.2%} | 回撤 {r['max_drawdown']:>8.2%} | 卡玛 {r['calmar']:.2f}")
        results[f'hold_{days}d'] = r

    # 2. 完整优化
    print("\n[2] 完整优化 (Regime + 冷却7天 + 50%仓位)")
    y_full = apply_regime_and_full(y_bull, prices, regime_bull)
    r = run_backtest(y_full, prices)
    print(f"    年化: {r['cagr']:>7.2%} | 回撤: {r['max_drawdown']:>8.2%} | 卡玛: {r['calmar']:.2f}")
    results['full_optimized'] = r

    # 3. 完整优化 + 更长冷却期
    print("\n[3] 完整优化 + 14天冷却")
    y_full14 = apply_regime_and_full(y_bull, prices, regime_bull)
    y_full14 = apply_hold_period(y_full14, 14 - 7)  # 额外增加7天
    # 重新应用完整逻辑
    y_full14 = np.zeros(n)
    current_pos = 0
    days_hold = 0
    for i in range(n):
        target = y_bull[i]
        if target == 1 and regime_bull[i] == 0:
            target = 0
        if days_hold < 14 and current_pos != 0:
            y_full14[i] = current_pos * 0.5
            days_hold += 1
        else:
            y_full14[i] = target * 0.5
            current_pos = target
            days_hold = 0 if target != 0 else days_hold
    r = run_backtest(y_full14, prices)
    print(f"    年化: {r['cagr']:>7.2%} | 回撤: {r['max_drawdown']:>8.2%} | 卡玛: {r['calmar']:.2f}")
    results['full_14d'] = r

    # 保存
    os.makedirs('experiments/weekly/optimization_exp', exist_ok=True)
    with open('experiments/weekly/optimization_exp/results.json', 'w') as f:
        json.dump(results, f, indent=2)

    # 汇总
    print("\n" + "="*70)
    print("汇总")
    print("="*70)
    for name, r in results.items():
        print(f"{name:<20}: {r['cagr']:>7.2%} | {r['max_drawdown']:>8.2%} | {r['calmar']:.2f}")


if __name__ == '__main__':
    main()
