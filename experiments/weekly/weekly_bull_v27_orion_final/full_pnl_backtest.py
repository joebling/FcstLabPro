import sys
import os

sys.path.insert(0, os.path.abspath('.'))

import pandas as pd
import numpy as np
from src.evaluation.pnl import calculate_pnl_metrics

def load_model_predictions(model_path):
    predictions_df = pd.read_csv(model_path)
    return predictions_df['y_true'].values, predictions_df['y_pred'].values

def load_prices():
    prices_df = pd.read_csv('data/raw/btc_binance_BTCUSDT_1d.csv')
    prices_df['date'] = pd.to_datetime(prices_df['date'])
    prices_df = prices_df.sort_values('date').reset_index(drop=True)
    return prices_df['close']

def run_backtest_for_model(model_name, y_true, y_pred, prices):
    print(f"\n{'='*80}")
    print(f"模型: {model_name}")
    print(f"{'='*80}")
    
    n_samples = len(y_true)
    n_prices = len(prices)
    
    print(f"预测样本数: {n_samples}")
    print(f"价格数据点数: {n_prices}")
    
    min_len = min(n_samples, n_prices)
    y_true = y_true[:min_len]
    y_pred = y_pred[:min_len]
    prices_aligned = prices.iloc[:min_len]
    print(f"对齐后: {len(y_true)} 个样本")
    
    metrics = calculate_pnl_metrics(
        y_true=y_true,
        y_pred=y_pred,
        prices=prices_aligned,
        position_size=1.0,
        transaction_cost=0.001,
        risk_free_rate=0.0,
        periods_per_year=52.0,
    )
    
    print(f"\nPnL 指标:")
    print(f"  总收益: {metrics.total_return:.2%}")
    print(f"  年化收益 (CAGR): {metrics.cagr:.2%}")
    print(f"  夏普比率: {metrics.sharpe:.2f}")
    print(f"  索提诺比率: {metrics.sortino:.2f}")
    print(f"  最大回撤: {metrics.max_drawdown:.2%}")
    print(f"  卡玛比率: {metrics.calmar:.2f}")
    print(f"  胜率: {metrics.win_rate:.2%}")
    print(f"  盈亏比: {metrics.profit_factor:.2f}")
    print(f"  交易次数: {metrics.num_trades}")
    
    return metrics

def main():
    print("="*80)
    print("完整 PnL 回测复现")
    print("="*80)
    
    prices = load_prices()
    
    models = [
        {
            'name': 'GBDT v15 (Bull)',
            'path': 'experiments/weekly/weekly_bull_v15_regime_20260215_142329_b42efc/predictions.csv'
        },
        {
            'name': 'GBDT v13 (Bear)',
            'path': 'experiments/weekly/weekly_bear_v13_T28_fgi_20260215_134804_ff4ad7/predictions.csv'
        }
    ]
    
    results = {}
    for model in models:
        try:
            y_true, y_pred = load_model_predictions(model['path'])
            results[model['name']] = run_backtest_for_model(model['name'], y_true, y_pred, prices)
        except Exception as e:
            print(f"\n⚠️  模型 {model['name']} 回测失败: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*80}")
    print("对比总结")
    print(f"{'='*80}")
    print(f"\n| 模型 | 年化收益 | 最大回撤 | 卡玛比率 | 夏普比率 |")
    print(f"|------|----------|----------|----------|----------|")
    
    for name, metrics in results.items():
        print(f"| {name} | {metrics.cagr:+.2%} | {metrics.max_drawdown:.2%} | {metrics.calmar:.2f} | {metrics.sharpe:.2f} |")
    
    print(f"\n{'='*80}")
    print("与部署报告对比")
    print(f"{'='*80}")
    print("\n部署报告中的结果:")
    print("| 指标 | GBDT v15 | Orion-BiX v27 | 差异 |")
    print("|------|----------|----------------|------|")
    print("| 平均 Kappa | 0.1756 | 0.1122 | -0.0634 |")
    print("| 正 Kappa 比例 | 92.3% | 69.6% | -22.7% |")
    print("| 年化收益 | -11.00% | +26.63% | +37.63% |")
    print("| 平均最大回撤 | 20.57% | 17.45% | -3.12% |")
    print("| 卡玛比率 | -0.53 | +1.53 | +2.06 |")
    print("| 夏普比率 | 0.03 | +0.80 | +0.77 |")

if __name__ == '__main__':
    main()
