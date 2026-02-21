#!/usr/bin/env python3
"""exp06_regime_switch: Regime-Switching 双策略系统."""

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
from src.visualization import plot_strategy_comparison

print("=" * 80)
print("exp06_regime_switch: Regime-Switching 双策略系统")
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
            random_state=42
        )
        model.fit(X_train_scaled, y_train)
        
        if hasattr(model, 'predict_proba'):
            proba = model.predict_proba(X_test_scaled)
            if proba.shape[1] == 2:
                y_proba_test = proba[:, 1]
            else:
                y_proba_test = np.ones(len(X_test)) * 0.5
        else:
            y_proba_test = np.ones(len(X_test)) * 0.5
        
        all_y_proba.extend(y_proba_test)
        all_close.extend(close_test)
        all_test_indices.extend(range(t, t + oos_window))
        
        t += step
    
    return np.array(all_y_proba), np.array(all_close), np.array(all_test_indices)

y_proba, close_prices_collected, test_indices = run_walk_forward_collect_proba(
    X_valid, y_valid, aligned_close
)

print(f"   收集了 {len(y_proba)} 个时点的数据")

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

print("\n5. 定义策略...")

def position_sizer_linear(prob):
    return max(0, 2 * (prob - 0.5))

class TrendStrategy:
    """简单趋势策略."""
    
    def __init__(self, ma_window=20):
        self.ma_window = ma_window
    
    def should_enter(self, i, close_prices):
        """判断是否入场."""
        if i < self.ma_window:
            return False
        
        ma = np.mean(close_prices[i-self.ma_window:i])
        current_price = close_prices[i]
        return current_price > ma
    
    def should_exit(self, i, close_prices):
        """判断是否出场."""
        if i < self.ma_window:
            return True
        
        ma = np.mean(close_prices[i-self.ma_window:i])
        current_price = close_prices[i]
        return current_price < ma

def calculate_regime_switch_pnl(close_prices, prob_scores, high_prob_threshold=0.7, low_prob_threshold=0.5):
    """计算 Regime-Switching 策略 PnL."""
    n = len(close_prices)
    positions = np.zeros(n)
    current_position = 0
    
    trend = TrendStrategy(ma_window=20)
    
    for i in range(n):
        prob = prob_scores[i]
        
        if current_position == 0:
            if prob > high_prob_threshold:
                positions[i] = 1.0
                current_position = 1.0
            elif prob < low_prob_threshold:
                if trend.should_enter(i, close_prices):
                    positions[i] = 1.0
                    current_position = 1.0
        else:
            if prob > high_prob_threshold:
                pass
            elif prob < low_prob_threshold:
                if trend.should_exit(i, close_prices):
                    positions[i] = 0.0
                    current_position = 0.0
            else:
                positions[i] = 0.0
                current_position = 0.0
        
        if i > 0 and positions[i] == 0:
            positions[i] = positions[i-1]
    
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
            'win_rate': 0,
            'annual_return': 0,
            'annual_vol': 0,
            'num_trades': 0,
            'positions': positions
        }
    
    annual_factor = 252 / len(returns) if len(returns) > 0 else 252
    annual_return = np.mean(returns) * annual_factor
    annual_vol = np.std(returns) * np.sqrt(annual_factor)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0
    
    cumulative = (1 + returns).cumprod()
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    max_dd = np.min(drawdown) if len(drawdown) > 0 else 0
    
    win_rate = np.mean(returns > 0) if len(returns) > 0 else 0
    total_return = cumulative[-1] - 1 if len(cumulative) > 0 else 0
    
    num_trades = 0
    for i in range(1, len(positions)):
        if positions[i] != positions[i-1] and positions[i] != 0:
            num_trades += 1
    
    return {
        'sharpe': sharpe,
        'total_return': total_return,
        'max_dd': max_dd,
        'win_rate': win_rate,
        'annual_return': annual_return,
        'annual_vol': annual_vol,
        'num_trades': num_trades,
        'positions': positions,
        'returns': returns
    }

print("\n6. 运行回测...")
strategies = []

print("\n   回测 S1: MR only (最佳参数)...")
engine = BacktestEngine(close_prices_collected, y_proba)
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
result = engine.run(trigger, exit_strategy)
metrics = calculate_metrics(result['returns'], result['cumulative'])
strategies.append({
    'name': 'S1_MR_only',
    'result': result,
    'metrics': metrics
})

print("\n   回测 S2: MR + Position sizing...")
result_ps = engine.run(trigger, exit_strategy, position_sizer=position_sizer_linear)
metrics_ps = calculate_metrics(result_ps['returns'], result_ps['cumulative'])
strategies.append({
    'name': 'S2_MR_PS',
    'result': result_ps,
    'metrics': metrics_ps
})

print("\n   回测 S3: Regime-Switching (MR + Trend)...")
result_rs = calculate_regime_switch_pnl(
    close_prices_collected, y_proba, 
    high_prob_threshold=0.7, 
    low_prob_threshold=0.5
)
strategies.append({
    'name': 'S3_Regime_Switch',
    'result': {
        'positions': result_rs['positions'],
        'returns': result_rs['returns'],
        'cumulative': (1 + result_rs['returns']).cumprod()
    },
    'metrics': {
        'sharpe': result_rs['sharpe'],
        'total_return': result_rs['total_return'],
        'max_dd': result_rs['max_dd'],
        'win_rate': result_rs['win_rate'],
        'annual_return': result_rs['annual_return'],
        'annual_vol': result_rs['annual_vol'],
        'num_trades': result_rs['num_trades']
    }
})

print("\n7. 计算指标...")
metrics_list = []
for s in strategies:
    m = s['metrics']
    if 'entry_indices' in s['result']:
        num_trades = len(s['result']['entry_indices'])
    else:
        num_trades = m.get('num_trades', 0)
    metrics_list.append({
        'strategy': s['name'],
        'sharpe': m['sharpe'],
        'total_return': m['total_return'],
        'max_dd': m['max_dd'],
        'win_rate': m['win_rate'],
        'annual_return': m['annual_return'],
        'annual_vol': m['annual_vol'],
        'num_trades': num_trades
    })
metrics_df = pd.DataFrame(metrics_list)
print("\n   指标汇总:")
print(metrics_df.to_string(index=False))

print("\n8. 保存结果...")
output_dir = Path(__file__).parent
metrics_df.to_csv(output_dir / "metrics_regime_switch.csv", index=False)

fig, axes = plt.subplots(2, 2, figsize=(16, 12))

for s in strategies:
    cumulative = s['result']['cumulative']
    axes[0, 0].plot(cumulative, label=s['name'])
axes[0, 0].set_title('Cumulative Return')
axes[0, 0].legend()
axes[0, 0].grid(True)

axes[0, 1].bar([s['name'] for s in strategies], 
               [s['metrics']['sharpe'] for s in strategies])
axes[0, 1].set_title('Sharpe Ratio')
axes[0, 1].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
axes[0, 1].grid(True, axis='y')
axes[0, 1].tick_params(axis='x', rotation=45)

axes[1, 0].bar([s['name'] for s in strategies], 
               [-s['metrics']['max_dd']*100 for s in strategies])
axes[1, 0].set_title('Max Drawdown (%)')
axes[1, 0].grid(True, axis='y')
axes[1, 0].tick_params(axis='x', rotation=45)

axes[1, 1].bar([s['name'] for s in strategies], 
               [s['metrics']['total_return'] for s in strategies])
axes[1, 1].set_title('Total Return')
axes[1, 1].grid(True, axis='y')
axes[1, 1].tick_params(axis='x', rotation=45)

plt.tight_layout()
plot_path = output_dir / "plots" / "regime_switch_comparison.png"
plt.savefig(plot_path, dpi=150, bbox_inches='tight')
print(f"Plot saved to {plot_path}")
plt.close()

print("\n9. 生成报告...")
report_lines = []
report_lines.append("# exp06_regime_switch: Regime-Switching 双策略系统")
report_lines.append("")
report_lines.append("## 策略对比")
report_lines.append("")
report_lines.append("| 策略 | Sharpe | 总收益 | MaxDD | 年化收益 | 年化波动率 | 交易次数 |")
report_lines.append("|------|--------|--------|-------|----------|------------|---------|")
for row in metrics_list:
    report_lines.append(f"| {row['strategy']} | {row['sharpe']:.4f} | {row['total_return']:.4f} | {-row['max_dd']*100:.2f}% | {row['annual_return']*100:.2f}% | {row['annual_vol']*100:.2f}% | {row['num_trades']} |")
report_lines.append("")

report_path = output_dir / "results_regime_switch.md"
with open(report_path, 'w') as f:
    f.write('\n'.join(report_lines))
print(f"   报告保存至: {report_path}")

print("\n" + "=" * 80)
print("exp06_regime_switch 完成!")
print("=" * 80)
