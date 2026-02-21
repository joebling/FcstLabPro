#!/usr/bin/env python3
"""exp14_recent_year: 分析交易记录（修复重复日期问题）."""

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
from src.backtest import BacktestEngine, TriggerA, TP_SL_Exit, calculate_metrics

print("=" * 80)
print("exp14_recent_year: 交易记录分析（修复重复日期）")
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

def run_walk_forward_collect_proba(X, y, close_prices_aligned, dates_aligned):
    """运行 walk-forward，收集 y_proba 和 close 价格（去重）."""
    proba_dict = {}
    close_dict = {}
    
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
        dates_test = dates_aligned[t:t+oos_window]
        
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
        
        for i in range(len(dates_test)):
            date = dates_test[i]
            if date not in proba_dict:
                proba_dict[date] = y_proba[i]
                close_dict[date] = close_test[i]
        
        t += step
    
    sorted_dates = sorted(proba_dict.keys())
    y_proba_all = np.array([proba_dict[d] for d in sorted_dates])
    close_all = np.array([close_dict[d] for d in sorted_dates])
    dates_all = np.array(sorted_dates)
    
    return y_proba_all, close_all, dates_all

y_proba_all, close_all, dates_all = run_walk_forward_collect_proba(
    X_valid, y_valid, aligned_close, aligned_dates
)

print(f"\n   收集了 {len(y_proba_all)} 个时点的数据（已去重）")
print(f"   时间范围: {dates_all[0]} 到 {dates_all[-1]}")

print("\n4. 使用最佳参数进行回测...")

best_params = {
    'prob_threshold': 0.8,
    'dip_threshold': 0.05,
    'tp': 0.04,
    'sl': 0.03,
    'monitor_days': 7
}

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

def position_sizer_linear(prob):
    """线性仓位: size = 2 * (prob - 0.5)."""
    size = 2 * (prob - 0.5)
    return max(0.0, min(size, 1.0))

result = engine.run(trigger, exit_strategy, position_sizer=position_sizer_linear)

metrics = calculate_metrics(result['returns'], result['cumulative'])

print("\n" + "=" * 80)
print("5. 分析交易记录")
print("=" * 80)

trades = []
entry_indices = result['entry_indices']
exit_indices = result['exit_indices']

min_len = min(len(entry_indices), len(exit_indices))

for i in range(min_len):
    entry_idx = entry_indices[i]
    exit_idx = exit_indices[i]
    
    if exit_idx <= entry_idx:
        continue
    
    enter_date = dates_all[entry_idx]
    enter_price = close_all[entry_idx]
    prob = y_proba_all[entry_idx]
    
    if prob < 0.8:
        continue
    
    size = None
    for j in range(entry_idx, min(exit_idx, len(result['positions']))):
        if result['positions'][j] > 0:
            size = result['positions'][j]
            break
    if size is None:
        size = position_sizer_linear(prob)
    
    exit_date = dates_all[exit_idx]
    exit_price = close_all[exit_idx]
    ret = (exit_price - enter_price) / enter_price
    
    trade = {
        '序号': len(trades) + 1,
        '入场日期': enter_date,
        '入场价格': enter_price,
        '入场概率': prob,
        '入场仓位': size,
        '出场日期': exit_date,
        '出场价格': exit_price,
        '持仓天数': (exit_date - enter_date).days,
        '盈亏': ret
    }
    trades.append(trade)

trades_df = pd.DataFrame(trades)

if len(trades_df) > 0:
    trades_df = trades_df.sort_values('入场日期')
    trades_df['序号'] = range(1, len(trades_df) + 1)
    
    print(f"\n   共 {len(trades_df)} 笔有效交易（概率≥0.8，无重复）")
    
    print("\n" + "=" * 80)
    print("完整交易记录")
    print("=" * 80)
    
    for idx, row in trades_df.iterrows():
        print(f"\n交易 {row['序号']}:")
        print(f"  入场: {row['入场日期'].strftime('%Y-%m-%d')} @ ${row['入场价格']:.2f}")
        print(f"  概率: {row['入场概率']:.4f}, 仓位: {row['入场仓位']:.1%}")
        print(f"  出场: {row['出场日期'].strftime('%Y-%m-%d')} @ ${row['出场价格']:.2f}")
        print(f"  持仓: {row['持仓天数']} 天, 盈亏: {row['盈亏']:+.2%}")

print("\n" + "=" * 80)
print("6. 筛选最近一年交易（2025-01-01 至今）")
print("=" * 80)

recent_year_start = pd.Timestamp('2025-01-01')

if len(trades_df) > 0:
    recent_trades = trades_df[trades_df['入场日期'] >= recent_year_start].copy()
    recent_trades = recent_trades.reset_index(drop=True)
    recent_trades['序号'] = range(1, len(recent_trades) + 1)
    
    print(f"\n   最近一年交易数: {len(recent_trades)}")
    
    if len(recent_trades) > 0:
        print("\n" + "=" * 80)
        print("最近一年详细交易记录")
        print("=" * 80)
        
        for idx, row in recent_trades.iterrows():
            print(f"\n交易 {row['序号']}:")
            print(f"  入场: {row['入场日期'].strftime('%Y-%m-%d')} @ ${row['入场价格']:.2f}")
            print(f"  概率: {row['入场概率']:.4f}, 仓位: {row['入场仓位']:.1%}")
            print(f"  出场: {row['出场日期'].strftime('%Y-%m-%d')} @ ${row['出场价格']:.2f}")
            print(f"  持仓: {row['持仓天数']} 天, 盈亏: {row['盈亏']:+.2%}")

print("\n" + "=" * 80)
print("7. 保存结果")
print("=" * 80)

OUTPUT_DIR = Path(__file__).parent
OUTPUT_DIR.mkdir(exist_ok=True)

if len(trades_df) > 0:
    trades_df.to_csv(OUTPUT_DIR / "all_trades_final.csv", index=False)
    print(f"\n   全部交易: {OUTPUT_DIR / 'all_trades_final.csv'}")
    
    if len(recent_trades) > 0:
        recent_trades.to_csv(OUTPUT_DIR / "recent_year_trades_final.csv", index=False)
        print(f"   最近一年: {OUTPUT_DIR / 'recent_year_trades_final.csv'}")

print("\n8. 生成报告...")

with open(OUTPUT_DIR / "results_final_fixed.md", "w", encoding="utf-8") as f:
    f.write("# exp14_recent_year: 最终交易记录报告（已去重）\n\n")
    f.write(f"**日期**: 2026-02-21\n\n")
    f.write("---\n\n")
    
    f.write("## 回测设置\n\n")
    f.write("| 参数 | 值 |\n")
    f.write("|------|-----|\n")
    for k, v in best_params.items():
        f.write(f"| {k} | {v} |\n")
    f.write("\n")
    
    f.write("## 整体回测结果\n\n")
    f.write(f"| 指标 | 值 |\n")
    f.write(f"|------|-----|\n")
    f.write(f"| 交易次数 | {len(trades_df)} |\n")
    f.write(f"| Sharpe | {metrics['sharpe']:.4f} |\n")
    f.write(f"| MaxDD | {metrics['max_dd']:.2%} |\n")
    f.write(f"| 总收益 | {metrics['total_return']:.2%} |\n")
    f.write(f"| 年化收益 | {metrics['annual_return']:.2%} |\n")
    f.write(f"| 年化波动率 | {metrics['annual_vol']:.2%} |\n")
    f.write("\n")
    
    if len(trades_df) > 0:
        f.write("## 全部交易记录（概率≥0.8，无重复）\n\n")
        f.write("| 序号 | 入场日期 | 入场价格 | 入场概率 | 入场仓位 | 出场日期 | 出场价格 | 持仓天数 | 盈亏 |\n")
        f.write("|------|---------|---------|---------|---------|---------|---------|---------|------|\n")
        
        for idx, row in trades_df.iterrows():
            f.write(f"| {row['序号']} | {row['入场日期'].strftime('%Y-%m-%d')} | ${row['入场价格']:.2f} | {row['入场概率']:.4f} | {row['入场仓位']:.1%} | {row['出场日期'].strftime('%Y-%m-%d')} | ${row['出场价格']:.2f} | {row['持仓天数']} | {row['盈亏']:+.2%} |\n")
        
        f.write("\n")
        
        f.write("## 最近一年交易（2025-01-01 至今）\n\n")
        f.write(f"| 指标 | 值 |\n")
        f.write(f"|------|-----|\n")
        f.write(f"| 交易次数 | {len(recent_trades)} |\n")
        f.write("\n")
        
        if len(recent_trades) > 0:
            f.write("| 序号 | 入场日期 | 入场价格 | 入场概率 | 入场仓位 | 出场日期 | 出场价格 | 持仓天数 | 盈亏 |\n")
            f.write("|------|---------|---------|---------|---------|---------|---------|---------|------|\n")
            
            for idx, row in recent_trades.iterrows():
                f.write(f"| {row['序号']} | {row['入场日期'].strftime('%Y-%m-%d')} | ${row['入场价格']:.2f} | {row['入场概率']:.4f} | {row['入场仓位']:.1%} | {row['出场日期'].strftime('%Y-%m-%d')} | ${row['出场价格']:.2f} | {row['持仓天数']} | {row['盈亏']:+.2%} |\n")
        else:
            f.write("**最近一年无交易**\n\n")
            f.write("这与 exp10_oos_check 的结果一致。策略设计非常保守，需要同时满足：\n")
            f.write("1. 模型预测概率 ≥ 0.8\n")
            f.write("2. 价格从监控期间的最高点下跌 ≥ 5%\n\n")
            f.write("这是策略的特点，不是 bug。\n")

print(f"\n   报告已保存: {OUTPUT_DIR / 'results_final_fixed.md'}")
print("\n" + "=" * 80)
print("完成!")
print("=" * 80)
