#!/usr/bin/env python3
"""综合回测: Bull + Bear 模型组合."""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import json
import numpy as np
import pandas as pd
from src.evaluation.pnl import calculate_pnl_metrics


def load_predictions(bull_dir, bear_dir):
    bull_pred = pd.read_csv(f'{bull_dir}/predictions.csv')
    bear_pred = pd.read_csv(f'{bear_dir}/predictions.csv')
    return bull_pred, bear_pred


def load_prices_with_regime():
    prices_df = pd.read_csv('data/raw/btc_binance_BTCUSDT_1d.csv')
    prices_df['date'] = pd.to_datetime(prices_df['date'])
    prices_df = prices_df.sort_values('date').reset_index(drop=True)
    sma_200 = prices_df['close'].rolling(200).mean()
    prices_df['regime_bull'] = (prices_df['close'] > sma_200).astype(int)
    return prices_df


def run_backtest(y_pred, prices):
    """使用 pnl.py 计算回测 (支持 -1 做空)."""
    pnl = calculate_pnl_metrics(
        y_true=np.zeros(len(y_pred)),
        y_pred=y_pred,
        prices=prices,
        position_size=1.0,
        transaction_cost=0.001,
    )
    return {
        'cagr': pnl.cagr,
        'max_drawdown': pnl.max_drawdown,
        'calmar': pnl.calmar,
        'num_trades': pnl.num_trades,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--bull-dir', type=str, default='experiments/weekly/weekly_bull_v27_orion_0218')
    parser.add_argument('--bear-dir', type=str, default='experiments/weekly/weekly_bear_v13_T28_fgi_20260215_134804_ff4ad7')
    parser.add_argument('--output', type=str, default='experiments/weekly/combined_backtest')
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    print("="*70)
    print("综合回测: Bull + Bear 模型")
    print("="*70)

    # 加载数据
    bull_pred, bear_pred = load_predictions(args.bull_dir, args.bear_dir)
    prices_df = load_prices_with_regime()

    # 对齐数据 (取前 1481 条)
    n = 1481
    y_bull = bull_pred['y_pred'].values[:n]
    y_bear = bear_pred['y_pred'].values[:n]
    prices = prices_df['close'][:n]
    regime_bull = prices_df['regime_bull'].values[:n]

    print(f"样本数: {n}")
    print(f"Bull: 0={np.sum(y_bull==0)}, 1={np.sum(y_bull==1)}")
    print(f"Bear: 0={np.sum(y_bear==0)}, 1={np.sum(y_bear==1)}")

    results = {}

    # 1. 纯 Bull (与报告一致)
    print("\n[1] 纯 Bull (1=多, 0=空) - 基准")
    y_pure_bull = y_bull.astype(float)
    r1 = run_backtest(y_pure_bull, prices)
    print(f"    年化: {r1['cagr']:>7.2%} | 回撤: {r1['max_drawdown']:>8.2%} | 卡玛: {r1['calmar']:.2f}")
    results['pure_bull'] = r1

    # 2. Bull + Bear 组合
    print("\n[2] Bull + Bear (Bull=1→多, Bear=1→空, 否则→空)")
    y_combined = np.zeros(n)
    for i in range(n):
        if y_bull[i] == 1 and y_bear[i] == 0:
            y_combined[i] = 1
        elif y_bear[i] == 1:
            y_combined[i] = -1
        else:
            y_combined[i] = 0
    r2 = run_backtest(y_combined, prices)
    print(f"    年化: {r2['cagr']:>7.2%} | 回撤: {r2['max_drawdown']:>8.2%} | 卡玛: {r2['calmar']:.2f}")
    results['bull_bear'] = r2

    # 3. Bull + Bear + Regime
    print("\n[3] Bull + Bear + Regime Gating")
    y_regime = np.zeros(n)
    for i in range(n):
        if y_bull[i] == 1 and y_bear[i] == 0 and regime_bull[i] == 1:
            y_regime[i] = 1
        elif y_bear[i] == 1 and regime_bull[i] == 0:
            y_regime[i] = -1
        else:
            y_regime[i] = 0
    r3 = run_backtest(y_regime, prices)
    print(f"    年化: {r3['cagr']:>7.2%} | 回撤: {r3['max_drawdown']:>8.2%} | 卡玛: {r3['calmar']:.2f}")
    results['with_regime'] = r3

    # 4. Bull + Bear + 冷却
    print("\n[4] Bull + Bear + 持仓冷却 (7天)")
    y_cooling = np.zeros(n)
    current_pos = 0
    days_hold = 0
    for i in range(n):
        if y_bull[i] == 1 and y_bear[i] == 0:
            target = 1
        elif y_bear[i] == 1:
            target = -1
        else:
            target = 0

        if days_hold < 7 and current_pos != 0:
            y_cooling[i] = current_pos
            days_hold += 1
        else:
            y_cooling[i] = target
            current_pos = target
            days_hold = 0 if target != 0 else days_hold

    r4 = run_backtest(y_cooling, prices)
    print(f"    年化: {r4['cagr']:>7.2%} | 回撤: {r4['max_drawdown']:>8.2%} | 卡玛: {r4['calmar']:.2f}")
    results['with_cooling'] = r4

    # 5. 完整优化
    print("\n[5] 完整优化: 冷却 + Regime + 50%仓位")
    y_full = np.zeros(n)
    current_pos = 0
    days_hold = 0
    for i in range(n):
        if y_bull[i] == 1 and y_bear[i] == 0:
            target = 1
        elif y_bear[i] == 1:
            target = -1
        else:
            target = 0

        # Regime
        if target == 1 and regime_bull[i] == 0:
            target = 0
        if target == -1 and regime_bull[i] == 1:
            target = 0

        # 冷却 + 50%仓位
        if days_hold < 7 and current_pos != 0:
            y_full[i] = current_pos * 0.5
            days_hold += 1
        else:
            y_full[i] = target * 0.5
            current_pos = target
            days_hold = 0 if target != 0 else days_hold

    r5 = run_backtest(y_full, prices)
    print(f"    年化: {r5['cagr']:>7.2%} | 回撤: {r5['max_drawdown']:>8.2%} | 卡玛: {r5['calmar']:.2f}")
    results['full_optimized'] = r5

    # 保存
    with open(f'{args.output}/backtest_final.json', 'w') as f:
        json.dump(results, f, indent=2)

    print("\n" + "="*70)
    print("汇总")
    print("="*70)
    for name, r in results.items():
        print(f"{name:<20}: {r['cagr']:>7.2%} | {r['max_drawdown']:>8.2%} | {r['calmar']:.2f}")


if __name__ == '__main__':
    main()
