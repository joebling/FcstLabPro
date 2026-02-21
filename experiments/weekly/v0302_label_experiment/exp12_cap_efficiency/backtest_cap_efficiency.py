#!/usr/bin/env python3
"""exp12_cap_efficiency: 放宽参数提高资金利用率."""

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
print("exp12_cap_efficiency: 放宽参数提高资金利用率")
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

y_proba, close_prices_collected = run_walk_forward_collect_proba(
    X_valid, y_valid, aligned_close
)

print(f"   收集了 {len(y_proba)} 个时点的数据")

print("\n4. 定义参数组合...")

param_combinations = [
    {'name': 'Original', 'prob_threshold': 0.8, 'dip_threshold': 0.05, 'label': '原参数(0.8+0.05)'},
    {'name': 'Relaxed_Prob', 'prob_threshold': 0.7, 'dip_threshold': 0.05, 'label': '放宽prob(0.7+0.05)'},
    {'name': 'Relaxed_Dip', 'prob_threshold': 0.8, 'dip_threshold': 0.03, 'label': '放宽dip(0.8+0.03)'},
    {'name': 'Relaxed_Both', 'prob_threshold': 0.7, 'dip_threshold': 0.03, 'label': '放宽两者(0.7+0.03)'},
    {'name': 'Aggressive', 'prob_threshold': 0.6, 'dip_threshold': 0.02, 'label': '激进(0.6+0.02)'},
]

print("\n   参数组合:")
for p in param_combinations:
    print(f"   {p['label']}")

print("\n5. 定义 Position sizing...")

def position_sizer_linear(prob):
    size = 2 * (prob - 0.5)
    return max(0.0, min(size, 1.0))

print("\n6. 运行所有参数组合回测...")

results = []

for params in param_combinations:
    print(f"\n   回测 {params['label']}...")
    
    engine = BacktestEngine(close_prices_collected, y_proba)
    trigger = TriggerA(
        prob_threshold=params['prob_threshold'],
        dip_threshold=params['dip_threshold'],
        monitor_days=7
    )
    exit_strategy = TP_SL_Exit(
        tp=0.04,
        sl=0.03,
        time_stop=14
    )
    result = engine.run(trigger, exit_strategy, position_sizer=position_sizer_linear)
    metrics = calculate_metrics(result['returns'], result['cumulative'])
    
    avg_exposure = np.mean(np.abs(result['positions']))
    time_in_market = np.mean(result['positions'] != 0)
    
    results.append({
        'name': params['name'],
        'label': params['label'],
        'prob_threshold': params['prob_threshold'],
        'dip_threshold': params['dip_threshold'],
        'sharpe': metrics['sharpe'],
        'total_return': metrics['total_return'],
        'max_dd': metrics['max_dd'],
        'annual_return': metrics['annual_return'],
        'annual_vol': metrics['annual_vol'],
        'avg_exposure': avg_exposure,
        'time_in_market': time_in_market,
        'result': result
    })

print("\n7. 结果汇总...")

results_df = pd.DataFrame(results)
print("\n   所有参数组合结果:")
print(results_df[['label', 'sharpe', 'total_return', 'max_dd', 'avg_exposure', 'time_in_market']].to_string(index=False))

print("\n8. 保存结果...")
output_dir = Path(__file__).parent
plots_dir = output_dir / "plots"
plots_dir.mkdir(exist_ok=True)

results_df.to_csv(output_dir / "metrics_cap_efficiency.csv", index=False)

fig, axes = plt.subplots(2, 2, figsize=(16, 12))

for res in results:
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

axes[1, 1].bar([r['label'] for r in results], [r['avg_exposure']*100 for r in results], label='Avg Exposure')
axes[1, 1].bar([r['label'] for r in results], [r['time_in_market']*100 for r in results], alpha=0.5, label='Time in Market')
axes[1, 1].set_title('Capital Utilization (%)')
axes[1, 1].legend()
axes[1, 1].grid(True, axis='y')
axes[1, 1].tick_params(axis='x', rotation=45)

plt.tight_layout()
plt.savefig(plots_dir / "cap_efficiency_comparison.png", dpi=150, bbox_inches='tight')
plt.close()

print("\n9. 生成报告...")

report_lines = []
report_lines.append("# exp12_cap_efficiency: 放宽参数提高资金利用率")
report_lines.append("")
report_lines.append("## 策略对比")
report_lines.append("")
report_lines.append("| 参数组合 | Sharpe | 总收益 | MaxDD | 年化收益 | 年化波动率 | 平均风险暴露 | 市场停留时间 |")
report_lines.append("|---------|--------|--------|-------|----------|------------|-------------|-------------|")
for res in results:
    report_lines.append(f"| {res['label']} | {res['sharpe']:.4f} | {res['total_return']:.4f} | {-res['max_dd']*100:.2f}% | {res['annual_return']*100:.2f}% | {res['annual_vol']*100:.2f}% | {res['avg_exposure']*100:.1f}% | {res['time_in_market']*100:.1f}% |")
report_lines.append("")

report_lines.append("## 关键发现")
report_lines.append("")

best_sharpe_idx = results_df['sharpe'].idxmax()
best_sharpe = results_df.loc[best_sharpe_idx]
report_lines.append(f"1. **最佳 Sharpe**: {best_sharpe['label']} - Sharpe={best_sharpe['sharpe']:.4f}")
report_lines.append(f"   - 平均风险暴露: {best_sharpe['avg_exposure']*100:.1f}%")
report_lines.append(f"   - 市场停留时间: {best_sharpe['time_in_market']*100:.1f}%")
report_lines.append("")

best_exposure_idx = results_df['avg_exposure'].idxmax()
best_exposure = results_df.loc[best_exposure_idx]
report_lines.append(f"2. **最高资金利用率**: {best_exposure['label']}")
report_lines.append(f"   - 平均风险暴露: {best_exposure['avg_exposure']*100:.1f}%")
report_lines.append(f"   - 市场停留时间: {best_exposure['time_in_market']*100:.1f}%")
report_lines.append(f"   - Sharpe: {best_exposure['sharpe']:.4f}")
report_lines.append("")

report_lines.append("3. **权衡建议**:")
report_lines.append("   - 如果追求 Sharpe: 使用 {best_sharpe['label']}")
report_lines.append("   - 如果追求资金利用率: 使用 {best_exposure['label']}")
report_lines.append("   - 平衡考虑: Relaxed_Dip 或 Relaxed_Prob")
report_lines.append("")

report_path = output_dir / "results_cap_efficiency.md"
with open(report_path, 'w') as f:
    f.write('\n'.join(report_lines))
print(f"   报告保存至: {report_path}")

print("\n" + "=" * 80)
print("exp12_cap_efficiency 完成!")
print("=" * 80)
