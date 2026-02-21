#!/usr/bin/env python3
"""exp03_param_opt: 参数优化回测."""

import sys
from pathlib import Path
import itertools

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import yaml
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
    FixedHoldExit,
    calculate_metrics
)

print("=" * 80)
print("exp03_param_opt: 参数优化")
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

print("\n4. 定义参数扫描空间...")

param_space = {
    'prob_threshold': [0.6, 0.7, 0.8],
    'dip_threshold': [0.03, 0.04, 0.05],
    'tp': [0.04, 0.06, 0.08],
    'sl': [0.03, 0.05, 0.07],
    'monitor_days': [7, 10, 14]
}

param_names = list(param_space.keys())
param_values = list(param_space.values())
all_combinations = list(itertools.product(*param_values))
total_combinations = len(all_combinations)

print(f"\n   参数空间:")
for name, values in param_space.items():
    print(f"   {name}: {values}")
print(f"\n   总组合数: {total_combinations}")

print("\n5. 运行参数扫描...")

results_list = []
engine = BacktestEngine(close_all, y_proba_all)

for idx, combo in enumerate(all_combinations, 1):
    params = dict(zip(param_names, combo))
    
    if idx % 20 == 0 or idx == 1 or idx == total_combinations:
        print(f"\r   进度: {idx}/{total_combinations} ({idx/total_combinations*100:.1f}%)", end='', flush=True)
    
    trigger = TriggerA(
        prob_threshold=params['prob_threshold'],
        dip_threshold=params['dip_threshold'],
        monitor_days=params['monitor_days']
    )
    
    exit_strategy = TP_SL_Exit(
        tp=params['tp'],
        sl=params['sl'],
        time_stop=14
    )
    
    try:
        result = engine.run(trigger, exit_strategy)
        metrics = calculate_metrics(result['returns'], result['cumulative'])
        
        metrics.update(params)
        metrics['num_trades'] = len(result['entry_indices'])
        metrics['calmar'] = metrics['sharpe'] / metrics['max_dd'] if metrics['max_dd'] > 0 else 0
        
        results_list.append(metrics)
    except Exception as e:
        pass

print(f"\r   进度: {total_combinations}/{total_combinations} (100.0%)")

print("\n6. 分析结果...")

results_df = pd.DataFrame(results_list)

cols = ['prob_threshold', 'dip_threshold', 'tp', 'sl', 'monitor_days',
        'sharpe', 'total_return', 'max_dd', 'calmar', 'win_rate',
        'annual_return', 'annual_vol', 'num_trades']
results_df = results_df[cols]

print("\n   Top 10 by Sharpe:")
top_sharpe = results_df.sort_values('sharpe', ascending=False).head(10)
print(top_sharpe.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

print("\n   Top 10 by Calmar (Sharpe/MaxDD):")
top_calmar = results_df.sort_values('calmar', ascending=False).head(10)
print(top_calmar.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

print("\n7. 保存结果...")

SAVE_DIR = Path(__file__).parent
results_df.to_csv(SAVE_DIR / "param_scan_results.csv", index=False)
top_sharpe.to_csv(SAVE_DIR / "top_sharpe.csv", index=False)
top_calmar.to_csv(SAVE_DIR / "top_calmar.csv", index=False)

print("\n8. 生成报告...")

with open(SAVE_DIR / "results_param_opt.md", "w", encoding="utf-8") as f:
    f.write("# exp03_param_opt: 参数优化结果\n\n")
    f.write(f"**日期**: 2026-02-21\n\n")
    
    f.write("## 参数扫描空间\n\n")
    f.write("| 参数 | 扫描范围 |\n")
    f.write("|------|---------|\n")
    for name, values in param_space.items():
        f.write(f"| {name} | {values} |\n")
    f.write(f"\n总组合数: {total_combinations}\n\n")
    
    f.write("## Top 10 by Sharpe\n\n")
    f.write("| prob_threshold | dip_threshold | tp | sl | monitor_days | sharpe | total_return | max_dd | calmar | win_rate | annual_return | annual_vol | num_trades |\n")
    f.write("|----------------|---------------|----|----|--------------|--------|--------------|--------|--------|----------|---------------|------------|------------|\n")
    for _, row in top_sharpe.iterrows():
        f.write(f"| {row['prob_threshold']:.1f} | {row['dip_threshold']:.2f} | {row['tp']:.2f} | {row['sl']:.2f} | {int(row['monitor_days'])} | {row['sharpe']:.4f} | {row['total_return']:.4f} | {row['max_dd']:.4f} | {row['calmar']:.4f} | {row['win_rate']:.4f} | {row['annual_return']:.4f} | {row['annual_vol']:.4f} | {int(row['num_trades'])} |\n")
    f.write("\n")
    
    f.write("## Top 10 by Calmar (Sharpe/MaxDD)\n\n")
    f.write("| prob_threshold | dip_threshold | tp | sl | monitor_days | sharpe | total_return | max_dd | calmar | win_rate | annual_return | annual_vol | num_trades |\n")
    f.write("|----------------|---------------|----|----|--------------|--------|--------------|--------|--------|----------|---------------|------------|------------|\n")
    for _, row in top_calmar.iterrows():
        f.write(f"| {row['prob_threshold']:.1f} | {row['dip_threshold']:.2f} | {row['tp']:.2f} | {row['sl']:.2f} | {int(row['monitor_days'])} | {row['sharpe']:.4f} | {row['total_return']:.4f} | {row['max_dd']:.4f} | {row['calmar']:.4f} | {row['win_rate']:.4f} | {row['annual_return']:.4f} | {row['annual_vol']:.4f} | {int(row['num_trades'])} |\n")
    f.write("\n")
    
    best = top_sharpe.iloc[0]
    f.write("## 最佳参数\n\n")
    f.write(f"**Sharpe**: {best['sharpe']:.4f}\n")
    f.write(f"**MaxDD**: {best['max_dd']:.4f}\n")
    f.write(f"**Calmar**: {best['calmar']:.4f}\n\n")
    f.write("参数:\n")
    f.write(f"- prob_threshold: {best['prob_threshold']:.1f}\n")
    f.write(f"- dip_threshold: {best['dip_threshold']:.2f}\n")
    f.write(f"- tp: {best['tp']:.2f}\n")
    f.write(f"- sl: {best['sl']:.2f}\n")
    f.write(f"- monitor_days: {int(best['monitor_days'])}\n")
    f.write("\n")
    
    f.write("## 成功标准\n\n")
    f.write("- Sharpe > 0.5\n")
    f.write("- MaxDD < 40%\n\n")
    
    passed = best['sharpe'] > 0.5 and best['max_dd'] < 0.4
    status = "✅ 通过" if passed else "❌ 未通过"
    f.write(f"最佳参数: {status}\n")
    f.write("\n---\n")

print(f"\n   报告保存至: {SAVE_DIR / 'results_param_opt.md'}")

print("\n" + "=" * 80)
print("exp03_param_opt 完成!")
print("=" * 80)
