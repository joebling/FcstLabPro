#!/usr/bin/env python3
"""exp02_prob_layered: 概率分层测试."""

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
from src.backtest import (
    BacktestEngine,
    TriggerA,
    TP_SL_Exit,
    calculate_metrics
)
from src.visualization import plot_strategy_comparison

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

print("=" * 80)
print("exp02_prob_layered: 概率分层测试")
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

y_proba_all, close_all = run_walk_forward_collect_proba(
    X_valid, y_valid, aligned_close
)

print(f"\n   收集了 {len(y_proba_all)} 个时点的数据")

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

print("\n5. 定义概率分层...")

percentiles = np.percentile(y_proba_all, [50, 70, 80])
print(f"\n   prob 分布:")
print(f"   50% percentile: {percentiles[0]:.4f}")
print(f"   70% percentile: {percentiles[1]:.4f}")
print(f"   80% percentile: {percentiles[2]:.4f}")

layer_thresholds = {
    'P1_top_20': percentiles[2],
    'P2_top_30': percentiles[1],
    'P3_top_50': percentiles[0],
    'P4_all': 0.0
}

layers = list(layer_thresholds.keys())
print(f"\n   分层: {layers}")

print("\n6. 运行分层回测...")

all_results = {}
engine = BacktestEngine(close_all, y_proba_all)

for layer_name, threshold in layer_thresholds.items():
    print(f"\n   回测 {layer_name} (threshold={threshold:.4f})...")
    
    mask = y_proba_all >= threshold
    masked_proba = np.where(mask, y_proba_all, 0.0)
    
    layer_engine = BacktestEngine(close_all, masked_proba)
    
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
    
    result = layer_engine.run(trigger, exit_strategy)
    all_results[layer_name] = result

print("\n7. 计算指标...")

metrics_list = []

for name, result in all_results.items():
    metrics = calculate_metrics(result['returns'], result['cumulative'])
    metrics['layer'] = name
    metrics['num_trades'] = len(result['entry_indices'])
    metrics_list.append(metrics)

metrics_df = pd.DataFrame(metrics_list)
metrics_df = metrics_df[['layer', 'sharpe', 'total_return', 'max_dd', 
                         'win_rate', 'annual_return', 'annual_vol', 'num_trades']]

order = ['P1_top_20', 'P2_top_30', 'P3_top_50', 'P4_all']
metrics_df = metrics_df.set_index('layer').loc[order].reset_index()

print("\n   指标汇总:")
print(metrics_df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

print("\n8. 验证单调性...")

sharpe_values = metrics_df['sharpe'].values
is_monotonic = all(sharpe_values[i] >= sharpe_values[i+1] for i in range(len(sharpe_values)-1))
print(f"\n   Sharpe 单调性: {'✅ 单调下降' if is_monotonic else '❌ 非单调'}")

print("\n9. 保存结果...")

SAVE_DIR = Path(__file__).parent
metrics_df.to_csv(SAVE_DIR / "metrics_prob_layered.csv", index=False)

plot_strategy_comparison(
    all_results,
    save_path=SAVE_DIR / "plots" / "prob_layered_comparison.png"
)

print("\n10. 生成报告...")

with open(SAVE_DIR / "results_prob_layered.md", "w", encoding="utf-8") as f:
    f.write("# exp02_prob_layered: 概率分层测试结果\n\n")
    f.write(f"**日期**: 2026-02-21\n\n")
    
    f.write("## 使用的最佳参数\n\n")
    f.write("| 参数 | 值 |\n")
    f.write("|------|-----|\n")
    for k, v in best_params.items():
        f.write(f"| {k} | {v} |\n")
    f.write("\n")
    
    f.write("## Prob 分布\n\n")
    f.write(f"- 50% percentile: {percentiles[0]:.4f}\n")
    f.write(f"- 70% percentile: {percentiles[1]:.4f}\n")
    f.write(f"- 80% percentile: {percentiles[2]:.4f}\n")
    f.write("\n")
    
    f.write("## 分层定义\n\n")
    f.write("| 分层 | 描述 | 阈值 |\n")
    f.write("|------|------|------|\n")
    f.write(f"| P1_top_20 | prob 最高 20% | ≥ {percentiles[2]:.4f} |\n")
    f.write(f"| P2_top_30 | prob 最高 30% | ≥ {percentiles[1]:.4f} |\n")
    f.write(f"| P3_top_50 | prob 最高 50% | ≥ {percentiles[0]:.4f} |\n")
    f.write("| P4_all | 全部 | ≥ 0.0 |\n")
    f.write("\n")
    
    f.write("## 指标汇总\n\n")
    f.write("| layer | sharpe | total_return | max_dd | win_rate | annual_return | annual_vol | num_trades |\n")
    f.write("|-------|--------|--------------|--------|----------|---------------|------------|------------|\n")
    for _, row in metrics_df.iterrows():
        f.write(f"| {row['layer']} | {row['sharpe']:.4f} | {row['total_return']:.4f} | {row['max_dd']:.4f} | {row['win_rate']:.4f} | {row['annual_return']:.4f} | {row['annual_vol']:.4f} | {int(row['num_trades'])} |\n")
    f.write("\n")
    
    f.write("## 单调性验证\n\n")
    status = "✅ 通过" if is_monotonic else "❌ 未通过"
    f.write(f"Sharpe 单调性: {status}\n\n")
    f.write("预期: Sharpe(P1_top_20) > Sharpe(P2_top_30) > Sharpe(P3_top_50) > Sharpe(P4_all)\n")
    f.write("\n---\n")

print(f"\n   报告保存至: {SAVE_DIR / 'results_prob_layered.md'}")

print("\n" + "=" * 80)
print("exp02_prob_layered 完成!")
print("=" * 80)
