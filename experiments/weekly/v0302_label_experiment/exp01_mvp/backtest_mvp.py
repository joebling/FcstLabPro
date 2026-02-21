#!/usr/bin/env python3
"""exp01_mvp: MVP 验证回测."""

import sys
from pathlib import Path

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
    BaselineTrigger,
    TriggerA,
    BaselineExit,
    TP_SL_Exit,
    FixedHoldExit,
    calculate_metrics
)
from src.visualization import plot_strategy_comparison

print("=" * 80)
print("exp01_mvp: MVP 验证")
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
    all_test_indices = []
    
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
        all_test_indices.extend(range(t, t + oos_window))
        
        t += step
    
    return np.array(all_y_proba), np.array(all_close), np.array(all_test_indices)

y_proba_all, close_all, test_indices_all = run_walk_forward_collect_proba(
    X_valid, y_valid, aligned_close
)

print(f"\n   收集了 {len(y_proba_all)} 个时点的数据")

print("\n4. 定义 3 个回测方案...")

strategies = []

strategy1 = {
    'name': 'S1_baseline',
    'trigger': BaselineTrigger(prob_threshold=0.5),
    'exit': BaselineExit()
}

strategy2 = {
    'name': 'S2_trigger_a',
    'trigger': TriggerA(
        prob_threshold=0.7,
        dip_threshold=0.04,
        monitor_days=10
    ),
    'exit': TP_SL_Exit(
        tp=0.06,
        sl=0.05,
        time_stop=14
    )
}

strategy3 = {
    'name': 'S3_trigger_a_fixed',
    'trigger': TriggerA(
        prob_threshold=0.7,
        dip_threshold=0.04,
        monitor_days=10
    ),
    'exit': FixedHoldExit(hold_days=14)
}

strategies = [strategy1, strategy2, strategy3]

print("\n   方案列表:")
for i, s in enumerate(strategies, 1):
    print(f"   S{i}: {s['name']}")

print("\n5. 运行回测...")

all_results = {}
engine = BacktestEngine(close_all, y_proba_all)

for strategy in strategies:
    print(f"\n   回测 {strategy['name']}...")
    result = engine.run(strategy['trigger'], strategy['exit'])
    all_results[strategy['name']] = result

print("\n6. 计算指标...")

metrics_list = []

for name, result in all_results.items():
    metrics = calculate_metrics(result['returns'], result['cumulative'])
    metrics['strategy'] = name
    metrics['num_trades'] = len(result['entry_indices'])
    metrics_list.append(metrics)

metrics_df = pd.DataFrame(metrics_list)
metrics_df = metrics_df[['strategy', 'sharpe', 'total_return', 'max_dd', 
                         'win_rate', 'annual_return', 'annual_vol', 'num_trades']]

print("\n   指标汇总:")
print(metrics_df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

print("\n7. 保存结果...")

SAVE_DIR = Path(__file__).parent
metrics_df.to_csv(SAVE_DIR / "metrics_mvp.csv", index=False)

plot_strategy_comparison(
    all_results,
    save_path=SAVE_DIR / "plots" / "strategy_comparison.png"
)

print("\n8. 生成报告...")

with open(SAVE_DIR / "results_mvp.md", "w", encoding="utf-8") as f:
    f.write("# exp01_mvp: MVP 验证结果\n\n")
    f.write(f"**日期**: 2026-02-21\n\n")
    
    f.write("## 回测方案\n\n")
    f.write("| 方案 ID | 方案名称 | 描述 |\n")
    f.write("|---------|----------|------|\n")
    f.write("| S1 | S1_baseline | 原始直接持有 |\n")
    f.write("| S2 | S2_trigger_a | Trigger 方案 A + TP/SL |\n")
    f.write("| S3 | S3_trigger_a_fixed | Trigger 方案 A + 固定持仓14天 |\n")
    f.write("\n")
    
    f.write("## 指标汇总\n\n")
    f.write("| strategy | sharpe | total_return | max_dd | win_rate | annual_return | annual_vol | num_trades |\n")
    f.write("|----------|--------|--------------|--------|----------|---------------|------------|------------|\n")
    for _, row in metrics_df.iterrows():
        f.write(f"| {row['strategy']} | {row['sharpe']:.4f} | {row['total_return']:.4f} | {row['max_dd']:.4f} | {row['win_rate']:.4f} | {row['annual_return']:.4f} | {row['annual_vol']:.4f} | {row['num_trades']} |\n")
    f.write("\n")
    
    f.write("## 结果分析\n\n")
    
    best_sharpe = metrics_df.loc[metrics_df['sharpe'].idxmax()]
    f.write(f"**最佳 Sharpe**: {best_sharpe['strategy']} ({best_sharpe['sharpe']:.4f})\n\n")
    
    f.write("## 成功标准\n\n")
    f.write("- Sharpe > 0.5\n")
    f.write("- MaxDD < 50%\n\n")
    
    for _, row in metrics_df.iterrows():
        passed = row['sharpe'] > 0.5 and row['max_dd'] < 0.5
        status = "✅ 通过" if passed else "❌ 未通过"
        f.write(f"- {row['strategy']}: {status}\n")
    
    f.write("\n---\n")

print(f"\n   报告保存至: {SAVE_DIR / 'results_mvp.md'}")

print("\n" + "=" * 80)
print("exp01_mvp 完成!")
print("=" * 80)
