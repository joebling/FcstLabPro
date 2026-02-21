#!/usr/bin/env python3
"""exp10_oos_check: 回测2025年11月至今的表现，记录每天策略决策."""

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

print("=" * 80)
print("exp10_oos_check: 2025年11月至今回测 & 每日决策记录")
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
aligned_dates = df.loc[valid_idx].index.values

print(f"\n   样本数: {len(y_valid)}")
print(f"   正样本: {y_valid.sum():.0f} ({y_valid.mean():.1%})")

print("\n3. 运行 walk-forward 并收集 y_proba...")

def run_walk_forward_collect_proba(X, y, close_prices_aligned, dates_aligned):
    """运行 walk-forward，收集 y_proba, close 价格 和日期."""
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

y_proba_all, close_all, dates_all = run_walk_forward_collect_proba(X_valid, y_valid, aligned_close, aligned_dates)

print(f"   收集了 {len(y_proba_all)} 个时点的数据")

print("\n4. 过滤 2025-11-01 之后的数据...")
start_date = pd.Timestamp('2025-11-01')
mask = pd.to_datetime(dates_all) >= start_date
oos_dates = dates_all[mask]
oos_probs = y_proba_all[mask]
oos_closes = close_all[mask]

print(f"   2025-11-01 后数据点: {len(oos_dates)}")
print(f"   日期范围: {oos_dates[0]} 至 {oos_dates[-1]}")

print("\n5. 最佳策略参数...")
best_params = {
    'prob_threshold': 0.8,
    'dip_threshold': 0.05,
    'tp': 0.04,
    'sl': 0.03,
    'monitor_days': 7,
    'time_stop': 14
}

print("\n   最佳参数:")
for k, v in best_params.items():
    print(f"   {k}: {v}")

print("\n6. 运行回测并记录每日决策...")

def position_sizer_linear(prob):
    return max(0, 2 * (prob - 0.5))

def backtest_detailed(dates, close_prices, y_proba, params):
    """带详细每日记录的回测."""
    n = len(dates)
    positions = np.zeros(n)
    current_position = 0.0
    entry_price = 0.0
    entry_idx = -1
    
    daily_decisions = []
    
    for i in range(n):
        date = dates[i]
        price = close_prices[i]
        prob = y_proba[i]
        size = position_sizer_linear(prob)
        
        dip_triggered = False
        if i >= params['monitor_days']:
            window_low = np.min(close_prices[i-params['monitor_days']:i])
            dip = (window_low - close_prices[i]) / close_prices[i]
            dip_triggered = dip >= params['dip_threshold']
        
        decision = {
            'date': date,
            'close': price,
            'prob': prob,
            'position_size': size,
            'dip_triggered': dip_triggered,
            'current_position': current_position,
            'entry_price': entry_price if current_position > 0 else None,
            'days_in_position': (i - entry_idx) if current_position > 0 else 0,
            'action': 'hold'
        }
        
        if current_position == 0:
            if prob >= params['prob_threshold'] and dip_triggered:
                positions[i] = size
                current_position = size
                entry_price = price
                entry_idx = i
                decision['action'] = 'enter'
                decision['comment'] = f'Prob={prob:.4f} >= {params["prob_threshold"]}, dip triggered'
        else:
            tp_hit = False
            sl_hit = False
            time_stop_hit = False
            
            if entry_price > 0:
                if (price - entry_price) / entry_price >= params['tp']:
                    tp_hit = True
                if (price - entry_price) / entry_price <= -params['sl']:
                    sl_hit = True
                if (i - entry_idx) >= params['time_stop']:
                    time_stop_hit = True
            
            if tp_hit or sl_hit or time_stop_hit:
                positions[i] = 0.0
                current_position = 0.0
                decision['action'] = 'exit'
                reasons = []
                if tp_hit:
                    reasons.append(f'TP hit (+{params["tp"]*100:.0f}%)')
                if sl_hit:
                    reasons.append(f'SL hit (-{params["sl"]*100:.0f}%)')
                if time_stop_hit:
                    reasons.append(f'Time stop ({params["time_stop"]}d)')
                decision['comment'] = ', '.join(reasons)
            else:
                positions[i] = current_position
        
        daily_decisions.append(decision)
    
    returns = []
    for i in range(n - 1):
        ret = (close_prices[i+1] - close_prices[i]) / close_prices[i]
        returns.append(positions[i] * ret)
    returns = np.array(returns)
    
    if len(returns) == 0:
        cumulative = np.array([1.0])
    else:
        cumulative = (1 + returns).cumprod()
    
    entry_indices = [i for i, d in enumerate(daily_decisions) if d['action'] == 'enter']
    exit_indices = [i for i, d in enumerate(daily_decisions) if d['action'] == 'exit']
    
    return {
        'returns': returns,
        'cumulative': cumulative,
        'entry_indices': entry_indices,
        'exit_indices': exit_indices,
        'positions': positions,
        'daily_decisions': daily_decisions
    }

result = backtest_detailed(oos_dates, oos_closes, oos_probs, best_params)

print("\n7. 计算指标...")

def calculate_metrics_simple(returns, cumulative):
    """简单的指标计算."""
    if len(returns) == 0:
        return {
            'sharpe': 0.0,
            'total_return': 1.0,
            'max_dd': 0.0,
            'win_rate': 0.0,
            'annual_return': 0.0,
            'annual_vol': 0.0
        }
    
    total_return = cumulative[-1] if len(cumulative) > 0 else 1.0
    
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = 1 - cumulative / running_max
    max_dd = np.max(drawdowns) if len(drawdowns) > 0 else 0.0
    
    win_rate = np.mean(returns > 0) if len(returns) > 0 else 0.0
    
    annual_factor = 365.0
    n_days = len(returns)
    if n_days > 0:
        annual_return = (total_return ** (annual_factor / n_days)) - 1 if total_return > 0 else -1.0
    else:
        annual_return = 0.0
    annual_vol = np.std(returns) * np.sqrt(annual_factor)
    
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0.0
    
    return {
        'sharpe': sharpe,
        'total_return': total_return,
        'max_dd': max_dd,
        'win_rate': win_rate,
        'annual_return': annual_return,
        'annual_vol': annual_vol
    }

metrics = calculate_metrics_simple(result['returns'], result['cumulative'])

print(f"\n   指标:")
print(f"   Sharpe: {metrics['sharpe']:.4f}")
print(f"   总收益: {metrics['total_return']:.4f}")
print(f"   MaxDD: {metrics['max_dd']*100:.2f}%")
print(f"   年化收益: {metrics['annual_return']*100:.2f}%")
print(f"   年化波动率: {metrics['annual_vol']*100:.2f}%")
print(f"   入场次数: {len(result['entry_indices'])}")
print(f"   出场次数: {len(result['exit_indices'])}")

print("\n8. 保存每日决策...")
output_dir = Path(__file__).parent
output_dir.mkdir(exist_ok=True)

decisions_df = pd.DataFrame(result['daily_decisions'])
decisions_df.to_csv(output_dir / "daily_decisions.csv", index=False)
print(f"   每日决策保存至: {output_dir / 'daily_decisions.csv'}")

print("\n9. 生成报告...")
report_lines = []
report_lines.append("# exp10_oos_check: 2025年11月至今回测")
report_lines.append("")
report_lines.append("## 回测范围")
report_lines.append("")
report_lines.append(f"- 开始日期: {oos_dates[0]}")
report_lines.append(f"- 结束日期: {oos_dates[-1]}")
report_lines.append(f"- 数据点数: {len(oos_dates)}")
report_lines.append("")
report_lines.append("## 指标")
report_lines.append("")
report_lines.append("| 指标 | 值 |")
report_lines.append("|------|-----|")
report_lines.append(f"| Sharpe | {metrics['sharpe']:.4f} |")
report_lines.append(f"| 总收益 | {metrics['total_return']:.4f} |")
report_lines.append(f"| MaxDD | {metrics['max_dd']*100:.2f}% |")
report_lines.append(f"| 年化收益 | {metrics['annual_return']*100:.2f}% |")
report_lines.append(f"| 年化波动率 | {metrics['annual_vol']*100:.2f}% |")
report_lines.append(f"| 入场次数 | {len(result['entry_indices'])} |")
report_lines.append(f"| 出场次数 | {len(result['exit_indices'])} |")
report_lines.append("")
report_lines.append("## 交易记录")
report_lines.append("")
report_lines.append("| 日期 | 动作 | 价格 | 概率 | 说明 |")
report_lines.append("|------|------|------|------|------|")
for d in result['daily_decisions']:
    if d['action'] in ['enter', 'exit']:
        report_lines.append(f"| {d['date']} | {d['action']} | {d['close']:.2f} | {d['prob']:.4f} | {d['comment']} |")

report_path = output_dir / "results_oos_check.md"
with open(report_path, 'w') as f:
    f.write('\n'.join(report_lines))
print(f"   报告保存至: {report_path}")

print("\n" + "=" * 80)
print("exp10_oos_check 完成!")
print("=" * 80)
