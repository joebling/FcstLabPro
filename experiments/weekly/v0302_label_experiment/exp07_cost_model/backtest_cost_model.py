#!/usr/bin/env python3
"""exp07_cost_model: 交易成本压力测试."""

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
print("exp07_cost_model: 交易成本压力测试")
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

print(f"\n   样本数: {len(y_valid)}")
print(f"   正样本: {y_valid.sum():.0f} ({y_valid.mean():.1%})")

print("\n3. 运行 walk-forward 并收集 y_proba...")

def run_walk_forward_collect_proba(X, y, close_prices_aligned):
    """运行 walk-forward，收集 y_proba 和 close 价格."""
    all_y_proba = []
    all_close = []
    
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
        
        t += step
    
    return np.array(all_y_proba), np.array(all_close)

y_proba_all, close_all = run_walk_forward_collect_proba(X_valid, y_valid, aligned_close)

print(f"   收集了 {len(y_proba_all)} 个时点的数据")

print("\n4. 使用最佳参数...")
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

print("\n5. 定义成本场景...")
cost_scenarios = [
    {'name': 'C1_no_cost', 'fee': 0.0, 'slippage': 0.0, 'label': '无成本'},
    {'name': 'C2_realistic', 'fee': 0.001, 'slippage': 0.001, 'label': '实际(各0.1%'},
    {'name': 'C3_double', 'fee': 0.002, 'slippage': 0.002, 'label': '×2'},
    {'name': 'C4_stress', 'fee': 0.005, 'slippage': 0.005, 'label': '压力测试(各0.5%)'},
]
print("\n   成本场景:")
for cs in cost_scenarios:
    print(f"   {cs['name']}: fee={cs['fee']*100:.1f}%, slippage={cs['slippage']*100:.1f}%")

print("\n6. 运行回测...")

def position_sizer_linear(prob):
    return max(0, 2 * (prob - 0.5))

def backtest_with_costs(close_prices, y_proba, fee_rate, slippage_rate):
    """带成本的回测."""
    engine = BacktestEngine(close_prices, y_proba)
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
    result = engine.run(trigger, exit_strategy, position_sizer=position_sizer_linear)
    
    positions = result['positions']
    entry_indices = result['entry_indices']
    exit_indices = result['exit_indices']
    
    n = len(close_prices)
    returns = []
    
    for i in range(n - 1):
        ret = (close_prices[i+1] - close_prices[i]) / close_prices[i]
        returns.append(positions[i] * ret)
    
    returns = np.array(returns)
    
    total_cost = 0.0
    for idx in entry_indices:
        if idx < len(close_prices):
            total_cost += fee_rate + slippage_rate
    for idx in exit_indices:
        if idx < len(close_prices):
            total_cost += fee_rate + slippage_rate
    
    if len(returns) > 0:
        returns = returns - total_cost / len(returns)
    
    if len(returns) == 0:
        cumulative = np.array([1.0])
    else:
        cumulative = (1 + returns).cumprod()
    
    return {
        'returns': returns,
        'cumulative': cumulative,
        'entry_indices': entry_indices,
        'exit_indices': exit_indices,
        'positions': positions
    }

results = []
for cs in cost_scenarios:
    print(f"\n   回测 {cs['name']}...")
    result = backtest_with_costs(close_all, y_proba_all, cs['fee'], cs['slippage'])
    metrics = calculate_metrics(result['returns'], result['cumulative'])
    results.append({
        'name': cs['name'],
        'label': cs['label'],
        'result': result,
        'metrics': metrics
    })

print("\n7. 计算指标...")
metrics_list = []
for r in results:
    m = r['metrics']
    metrics_list.append({
        'scenario': r['name'],
        'label': r['label'],
        'sharpe': m['sharpe'],
        'total_return': m['total_return'],
        'max_dd': m['max_dd'],
        'win_rate': m['win_rate'],
        'annual_return': m['annual_return'],
        'annual_vol': m['annual_vol'],
        'num_trades': len(r['result']['entry_indices'])
    })
metrics_df = pd.DataFrame(metrics_list)
print("\n   指标汇总:")
print(metrics_df.to_string(index=False))

print("\n8. 保存结果...")
output_dir = Path(__file__).parent
metrics_df.to_csv(output_dir / "metrics_cost_model.csv", index=False)

fig, axes = plt.subplots(2, 2, figsize=(16, 12))

for r in results:
    cumulative = r['result']['cumulative']
    axes[0, 0].plot(cumulative, label=f"{r['name']}: {r['label']}")
axes[0, 0].set_title('Cumulative Return (with costs)')
axes[0, 0].legend()
axes[0, 0].grid(True)

axes[0, 1].bar([r['name'] for r in results], 
               [r['metrics']['sharpe'] for r in results])
axes[0, 1].set_title('Sharpe Ratio (with costs)')
axes[0, 1].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
axes[0, 1].grid(True, axis='y')
axes[0, 1].tick_params(axis='x', rotation=45)

axes[1, 0].bar([r['name'] for r in results], 
               [-r['metrics']['max_dd']*100 for r in results])
axes[1, 0].set_title('Max Drawdown (%) (with costs)')
axes[1, 0].grid(True, axis='y')
axes[1, 0].tick_params(axis='x', rotation=45)

axes[1, 1].bar([r['name'] for r in results], 
               [r['metrics']['total_return'] for r in results])
axes[1, 1].set_title('Total Return (with costs)')
axes[1, 1].grid(True, axis='y')
axes[1, 1].tick_params(axis='x', rotation=45)

plt.tight_layout()
plot_path = output_dir / "plots" / "cost_model_comparison.png"
plt.savefig(plot_path, dpi=150, bbox_inches='tight')
print(f"Plot saved to {plot_path}")
plt.close()

print("\n9. 生成报告...")
report_lines = []
report_lines.append("# exp07_cost_model: 交易成本压力测试")
report_lines.append("")
report_lines.append("## 成本场景对比")
report_lines.append("")
report_lines.append("| 场景 | Label | Sharpe | 总收益 | MaxDD | 年化收益 | 年化波动率 | 交易次数 |")
report_lines.append("|------|-------|--------|--------|-------|----------|------------|---------|")
for row in metrics_list:
    report_lines.append(f"| {row['scenario']} | {row['label']} | {row['sharpe']:.4f} | {row['total_return']:.4f} | {-row['max_dd']*100:.2f}% | {row['annual_return']*100:.2f}% | {row['annual_vol']*100:.2f}% | {row['num_trades']} |")
report_lines.append("")

report_path = output_dir / "results_cost_model.md"
with open(report_path, 'w') as f:
    f.write('\n'.join(report_lines))
print(f"   报告保存至: {report_path}")

print("\n" + "=" * 80)
print("exp07_cost_model 完成!")
print("=" * 80)
