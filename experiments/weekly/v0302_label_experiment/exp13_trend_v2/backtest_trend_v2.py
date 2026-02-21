#!/usr/bin/env python3
"""exp13_trend_v2: 改进 Trend 策略."""

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
print("exp13_trend_v2: 改进 Trend 策略")
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

print("\n4. 定义多个 Trend 策略...")

def calculate_trend_pnl_simple(close_prices, ma_short=20, ma_long=60):
    """简单双均线策略."""
    n = len(close_prices)
    positions = np.zeros(n)
    current_position = 0
    
    for i in range(n):
        if i < ma_long:
            continue
        
        ma_short_val = np.mean(close_prices[i-ma_short:i])
        ma_long_val = np.mean(close_prices[i-ma_long:i])
        
        if current_position == 0:
            if ma_short_val > ma_long_val:
                positions[i] = 1.0
                current_position = 1.0
        else:
            positions[i] = current_position
            if ma_short_val < ma_long_val:
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

def calculate_trend_pnl_momentum(close_prices, lookback=20):
    """简单动量策略."""
    n = len(close_prices)
    positions = np.zeros(n)
    current_position = 0
    
    for i in range(n):
        if i < lookback:
            continue
        
        momentum = (close_prices[i] - close_prices[i-lookback]) / close_prices[i-lookback]
        
        if current_position == 0:
            if momentum > 0:
                positions[i] = 1.0
                current_position = 1.0
        else:
            positions[i] = current_position
            if momentum < 0:
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

def calculate_trend_pnl_breakout(close_prices, lookback=20):
    """突破策略."""
    n = len(close_prices)
    positions = np.zeros(n)
    current_position = 0
    
    for i in range(n):
        if i < lookback:
            continue
        
        highest = np.max(close_prices[i-lookback:i])
        lowest = np.min(close_prices[i-lookback:i])
        
        if current_position == 0:
            if close_prices[i] > highest:
                positions[i] = 1.0
                current_position = 1.0
        else:
            positions[i] = current_position
            if close_prices[i] < lowest:
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

print("\n5. 运行多个 Trend 策略回测...")

trend_strategies = [
    {'name': 'MA20_60', 'func': lambda x: calculate_trend_pnl_simple(x, 20, 60), 'label': '双均线(20,60)'},
    {'name': 'MA10_30', 'func': lambda x: calculate_trend_pnl_simple(x, 10, 30), 'label': '双均线(10,30)'},
    {'name': 'Momentum20', 'func': lambda x: calculate_trend_pnl_momentum(x, 20), 'label': '动量(20)'},
    {'name': 'Momentum10', 'func': lambda x: calculate_trend_pnl_momentum(x, 10), 'label': '动量(10)'},
    {'name': 'Breakout20', 'func': lambda x: calculate_trend_pnl_breakout(x, 20), 'label': '突破(20)'},
    {'name': 'Breakout10', 'func': lambda x: calculate_trend_pnl_breakout(x, 10), 'label': '突破(10)'},
]

results = []

for strat in trend_strategies:
    print(f"\n   回测 {strat['label']}...")
    result = strat['func'](close_prices_collected)
    results.append({
        'name': strat['name'],
        'label': strat['label'],
        'sharpe': result['sharpe'],
        'total_return': result['total_return'],
        'max_dd': result['max_dd'],
        'annual_return': result['annual_return'],
        'annual_vol': result['annual_vol'],
        'result': result
    })

print("\n6. 运行 MR 策略作为对比...")

def position_sizer_linear(prob):
    size = 2 * (prob - 0.5)
    return max(0.0, min(size, 1.0))

engine = BacktestEngine(close_prices_collected, y_proba)
trigger = TriggerA(
    prob_threshold=0.8,
    dip_threshold=0.05,
    monitor_days=7
)
exit_strategy = TP_SL_Exit(
    tp=0.04,
    sl=0.03,
    time_stop=14
)
result_mr = engine.run(trigger, exit_strategy, position_sizer=position_sizer_linear)
metrics_mr = calculate_metrics(result_mr['returns'], result_mr['cumulative'])

results.append({
    'name': 'MR_Baseline',
    'label': 'MR基准',
    'sharpe': metrics_mr['sharpe'],
    'total_return': metrics_mr['total_return'],
    'max_dd': metrics_mr['max_dd'],
    'annual_return': metrics_mr['annual_return'],
    'annual_vol': metrics_mr['annual_vol'],
    'result': result_mr
})

print("\n7. 结果汇总...")

results_df = pd.DataFrame(results)
print("\n   所有策略结果:")
print(results_df[['label', 'sharpe', 'total_return', 'max_dd']].to_string(index=False))

print("\n8. 保存结果...")
output_dir = Path(__file__).parent
plots_dir = output_dir / "plots"
plots_dir.mkdir(exist_ok=True)

results_df.to_csv(output_dir / "metrics_trend_v2.csv", index=False)

fig, axes = plt.subplots(2, 2, figsize=(16, 12))

for res in results:
    if 'cumulative' in res['result']:
        axes[0, 0].plot(res['result']['cumulative'], label=res['label'])
    else:
        axes[0, 0].plot(res['result']['cumulative'], label=res['label'])
axes[0, 0].set_title('Cumulative Return')
axes[0, 0].legend()
axes[0, 0].grid(True)

axes[0, 1].bar([r['label'] for r in results], [r['sharpe'] for r in results])
axes[0, 1].set_title('Sharpe Ratio')
axes[0, 1].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
axes[0, 1].grid(True, axis='y')
axes[0, 1].tick_params(axis='x', rotation=45)

axes[1, 0].bar([r['label'] for r in results], [-r['max_dd']*100 for r in results])
axes[1, 0].set_title('Max Drawdown (%)')
axes[1, 0].grid(True, axis='y')
axes[1, 0].tick_params(axis='x', rotation=45)

axes[1, 1].bar([r['label'] for r in results], [r['total_return'] for r in results])
axes[1, 1].set_title('Total Return')
axes[1, 1].grid(True, axis='y')
axes[1, 1].tick_params(axis='x', rotation=45)

plt.tight_layout()
plt.savefig(plots_dir / "trend_v2_comparison.png", dpi=150, bbox_inches='tight')
plt.close()

print("\n9. 生成报告...")

report_lines = []
report_lines.append("# exp13_trend_v2: 改进 Trend 策略")
report_lines.append("")
report_lines.append("## 策略对比")
report_lines.append("")
report_lines.append("| 策略 | Sharpe | 总收益 | MaxDD | 年化收益 | 年化波动率 |")
report_lines.append("|------|--------|--------|-------|----------|------------|")
for res in results:
    report_lines.append(f"| {res['label']} | {res['sharpe']:.4f} | {res['total_return']:.4f} | {-res['max_dd']*100:.2f}% | {res['annual_return']*100:.2f}% | {res['annual_vol']*100:.2f}% |")
report_lines.append("")

best_sharpe_idx = results_df['sharpe'].idxmax()
best_sharpe = results_df.loc[best_sharpe_idx]
report_lines.append(f"**最佳 Trend 策略**: {best_sharpe['label']} - Sharpe={best_sharpe['sharpe']:.4f}")
report_lines.append("")

report_lines.append("## 结论")
report_lines.append("")
if best_sharpe['sharpe'] > 0:
    report_lines.append(f"✅ 找到有效的 Trend 策略: {best_sharpe['label']}")
    report_lines.append(f"   - Sharpe: {best_sharpe['sharpe']:.4f}")
    report_lines.append(f"   - 可以尝试与 MR 策略组合")
else:
    report_lines.append("❌ 所有 Trend 策略表现都不好（Sharpe 为负）")
    report_lines.append("   - 建议放弃 Regime-Switching 架构")
    report_lines.append("   - 专注于优化 MR 策略")
report_lines.append("")

report_path = output_dir / "results_trend_v2.md"
with open(report_path, 'w') as f:
    f.write('\n'.join(report_lines))
print(f"   报告保存至: {report_path}")

print("\n" + "=" * 80)
print("exp13_trend_v2 完成!")
print("=" * 80)
