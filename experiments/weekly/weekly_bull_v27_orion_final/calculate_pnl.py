import sys
import os

sys.path.insert(0, os.path.abspath('.'))

import pandas as pd
import numpy as np
from src.evaluation.pnl import calculate_pnl_metrics

def main():
    print("="*80)
    print("计算 Orion-BiX v27 年化收益")
    print("="*80)
    
    predictions_path = 'experiments/weekly/weekly_bull_v27_orion_final/predictions.csv'
    prices_path = 'data/raw/btc_binance_BTCUSDT_1d.csv'
    
    print(f"\n加载预测数据: {predictions_path}")
    pred_df = pd.read_csv(predictions_path)
    print(f"预测样本数: {len(pred_df)}")
    print(f"预测列: {pred_df.columns.tolist()}")
    print(f"标签分布: {pred_df['y_true'].value_counts().to_dict()}")
    print(f"预测分布: {pred_df['y_pred'].value_counts().to_dict()}")
    
    print(f"\n加载价格数据: {prices_path}")
    prices_df = pd.read_csv(prices_path)
    prices_df['date'] = pd.to_datetime(prices_df['date'])
    prices_df = prices_df.sort_values('date').reset_index(drop=True)
    prices = prices_df['close']
    print(f"价格数据点数: {len(prices)}")
    
    n_samples = len(pred_df)
    n_prices = len(prices)
    min_len = min(n_samples, n_prices)
    
    print(f"\n对齐数据: {min_len} 个样本")
    y_true = pred_df['y_true'].values[:min_len]
    y_pred = pred_df['y_pred'].values[:min_len]
    prices_aligned = prices.iloc[:min_len]
    
    print(f"\n运行 PnL 回测...")
    metrics = calculate_pnl_metrics(
        y_true=y_true,
        y_pred=y_pred,
        prices=prices_aligned,
        position_size=1.0,
        transaction_cost=0.001,
        risk_free_rate=0.0,
        periods_per_year=52.0,
    )
    
    print(f"\n{'='*80}")
    print("Orion-BiX v27 PnL 回测结果")
    print(f"{'='*80}")
    print(f"  总收益: {metrics.total_return:.2%}")
    print(f"  年化收益 (CAGR): {metrics.cagr:.2%}")
    print(f"  夏普比率: {metrics.sharpe:.2f}")
    print(f"  索提诺比率: {metrics.sortino:.2f}")
    print(f"  最大回撤: {metrics.max_drawdown:.2%}")
    print(f"  卡玛比率: {metrics.calmar:.2f}")
    print(f"  胜率: {metrics.win_rate:.2%}")
    print(f"  盈亏比: {metrics.profit_factor:.2f}")
    print(f"  交易次数: {metrics.num_trades}")
    print(f"{'='*80}")

if __name__ == '__main__':
    main()
