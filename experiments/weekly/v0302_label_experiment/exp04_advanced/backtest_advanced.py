#!/usr/bin/env python3
"""exp04_advanced: 高级特性 - Position sizing & 风险控制."""

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
    TriggerA,
    TP_SL_Exit,
    calculate_metrics
)
from src.visualization import plot_strategy_comparison

print("=" * 80)
print("exp04_advanced: 高级特性")
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

print("\n5. 定义 Position sizing 策略...")

def position_sizer_fixed(prob):
    """固定 100% 仓位."""
    return 1.0

def position_sizer_linear(prob):
    """线性仓位: size = 2 * (prob - 0.5)."""
    size = 2 * (prob - 0.5)
    return max(0.0, min(size, 1.0))

def position_sizer_kelly(prob):
    """Kelly 仓位，cap 30%."""
    size = prob - (1 - prob)
    return max(0.0, min(size, 0.3))

position_strategies = {
    'PS1_fixed': position_sizer_fixed,
    'PS2_linear': position_sizer_linear,
    'PS3_kelly': position_sizer_kelly
}

print("\n   Position sizing 策略:")
for name in position_strategies.keys():
    print(f"   {name}")

print("\n6. 定义风险控制策略...")

def risk_manager_none(result):
    """无风险控制."""
    return result

def risk_manager_dd_cutoff(result, max_dd_cutoff=0.2):
    """Max DD cutoff: 超过 20% 后仓位减半."""
    positions = result['positions'].copy()
    cumulative = result['cumulative']
    
    peak = np.maximum.accumulate(np.concatenate([[1.0], cumulative]))
    drawdown = (peak[1:] - cumulative) / peak[1:]
    
    for i in range(len(positions)):
        if i < len(drawdown) and drawdown[i] > max_dd_cutoff:
            positions[i] *= 0.5
    
    returns = []
    for i in range(len(close_all) - 1):
        ret = (close_all[i+1] - close_all[i]) / close_all[i]
        returns.append(positions[i] * ret)
    
    returns = np.array(returns)
    cumulative_new = (1 + returns).cumprod() if len(returns) > 0 else np.array([1.0])
    
    return {
        'positions': positions,
        'returns': returns,
        'cumulative': cumulative_new,
        'entry_indices': result['entry_indices'],
        'exit_indices': result['exit_indices'],
        'entry_prices': result['entry_prices'],
        'exit_prices': result['exit_prices']
    }

risk_strategies = {
    'RC1_none': risk_manager_none,
    'RC2_dd_cutoff': lambda r: risk_manager_dd_cutoff(r, max_dd_cutoff=0.2)
}

print("\n   风险控制策略:")
for name in risk_strategies.keys():
    print(f"   {name}")

print("\n7. 运行回测...")

all_results = {}
engine = BacktestEngine(close_all, y_proba_all)

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

for ps_name, ps_func in position_strategies.items():
    for rc_name, rc_func in risk_strategies.items():
        strategy_name = f"{ps_name}_{rc_name}"
        print(f"\n   回测 {strategy_name}...")
        
        result = engine.run(trigger, exit_strategy, position_sizer=ps_func)
        result = rc_func(result)
        
        all_results[strategy_name] = result

print("\n8. 计算指标...")

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

print("\n9. 保存结果...")

SAVE_DIR = Path(__file__).parent
metrics_df.to_csv(SAVE_DIR / "metrics_advanced.csv", index=False)

plot_strategy_comparison(
    all_results,
    save_path=SAVE_DIR / "plots" / "advanced_comparison.png"
)

print("\n10. 生成报告...")

with open(SAVE_DIR / "results_advanced.md", "w", encoding="utf-8") as f:
    f.write("# exp04_advanced: 高级特性结果\n\n")
    f.write(f"**日期**: 2026-02-21\n\n")
    
    f.write("## 使用的最佳参数\n\n")
    f.write("| 参数 | 值 |\n")
    f.write("|------|-----|\n")
    for k, v in best_params.items():
        f.write(f"| {k} | {v} |\n")
    f.write("\n")
    
    f.write("## Position Sizing 策略\n\n")
    f.write("| 策略 | 描述 |\n")
    f.write("|------|------|\n")
    f.write("| PS1_fixed | 固定 100% |\n")
    f.write("| PS2_linear | size = 2 * (prob - 0.5) |\n")
    f.write("| PS3_kelly | Kelly fraction, cap 30% |\n")
    f.write("\n")
    
    f.write("## 风险控制策略\n\n")
    f.write("| 策略 | 描述 |\n")
    f.write("|------|------|\n")
    f.write("| RC1_none | 无风险控制 |\n")
    f.write("| RC2_dd_cutoff | Max DD cutoff 20% |\n")
    f.write("\n")
    
    f.write("## 指标汇总\n\n")
    f.write("| strategy | sharpe | total_return | max_dd | win_rate | annual_return | annual_vol | num_trades |\n")
    f.write("|----------|--------|--------------|--------|----------|---------------|------------|------------|\n")
    for _, row in metrics_df.iterrows():
        f.write(f"| {row['strategy']} | {row['sharpe']:.4f} | {row['total_return']:.4f} | {row['max_dd']:.4f} | {row['win_rate']:.4f} | {row['annual_return']:.4f} | {row['annual_vol']:.4f} | {int(row['num_trades'])} |\n")
    f.write("\n")
    
    best = metrics_df.loc[metrics_df['sharpe'].idxmax()]
    f.write("## 最佳策略\n\n")
    f.write(f"**策略**: {best['strategy']}\n")
    f.write(f"**Sharpe**: {best['sharpe']:.4f}\n")
    f.write(f"**MaxDD**: {best['max_dd']:.4f}\n")
    f.write(f"**总收益**: {best['total_return']:.4f}\n")
    f.write("\n---\n")

print(f"\n   报告保存至: {SAVE_DIR / 'results_advanced.md'}")

print("\n" + "=" * 80)
print("exp04_advanced 完成!")
print("=" * 80)
