#!/usr/bin/env python3
"""PM级分析：资本利用率 + 贡献分解 + 极端行情 + 成本压力测试."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import yaml
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings('ignore')

from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier

from src.labels.registry import get_label_strategy
from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns
from src.backtest import BacktestEngine, TriggerA, TP_SL_Exit, calculate_metrics

print("=" * 80)
print("exp11_pm_analysis: PM级综合分析")
print("=" * 80)

DATA_PATH = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"
BASE_CONFIG_PATH = PROJECT_ROOT / "configs" / "experiments" / "weekly" / "exp_weekly_bull_v27_orion_v4_extended_oos.yaml"

with open(BASE_CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)

print("\n1. 加载数据...")
df = load_csv(str(DATA_PATH))
df = build_features(
    df,
    feature_sets=config['features']['sets'],
    drop_na_method=config['features'].get('drop_na_method', 'ffill_then_drop'),
)

feature_cols = get_feature_columns(df)
close_prices = df['close'].values
df_dates = df.index

T = 21
init_train = 800
oos_window = 63
step = 21
purge_gap = 21

print("\n2. 生成 dip_recovery label...")
label_func = get_label_strategy("dip_recovery")
labels = label_func(df, T=T, dip_threshold=0.05, recovery_threshold=0.03)
valid_labels = labels.dropna()
valid_idx = valid_labels.index
X_valid = df.loc[valid_idx, feature_cols].values
y_valid = valid_labels.values
aligned_close = df.loc[valid_idx, 'close'].values
aligned_dates = df.loc[valid_idx].index

print(f"\n   样本数: {len(y_valid)}")
print(f"   正样本: {y_valid.sum():.0f} ({y_valid.mean():.1%})")

print("\n3. 运行 walk-forward 并收集 y_proba...")

def run_walk_forward_collect_proba(X, y, close_prices_aligned):
    """运行 walk-forward，收集 y_proba 和 close 价格."""
    all_y_proba = []
    all_close = []
    all_dates = []
    
    t = init_train
    while t + oos_window <= len(X):
        train_end = t - purge_gap
        if train_end <= 0:
            t += step
            continue
            
        X_train = X[:train_end]
        y_train = y[:train_end]
        X_test = X[t:t+oos_window]
        close_test = close_prices_aligned[t:t+oos_window]
        dates_test = aligned_dates[t:t+oos_window]
        
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        if len(np.unique(y_train)) < 2:
            t += step
            continue
            
        model = RandomForestClassifier(
            n_estimators=100,
            max_depth=6,
            random_state=42,
            n_jobs=-1
        )
        model.fit(X_train_scaled, y_train)
        
        if len(model.classes_) == 2:
            y_proba = model.predict_proba(X_test_scaled)[:, 1]
        else:
            y_proba = np.zeros(len(X_test))
        
        all_y_proba.extend(y_proba)
        all_close.extend(close_test)
        all_dates.extend(dates_test)
        
        t += step
    
    return np.array(all_y_proba), np.array(all_close), np.array(all_dates)

y_proba, close_prices_collected, dates_collected = run_walk_forward_collect_proba(
    X_valid, y_valid, aligned_close
)

print(f"   收集了 {len(y_proba)} 个时点的数据")
print(f"   时间范围: {dates_collected[0]} 到 {dates_collected[-1]}")

print("\n4. 使用 exp03 的最佳参数...")
best_params = {
    'prob_threshold': 0.8,
    'dip_threshold': 0.05,
    'tp': 0.04,
    'sl': 0.03,
    'monitor_days': 7
}
print("\n   最佳参数:")
for k, v in best_params.items():
    print(f"   {k}: {v}")

print("\n5. 定义策略...")

def position_sizer_linear(prob):
    size = 2 * (prob - 0.5)
    return max(0.0, min(size, 1.0))

class TrendStrategy:
    """简单趋势策略（MA50+MA200）."""
    
    def __init__(self, ma_short=50, ma_long=200):
        self.ma_short = ma_short
        self.ma_long = ma_long
    
    def should_enter(self, i, close_prices):
        if i < self.ma_long:
            return False
        ma_short = np.mean(close_prices[i-self.ma_short:i])
        ma_long = np.mean(close_prices[i-self.ma_long:i])
        current_price = close_prices[i]
        return current_price > ma_short and current_price > ma_long
    
    def should_exit(self, i, close_prices):
        if i < self.ma_short:
            return True
        ma_short = np.mean(close_prices[i-self.ma_short:i])
        current_price = close_prices[i]
        return current_price < ma_short

def calculate_trend_pnl(close_prices):
    """趋势策略PnL."""
    n = len(close_prices)
    positions = np.zeros(n)
    current_position = 0
    
    trend = TrendStrategy(ma_short=50, ma_long=200)
    
    for i in range(n):
        if current_position == 0:
            if trend.should_enter(i, close_prices):
                positions[i] = 1.0
                current_position = 1.0
        else:
            positions[i] = current_position
            if trend.should_exit(i, close_prices):
                positions[i] = 0.0
                current_position = 0.0
    
    returns = []
    for i in range(n - 1):
        ret = (close_prices[i+1] - close_prices[i]) / close_prices[i]
        returns.append(positions[i] * ret)
    
    returns = np.array(returns)
    
    if len(returns) == 0:
        return {
            'sharpe': 0,
            'total_return': 0,
            'max_dd': 0,
            'positions': positions,
            'returns': returns
        }
    
    annual_factor = 252 / len(returns) if len(returns) > 0 else 252
    annual_return = np.mean(returns) * annual_factor
    annual_vol = np.std(returns) * np.sqrt(annual_factor)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0
    
    cumulative = (1 + returns).cumprod()
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    max_dd = np.min(drawdown) if len(drawdown) > 0 else 0
    
    total_return = cumulative[-1] - 1 if len(cumulative) > 0 else 0
    
    return {
        'sharpe': sharpe,
        'total_return': total_return,
        'max_dd': max_dd,
        'annual_return': annual_return,
        'annual_vol': annual_vol,
        'positions': positions,
        'returns': returns,
        'cumulative': cumulative
    }

print("\n6. 运行 MR 策略回测...")
engine = BacktestEngine(close_prices_collected, y_proba)
trigger = TriggerA(
    prob_threshold=best_params['prob_threshold'],
    dip_threshold=best_params['dip_threshold'],
    monitor_days=best_params['monitor_days']
)
exit_strategy = TP_SL_Exit(
    tp=best_params['tp'],
    sl=best_params['sl'],
    time_stop=14
)
result_mr = engine.run(trigger, exit_strategy, position_sizer=position_sizer_linear)
metrics_mr = calculate_metrics(result_mr['returns'], result_mr['cumulative'])

print(f"   MR 策略:")
print(f"   Sharpe: {metrics_mr['sharpe']:.4f}")
print(f"   总收益: {metrics_mr['total_return']:.4f}")
print(f"   MaxDD: {metrics_mr['max_dd']:.4f}")

print("\n7. 运行 Trend 策略回测...")
result_trend = calculate_trend_pnl(close_prices_collected)

print(f"   Trend 策略:")
print(f"   Sharpe: {result_trend['sharpe']:.4f}")
print(f"   总收益: {result_trend['total_return']:.4f}")
print(f"   MaxDD: {result_trend['max_dd']:.4f}")

print("\n8. 分析 1: 资本利用率...")

average_exposure_mr = np.mean(np.abs(result_mr['positions']))
time_in_market_mr = np.mean(result_mr['positions'] != 0)

print(f"\n   MR 策略:")
print(f"   平均风险暴露: {average_exposure_mr*100:.1f}%")
print(f"   市场停留时间: {time_in_market_mr*100:.1f}%")

average_exposure_trend = np.mean(np.abs(result_trend['positions']))
time_in_market_trend = np.mean(result_trend['positions'] != 0)

print(f"\n   Trend 策略:")
print(f"   平均风险暴露: {average_exposure_trend*100:.1f}%")
print(f"   市场停留时间: {time_in_market_trend*100:.1f}%")

print("\n9. 分析 2: 极端行情测试...")

dates_np = np.array(dates_collected)
bear_start_idx = np.where(dates_np >= pd.Timestamp('2022-01-01'))[0]
bear_end_idx = np.where(dates_np <= pd.Timestamp('2023-01-01'))[0]

bear_metrics = {}
trend_bear_metrics = {}
if len(bear_start_idx) > 0 and len(bear_end_idx) > 0:
    bear_start = bear_start_idx[0]
    bear_end = bear_end_idx[-1]
    if bear_start < bear_end and bear_end < len(result_mr['returns']):
        returns_bear_mr = result_mr['returns'][bear_start:bear_end]
        cumulative_bear_mr = (1 + returns_bear_mr).cumprod()
        total_return_bear_mr = cumulative_bear_mr[-1] - 1 if len(cumulative_bear_mr) > 0 else 0
        
        returns_bear_trend = result_trend['returns'][bear_start:bear_end]
        cumulative_bear_trend = (1 + returns_bear_trend).cumprod()
        total_return_bear_trend = cumulative_bear_trend[-1] - 1 if len(cumulative_bear_trend) > 0 else 0
        
        bear_metrics = {
            'start': dates_collected[bear_start],
            'end': dates_collected[bear_end],
            'mr_return': total_return_bear_mr,
            'trend_return': total_return_bear_trend
        }
        print(f"\n   2022 熊市 ({dates_collected[bear_start]} 到 {dates_collected[bear_end]}):")
        print(f"   MR 收益: {total_return_bear_mr*100:.1f}%")
        print(f"   Trend 收益: {total_return_bear_trend*100:.1f}%")

bull_start_idx = np.where(dates_np >= pd.Timestamp('2024-01-01'))[0]
bull_end_idx = np.where(dates_np <= pd.Timestamp('2025-01-01'))[0]

bull_metrics = {}
trend_bull_metrics = {}
if len(bull_start_idx) > 0 and len(bull_end_idx) > 0:
    bull_start = bull_start_idx[0]
    bull_end = bull_end_idx[-1]
    if bull_start < bull_end and bull_end < len(result_mr['returns']):
        returns_bull_mr = result_mr['returns'][bull_start:bull_end]
        cumulative_bull_mr = (1 + returns_bull_mr).cumprod()
        total_return_bull_mr = cumulative_bull_mr[-1] - 1 if len(cumulative_bull_mr) > 0 else 0
        
        returns_bull_trend = result_trend['returns'][bull_start:bull_end]
        cumulative_bull_trend = (1 + returns_bull_trend).cumprod()
        total_return_bull_trend = cumulative_bull_trend[-1] - 1 if len(cumulative_bull_trend) > 0 else 0
        
        bull_metrics = {
            'start': dates_collected[bull_start],
            'end': dates_collected[bull_end],
            'mr_return': total_return_bull_mr,
            'trend_return': total_return_bull_trend
        }
        print(f"\n   2024 牛市 ({dates_collected[bull_start]} 到 {dates_collected[bull_end]}):")
        print(f"   MR 收益: {total_return_bull_mr*100:.1f}%")
        print(f"   Trend 收益: {total_return_bull_trend*100:.1f}%")

print("\n10. 分析 3: 成本压力测试...")

fee_scenarios = [
    {'name': 'C1_no_cost', 'fee': 0.0, 'slippage': 0.0, 'label': '无成本'},
    {'name': 'C2_realistic', 'fee': 0.001, 'slippage': 0.001, 'label': '实际(各0.1%)'},
    {'name': 'C3_double', 'fee': 0.002, 'slippage': 0.002, 'label': '×2'},
    {'name': 'C4_stress', 'fee': 0.005, 'slippage': 0.005, 'label': '压力测试(各0.5%)'},
]

def calculate_with_costs(returns, positions, fee, slippage):
    n = len(returns)
    new_returns = returns.copy()
    
    for i in range(1, n):
        if positions[i] != positions[i-1]:
            cost = fee + slippage
            if positions[i-1] != 0:
                new_returns[i-1] -= cost * abs(positions[i] - positions[i-1])
    
    return new_returns

cost_results = []
for scenario in fee_scenarios:
    returns_with_cost = calculate_with_costs(
        result_mr['returns'], result_mr['positions'],
        scenario['fee'], scenario['slippage']
    )
    
    if len(returns_with_cost) > 0:
        cumulative = (1 + returns_with_cost).cumprod()
        metrics_cost = calculate_metrics(returns_with_cost, cumulative)
        
        cost_results.append({
            'scenario': scenario['name'],
            'label': scenario['label'],
            'sharpe': metrics_cost['sharpe'],
            'total_return': metrics_cost['total_return'],
            'max_dd': metrics_cost['max_dd'],
            'annual_return': metrics_cost['annual_return'],
            'annual_vol': metrics_cost['annual_vol']
        })

print(f"\n   成本压力测试结果:")
for res in cost_results:
    print(f"   {res['label']}: Sharpe={res['sharpe']:.4f}, 收益={res['total_return']:.4f}, MaxDD={res['max_dd']:.4f}")

print("\n11. 分析 4: Regime-Switching 组合...")

def calculate_regime_switch_soft(close_prices, prob_scores, mr_positions, trend_positions):
    """软切换组合策略."""
    n = len(close_prices)
    positions = np.zeros(n)
    
    for i in range(n):
        prob = prob_scores[i]
        w_mr = min(prob, 0.8)
        w_trend = 1 - w_mr
        positions[i] = w_mr * mr_positions[i] + w_trend * trend_positions[i]
    
    returns = []
    for i in range(n - 1):
        ret = (close_prices[i+1] - close_prices[i]) / close_prices[i]
        returns.append(positions[i] * ret)
    
    returns = np.array(returns)
    
    if len(returns) == 0:
        return {
            'sharpe': 0,
            'total_return': 0,
            'max_dd': 0,
            'positions': positions,
            'returns': returns
        }
    
    annual_factor = 252 / len(returns) if len(returns) > 0 else 252
    annual_return = np.mean(returns) * annual_factor
    annual_vol = np.std(returns) * np.sqrt(annual_factor)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0
    
    cumulative = (1 + returns).cumprod()
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    max_dd = np.min(drawdown) if len(drawdown) > 0 else 0
    
    total_return = cumulative[-1] - 1 if len(cumulative) > 0 else 0
    
    return {
        'sharpe': sharpe,
        'total_return': total_return,
        'max_dd': max_dd,
        'annual_return': annual_return,
        'annual_vol': annual_vol,
        'positions': positions,
        'returns': returns,
        'cumulative': cumulative
    }

mr_positions_padded = np.zeros(len(close_prices_collected))
mr_positions_padded[:len(result_mr['positions'])] = result_mr['positions']

trend_positions_padded = np.zeros(len(close_prices_collected))
trend_positions_padded[:len(result_trend['positions'])] = result_trend['positions']

result_rs = calculate_regime_switch_soft(
    close_prices_collected, y_proba,
    mr_positions_padded, trend_positions_padded
)

print(f"\n   Regime-Switching 组合:")
print(f"   Sharpe: {result_rs['sharpe']:.4f}")
print(f"   总收益: {result_rs['total_return']:.4f}")
print(f"   MaxDD: {result_rs['max_dd']:.4f}")

print("\n12. 保存结果...")
output_dir = Path(__file__).parent
plots_dir = output_dir / "plots"
plots_dir.mkdir(exist_ok=True)

fig, axes = plt.subplots(2, 2, figsize=(16, 12))

axes[0, 0].plot(result_mr['cumulative'], label='MR')
axes[0, 0].plot(result_trend['cumulative'], label='Trend')
axes[0, 0].plot(result_rs['cumulative'], label='Regime-Switch')
axes[0, 0].set_title('Cumulative Return')
axes[0, 0].legend()
axes[0, 0].grid(True)

strategies = ['MR', 'Trend', 'Regime-Switch']
sharpes = [metrics_mr['sharpe'], result_trend['sharpe'], result_rs['sharpe']]
axes[0, 1].bar(strategies, sharpes)
axes[0, 1].set_title('Sharpe Ratio')
axes[0, 1].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
axes[0, 1].grid(True, axis='y')

maxdds = [-metrics_mr['max_dd']*100, -result_trend['max_dd']*100, -result_rs['max_dd']*100]
axes[1, 0].bar(strategies, maxdds)
axes[1, 0].set_title('Max Drawdown (%)')
axes[1, 0].grid(True, axis='y')

total_returns = [metrics_mr['total_return'], result_trend['total_return'], result_rs['total_return']]
axes[1, 1].bar(strategies, total_returns)
axes[1, 1].set_title('Total Return')
axes[1, 1].grid(True, axis='y')

plt.tight_layout()
plt.savefig(plots_dir / "pm_analysis_comparison.png", dpi=150, bbox_inches='tight')
plt.close()

print("\n13. 生成报告...")

report_lines = []
report_lines.append("# exp11_pm_analysis: PM级综合分析")
report_lines.append("")
report_lines.append("## 策略对比")
report_lines.append("")
report_lines.append("| 策略 | Sharpe | 总收益 | MaxDD | 年化收益 | 年化波动率 |")
report_lines.append("|------|--------|--------|-------|----------|------------|")
report_lines.append(f"| MR | {metrics_mr['sharpe']:.4f} | {metrics_mr['total_return']:.4f} | {-metrics_mr['max_dd']*100:.2f}% | {metrics_mr['annual_return']*100:.2f}% | {metrics_mr['annual_vol']*100:.2f}% |")
report_lines.append(f"| Trend | {result_trend['sharpe']:.4f} | {result_trend['total_return']:.4f} | {-result_trend['max_dd']*100:.2f}% | {result_trend['annual_return']*100:.2f}% | {result_trend['annual_vol']*100:.2f}% |")
report_lines.append(f"| Regime-Switch | {result_rs['sharpe']:.4f} | {result_rs['total_return']:.4f} | {-result_rs['max_dd']*100:.2f}% | {result_rs['annual_return']*100:.2f}% | {result_rs['annual_vol']*100:.2f}% |")
report_lines.append("")

report_lines.append("## 资本利用率")
report_lines.append("")
report_lines.append("| 策略 | 平均风险暴露 | 市场停留时间 |")
report_lines.append("|------|-------------|-------------|")
report_lines.append(f"| MR | {average_exposure_mr*100:.1f}% | {time_in_market_mr*100:.1f}% |")
report_lines.append(f"| Trend | {average_exposure_trend*100:.1f}% | {time_in_market_trend*100:.1f}% |")
report_lines.append("")

if bear_metrics:
    report_lines.append("## 极端行情测试")
    report_lines.append("")
    report_lines.append(f"### 2022 熊市 ({bear_metrics['start']} 到 {bear_metrics['end']})")
    report_lines.append("")
    report_lines.append("| 策略 | 收益 |")
    report_lines.append("|------|------|")
    report_lines.append(f"| MR | {bear_metrics['mr_return']*100:.1f}% |")
    report_lines.append(f"| Trend | {bear_metrics['trend_return']*100:.1f}% |")
    report_lines.append("")

if bull_metrics:
    report_lines.append(f"### 2024 牛市 ({bull_metrics['start']} 到 {bull_metrics['end']})")
    report_lines.append("")
    report_lines.append("| 策略 | 收益 |")
    report_lines.append("|------|------|")
    report_lines.append(f"| MR | {bull_metrics['mr_return']*100:.1f}% |")
    report_lines.append(f"| Trend | {bull_metrics['trend_return']*100:.1f}% |")
    report_lines.append("")

report_lines.append("## 成本压力测试")
report_lines.append("")
report_lines.append("| 场景 | Sharpe | 总收益 | MaxDD |")
report_lines.append("|------|--------|--------|-------|")
for res in cost_results:
    report_lines.append(f"| {res['label']} | {res['sharpe']:.4f} | {res['total_return']:.4f} | {-res['max_dd']*100:.2f}% |")
report_lines.append("")

report_path = output_dir / "results_pm_analysis.md"
with open(report_path, 'w') as f:
    f.write('\n'.join(report_lines))
print(f"   报告保存至: {report_path}")

print("\n" + "=" * 80)
print("exp11_pm_analysis 完成!")
print("=" * 80)
