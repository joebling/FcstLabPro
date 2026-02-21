#!/usr/bin/env python3
"""exp14_recent_year: 最近一年回测 - 详细记录入场、买入、卖出时间."""

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

print("=" * 80)
print("exp14_recent_year: 最近一年回测")
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

print(f"   数据范围: {df.index[0]} 到 {df.index[-1]}")
print(f"   总数据点数: {len(df)}")

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

def run_walk_forward_collect_proba(X, y, close_prices_aligned, dates_aligned):
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
        
        all_y_proba.extend(y_proba)
        all_close.extend(close_test)
        all_dates.extend(dates_test)
        
        t += step
    
    return np.array(all_y_proba), np.array(all_close), np.array(all_dates)

dates_aligned = valid_idx
y_proba_all, close_all, dates_all = run_walk_forward_collect_proba(
    X_valid, y_valid, aligned_close, dates_aligned
)

print(f"\n   收集了 {len(y_proba_all)} 个时点的数据")
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

print(f"\n   回测完成!")
print(f"   入场次数: {len(result['entry_indices'])}")
print(f"   出场次数: {len(result['exit_indices'])}")

print("\n5. 构建交易记录...")

trades = []
for entry_idx, exit_idx in zip(result['entry_indices'], result['exit_indices']):
    trade = {
        'enter_date': dates_all[entry_idx],
        'enter_price': close_all[entry_idx],
        'prob': y_proba_all[entry_idx],
        'size': result['positions'][entry_idx],
        'exit_date': dates_all[exit_idx],
        'exit_price': close_all[exit_idx],
        'return': (close_all[exit_idx] - close_all[entry_idx]) / close_all[entry_idx],
        'pnl': result['positions'][entry_idx] * (close_all[exit_idx] - close_all[entry_idx])
    }
    trades.append(trade)

print(f"\n   构建了 {len(trades)} 笔交易")

print("\n6. 筛选最近一年的交易...")

recent_year_start = pd.Timestamp('2025-01-01')
recent_trades = [t for t in trades if t['enter_date'] >= recent_year_start]

print(f"\n   最近一年开始日期: {recent_year_start}")
print(f"   最近一年交易次数: {len(recent_trades)}")

print("\n7. 生成详细交易记录...")

trades_df = pd.DataFrame(trades)
if len(trades_df) > 0:
    trades_df = trades_df.sort_values('enter_date')
    trades_df['enter_date'] = pd.to_datetime(trades_df['enter_date'])
    trades_df['exit_date'] = pd.to_datetime(trades_df['exit_date'])
    trades_df['hold_days'] = (trades_df['exit_date'] - trades_df['enter_date']).dt.days
    
    print("\n" + "=" * 80)
    print("详细交易记录")
    print("=" * 80)
    
    for idx, row in trades_df.iterrows():
        print(f"\n交易 {idx+1}:")
        print(f"  入场日期: {row['enter_date'].strftime('%Y-%m-%d')}")
        print(f"  入场价格: ${row['enter_price']:.2f}")
        print(f"  入场概率: {row['prob']:.4f}")
        print(f"  入场仓位: {row['size']:.1%}")
        print(f"  出场日期: {row['exit_date'].strftime('%Y-%m-%d')}")
        print(f"  出场价格: ${row['exit_price']:.2f}")
        print(f"  持仓天数: {row['hold_days']} 天")
        print(f"  盈亏: {row['return']:+.2%}")
        print(f"  盈亏(绝对): ${row['pnl']:.2f}")

print("\n" + "=" * 80)
print("8. 保存结果...")
print("=" * 80)

OUTPUT_DIR = Path(__file__).parent
OUTPUT_DIR.mkdir(exist_ok=True)

if len(trades_df) > 0:
    trades_df.to_csv(OUTPUT_DIR / "all_trades.csv", index=False)
    print(f"\n   全部交易记录已保存: {OUTPUT_DIR / 'all_trades.csv'}")
    
    if len(recent_trades) > 0:
        recent_trades_df = pd.DataFrame(recent_trades)
        recent_trades_df = recent_trades_df.sort_values('enter_date')
        recent_trades_df['enter_date'] = pd.to_datetime(recent_trades_df['enter_date'])
        recent_trades_df['exit_date'] = pd.to_datetime(recent_trades_df['exit_date'])
        recent_trades_df['hold_days'] = (recent_trades_df['exit_date'] - recent_trades_df['enter_date']).dt.days
        recent_trades_df.to_csv(OUTPUT_DIR / "recent_year_trades.csv", index=False)
        print(f"   最近一年交易记录已保存: {OUTPUT_DIR / 'recent_year_trades.csv'}")
else:
    print("\n   无交易")

print("\n9. 计算整体指标...")

metrics = calculate_metrics(result['returns'])

print("\n" + "=" * 80)
print("整体回测指标")
print("=" * 80)
print(f"\n   Sharpe: {metrics['sharpe']:.4f}")
print(f"   MaxDD: {metrics['maxdd']:.2%}")
print(f"   总收益: {metrics['total_return']:.2%}")
print(f"   年化收益: {metrics['annual_return']:.2%}")
print(f"   年化波动率: {metrics['annual_vol']:.2%}")

print("\n10. 生成报告...")

with open(OUTPUT_DIR / "results_recent_year.md", "w", encoding="utf-8") as f:
    f.write("# exp14_recent_year: 最近一年回测报告\n\n")
    f.write(f"**日期**: 2026-02-21\n\n")
    f.write("---\n\n")
    
    f.write("## 回测设置\n\n")
    f.write("| 参数 | 值 |\n")
    f.write("|------|-----|\n")
    for k, v in best_params.items():
        f.write(f"| {k} | {v} |\n")
    f.write("\n")
    
    f.write("## 回测时间范围\n\n")
    f.write(f"- 开始日期: {dates_all[0]}\n")
    f.write(f"- 结束日期: {dates_all[-1]}\n\n")
    
    f.write("## 最近一年时间范围\n\n")
    f.write(f"- 开始日期: {recent_year_start}\n")
    f.write(f"- 结束日期: {dates_all[-1]}\n\n")
    
    f.write("## 整体回测结果\n\n")
    f.write(f"| 指标 | 值 |\n")
    f.write(f"|------|-----|\n")
    f.write(f"| 交易次数 | {len(trades)} |\n")
    f.write(f"| Sharpe | {metrics['sharpe']:.4f} |\n")
    f.write(f"| MaxDD | {metrics['maxdd']:.2%} |\n")
    f.write(f"| 总收益 | {metrics['total_return']:.2%} |\n")
    f.write(f"| 年化收益 | {metrics['annual_return']:.2%} |\n")
    f.write(f"| 年化波动率 | {metrics['annual_vol']:.2%} |\n")
    f.write("\n")
    
    f.write("## 最近一年交易情况\n\n")
    f.write(f"| 指标 | 值 |\n")
    f.write(f"|------|-----|\n")
    f.write(f"| 交易次数 | {len(recent_trades)} |\n")
    f.write("\n")
    
    if len(trades) > 0:
        f.write("## 全部详细交易记录\n\n")
        f.write("| 序号 | 入场日期 | 入场价格 | 入场概率 | 入场仓位 | 出场日期 | 出场价格 | 持仓天数 | 盈亏 |\n")
        f.write("|------|---------|---------|---------|---------|---------|---------|---------|------|\n")
        
        for idx, row in trades_df.iterrows():
            f.write(f"| {idx+1} | {row['enter_date'].strftime('%Y-%m-%d')} | ${row['enter_price']:.2f} | {row['prob']:.4f} | {row['size']:.1%} | {row['exit_date'].strftime('%Y-%m-%d')} | ${row['exit_price']:.2f} | {row['hold_days']} | {row['return']:+.2%} |\n")
        
        f.write("\n")
        
        if len(recent_trades) > 0:
            f.write("## 最近一年详细交易记录\n\n")
            f.write("| 序号 | 入场日期 | 入场价格 | 入场概率 | 入场仓位 | 出场日期 | 出场价格 | 持仓天数 | 盈亏 |\n")
            f.write("|------|---------|---------|---------|---------|---------|---------|---------|------|\n")
            
            for idx, row in recent_trades_df.iterrows():
                f.write(f"| {idx+1} | {row['enter_date'].strftime('%Y-%m-%d')} | ${row['enter_price']:.2f} | {row['prob']:.4f} | {row['size']:.1%} | {row['exit_date'].strftime('%Y-%m-%d')} | ${row['exit_price']:.2f} | {row['hold_days']} | {row['return']:+.2%} |\n")
    else:
        f.write("## 详细交易记录\n\n")
        f.write("**无交易**\n\n")
    
    f.write("---\n\n")
    f.write("## 结论\n\n")
    if len(recent_trades) > 0:
        f.write(f"最近一年（{recent_year_start} 至今）策略共触发 {len(recent_trades)} 次交易。\n")
        f.write("\n详细交易记录见 `recent_year_trades.csv`。\n")
    else:
        f.write(f"最近一年（{recent_year_start} 至今）策略**没有触发任何交易**。\n\n")
        f.write("这与 exp10_oos_check 的结果一致（2025年11月至今也没有交易）。\n\n")
        f.write("**原因**：策略设计非常保守，需要同时满足：\n")
        f.write("1. 模型预测概率 ≥ 0.8\n")
        f.write("2. 价格从监控期间的最高点下跌 ≥ 5%\n\n")
        f.write("这是策略的特点，不是 bug。\n")

print(f"\n   报告已保存: {OUTPUT_DIR / 'results_recent_year.md'}")
print("\n" + "=" * 80)
print("完成!")
print("=" * 80)
