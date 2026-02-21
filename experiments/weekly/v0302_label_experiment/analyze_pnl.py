#!/usr/bin/env python3
"""分析 dip_recovery 为什么分类好但 Sharpe 低，并设计交易策略."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import yaml
import warnings
warnings.filterwarnings('ignore')

from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import cohen_kappa_score, accuracy_score

from src.labels.registry import get_label_strategy
from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

print("=" * 80)
print("分析 dip_recovery 为什么分类好但 Sharpe 低")
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

print("\n3. 运行 walk-forward 并收集详细信息...")

def run_detailed_walk_forward(X, y, close_prices_aligned):
    """运行详细的 walk-forward，收集每个时点的信息."""
    results = []
    
    t = init_train
    while t + oos_window <= len(X):
        train_end = t - purge_gap
        if train_end <= 0:
            t += step
            continue
            
        X_train = X[:train_end]
        y_train = y[:train_end]
        X_test = X[t:t+oos_window]
        y_test = y[t:t+oos_window]
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
        y_pred = (y_proba > 0.5).astype(int)
        
        for i in range(len(X_test)):
            results.append({
                't': t + i,
                'y_true': y_test[i],
                'y_pred': y_pred[i],
                'y_proba': y_proba[i],
                'close': close_test[i],
            })
        
        t += step
    
    return pd.DataFrame(results)

results_df = run_detailed_walk_forward(X_valid, y_valid, aligned_close)

print(f"\n   收集了 {len(results_df)} 个时点的数据")

print("\n4. 分析 label 和价格的关系...")

future_returns = []
for i in range(len(results_df) - T):
    current_close = results_df.iloc[i]['close']
    future_close = results_df.iloc[i + T]['close']
    ret = (future_close - current_close) / current_close
    future_returns.append(ret)

future_returns = np.array(future_returns)
results_df_analysis = results_df.iloc[:-T].copy()
results_df_analysis['future_return'] = future_returns

print("\n   按预测分组的未来收益:")
grouped = results_df_analysis.groupby('y_pred')['future_return'].agg(['mean', 'std', 'count'])
print(grouped)

print("\n   按真实 label 分组的未来收益:")
grouped_true = results_df_analysis.groupby('y_true')['future_return'].agg(['mean', 'std', 'count'])
print(grouped_true)

print("\n5. 分析当前策略的问题...")

print("\n   当前策略: 预测=1 就买入，预测=0 就空仓")
print("   问题分析:")
print("   1. dip_recovery label 定义的是'跌后反弹'，但我们用的是简单的 0/1 持仓")
print("   2. 没有考虑入场时机（应该等 dip 发生后再入场）")
print("   3. 没有考虑出场时机（应该在反弹后出场）")
print("   4. 没有考虑止损止盈")

print("\n6. 设计改进的交易策略...")

print("\n   策略思路:")
print("   - dip_recovery label 的语义是: 未来 T 天内会先跌 >5%，然后反弹 >3%")
print("   - 更好的策略应该是: 等待 dip 发生，然后在低点附近入场，反弹后出场")
print("   - 但在实际交易中，我们无法预知未来，所以需要基于预测概率来设计策略")

print("\n   设计几个候选策略:")
print("   策略 A: 高概率阈值 (proba > 0.7)")
print("   策略 B: 动态持仓期 (持有 T/2 = 10 天)")
print("   策略 C: 分批入场 (proba > 0.6 建 50%，proba > 0.8 加至 100%)")

print("\n7. 回测不同策略...")

def backtest_strategy(results_df, strategy_name, **kwargs):
    """回测策略."""
    df = results_df.copy()
    
    if strategy_name == 'baseline':
        df['position'] = df['y_pred']
    elif strategy_name == 'high_prob':
        threshold = kwargs.get('threshold', 0.7)
        df['position'] = (df['y_proba'] > threshold).astype(int)
    elif strategy_name == 'fixed_hold':
        hold_days = kwargs.get('hold_days', 10)
        df['position'] = 0
        for i in range(len(df)):
            if df.iloc[i]['y_pred'] == 1:
                end_idx = min(i + hold_days, len(df))
                df.iloc[i:end_idx, df.columns.get_loc('position')] = 1
    elif strategy_name == 'scaled':
        df['position'] = 0
        df.loc[df['y_proba'] > 0.6, 'position'] = 0.5
        df.loc[df['y_proba'] > 0.8, 'position'] = 1.0
    
    returns = []
    for i in range(len(df) - 1):
        ret = (df.iloc[i+1]['close'] - df.iloc[i]['close']) / df.iloc[i]['close']
        returns.append(df.iloc[i]['position'] * ret)
    
    returns = np.array(returns)
    
    if len(returns) == 0:
        return None
    
    cumulative = (1 + returns).cumprod()
    total_return = cumulative[-1] - 1
    sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252 / 1) if np.std(returns) > 0 else 0
    max_dd = np.max(1 - cumulative / np.maximum.accumulate(cumulative))
    turnover = np.mean(np.abs(np.diff(df['position'].values)))
    
    return {
        'strategy': strategy_name,
        'total_return': total_return,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'turnover': turnover,
        'returns': returns,
        'cumulative': cumulative,
        'positions': df['position'].values,
    }

strategies = [
    ('baseline', {}),
    ('high_prob', {'threshold': 0.6}),
    ('high_prob', {'threshold': 0.7}),
    ('high_prob', {'threshold': 0.8}),
    ('fixed_hold', {'hold_days': 7}),
    ('fixed_hold', {'hold_days': 10}),
    ('fixed_hold', {'hold_days': 14}),
    ('scaled', {}),
]

backtest_results = []
for name, kwargs in strategies:
    result = backtest_strategy(results_df, name, **kwargs)
    if result is not None:
        result['params'] = kwargs
        backtest_results.append(result)

print("\n   策略回测结果:")
print(f"\n{'策略':<20} {'参数':<20} {'总收益':<10} {'Sharpe':<10} {'最大回撤':<10} {'换手率':<10}")
print("-" * 80)

for r in backtest_results:
    params_str = ', '.join([f"{k}={v}" for k, v in r['params'].items()])
    print(f"{r['strategy']:<20} {params_str:<20} {r['total_return']:>8.1%} {r['sharpe']:>10.4f} {r['max_dd']:>10.1%} {r['turnover']:>10.4f}")

print("\n8. 绘制收益曲线对比...")

fig, ax = plt.subplots(figsize=(14, 8))

for r in backtest_results:
    label = f"{r['strategy']}"
    if r['params']:
        label += f" ({', '.join([f'{k}={v}' for k, v in r['params'].items()])})"
    ax.plot(r['cumulative'], label=label, linewidth=2, alpha=0.8)

ax.set_title('不同策略的累计收益对比', fontsize=14, fontweight='bold')
ax.set_xlabel('时间', fontsize=12)
ax.set_ylabel('累计收益', fontsize=12)
ax.legend(loc='best', fontsize=10)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(PROJECT_ROOT / "experiments/weekly/v0302_label_experiment/strategy_comparison.png", dpi=150, bbox_inches='tight')
print(f"\n   图表已保存到: strategy_comparison.png")

print("\n" + "=" * 80)
print("分析结论")
print("=" * 80)

print("\n为什么分类好但 Sharpe 低？")
print("\n1. Label 语义与交易策略不匹配:")
print("   - dip_recovery label 定义的是: 未来 T 天内先跌 >5%，然后反弹 >3%")
print("   - 但我们的交易策略是: 预测=1 就立即买入，持有到下一个预测")
print("   - 问题: 我们在 dip 发生前就入场了，承担了下跌的风险")

print("\n2. 没有考虑价格路径:")
print("   - Label 只关心最终结果（是否发生了 dip+recovery）")
print("   - 但实际收益取决于入场和出场的时机")
print("   - 如果我们在 dip 前入场，会先亏损，然后才反弹")

print("\n3. 持仓期太长:")
print("   - 当前策略是一直持有到下一个预测")
print("   - 但 dip_recovery 的反弹可能在短期内就完成了")
print("   - 应该在反弹后及时出场")

print("\n建议的交易策略:")
print("\n策略 1: 高概率阈值")
print("   - 只在预测概率 > 0.7 时入场")
print("   - 提高胜率，降低交易频率")

print("\n策略 2: 固定持仓期")
print("   - 入场后持有 7-14 天")
print("   - 捕捉反弹，避免长期持有")

print("\n策略 3: 分批入场")
print("   - 概率 0.6-0.8: 50% 仓位")
print("   - 概率 > 0.8: 100% 仓位")
print("   - 根据信心调整仓位")

print("\n策略 4: 结合技术指标（进阶）")
print("   - 预测=1 时，等待 RSI < 30 再入场")
print("   - 结合实际的超卖信号")
print("   - 避免在 dip 前入场")

print("\n" + "=" * 80)
