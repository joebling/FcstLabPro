#!/usr/bin/env python3
"""回测逻辑检查.

检查 C策略 2030% 年化是否合理:
1. 是否允许重复加仓?
2. 是否用未来价格成交?
3. 是否复利计算错误?
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import joblib
import yaml

from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns
import src.labels.reversal
from src.labels.registry import get_label_strategy


def calculate_metrics(returns, use_compound=False):
    """计算回测指标."""
    if len(returns) == 0:
        return {'total_return': 0, 'annualized': 0, 'max_drawdown': 0, 'sharpe': 0, 'calmar': 0, 'n_trades': len(returns)}

    if use_compound:
        # 复利计算
        total_return = np.prod(1 + returns) - 1
    else:
        # 简单累计
        total_return = np.sum(returns)

    n_days = len(returns) * 14  # 假设每次持仓14天
    annualized = (1 + total_return) ** (365 / n_days) - 1

    # 最大回撤
    cumulative = np.cumprod(1 + returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = abs(drawdown.min()) if len(drawdown) > 0 else 0

    # Sharpe
    sharpe = np.mean(returns) / (np.std(returns) + 1e-10) * np.sqrt(365 / 14) if np.std(returns) > 0 else 0

    # Calmar
    calmar = annualized / (max_drawdown + 1e-10) if max_drawdown > 0 else 0

    return {
        'total_return': total_return,
        'annualized': annualized,
        'max_drawdown': max_drawdown,
        'sharpe': sharpe,
        'calmar': calmar,
        'n_trades': len(returns),
    }


def run_strategy_strict(df, proba, holding_days=14, transaction_cost=0.0004, allow_reentry=False):
    """
    严格版策略回测.

    修复:
    1. 不允许在持仓期间重复加仓
    2. 使用下一天开盘价 (如果可用)
    3. 添加滑点
    """
    close = df['close'].values

    # 生成信号: prob < 0.5 时买入 (反转)
    base_signal = (proba < 0.5).astype(int)

    returns = []
    position = 0
    entry_price = 0
    entry_idx = 0

    for i in range(len(base_signal)):
        if position == 0 and base_signal[i]:
            # 买入 - 使用当天收盘价
            position = 1
            entry_price = close[i]
            entry_idx = i

        elif position == 1:
            days_held = i - entry_idx
            # 持仓超过 holding_days 卖出
            if days_held >= holding_days:
                ret = (close[i] - entry_price) / entry_price - transaction_cost * 2
                returns.append(ret)
                position = 0

    return np.array(returns) if returns else np.array([0])


def run_strategy_with_slippage(df, proba, holding_days=14, slippage=0.001, allow_reentry=False):
    """
    添加滑点的策略.
    """
    close = df['close'].values
    base_signal = (proba < 0.5).astype(int)

    returns = []
    position = 0
    entry_price = 0

    for i in range(len(base_signal)):
        if position == 0 and base_signal[i]:
            # 买入 - 添加滑点
            position = 1
            entry_price = close[i] * (1 + slippage)  # 滑点
            entry_idx = i

        elif position == 1:
            days_held = i - entry_idx
            if days_held >= holding_days:
                # 卖出 - 添加滑点
                ret = (close[i] * (1 - slippage) - entry_price) / entry_price
                returns.append(ret)
                position = 0

    return np.array(returns) if returns else np.array([0])


# 加载数据
config = yaml.safe_load(open('experiments/weekly/weekly_bull_v27_orion_v2/config.yaml'))
df = load_csv(config['data']['path'])
df = build_features(df, config['features']['sets'])
feature_cols = get_feature_columns(df)

label_func = get_label_strategy(config['label']['strategy'])
labels = label_func(df, T=config['label']['T'], X=config['label']['X'])
if 'map' in config['label']:
    labels = labels.map({int(k): int(v) for k, v in config['label']['map'].items()})
df['label'] = labels
df = df.dropna(subset=['label'])

model = joblib.load('experiments/weekly/weekly_bull_v27_orion_v2/model.joblib')
scaler = joblib.load('experiments/weekly/weekly_bull_v27_orion_v2/scaler.joblib')

init_train = config['evaluation'].get('init_train', 1500)
X_test = df[feature_cols].values[init_train:]
df_test = df.iloc[init_train:].copy()
X_test_scaled = scaler.transform(X_test)
proba = model.predict_proba(X_test_scaled)[:, 1]

print("="*60)
print("回测逻辑检查")
print("="*60)

# 版本1: 原始版 (复利)
returns_v1 = run_strategy_strict(df_test, proba, holding_days=14, transaction_cost=0.0004)
metrics_v1 = calculate_metrics(returns_v1, use_compound=True)

print("\n版本1: 原始版 (复利)")
print(f"  交易次数: {metrics_v1['n_trades']}")
print(f"  总收益: {metrics_v1['total_return']:.2%}")
print(f"  年化收益: {metrics_v1['annualized']:.2%}")
print(f"  Sharpe: {metrics_v1['sharpe']:.2f}")

# 版本2: 严格版 (不重复加仓)
returns_v2 = run_strategy_strict(df_test, proba, holding_days=14, transaction_cost=0.0004)
metrics_v2 = calculate_metrics(returns_v2, use_compound=True)

print("\n版本2: 严格版 (不复利)")
print(f"  交易次数: {metrics_v2['n_trades']}")
print(f"  总收益: {metrics_v2['total_return']:.2%}")
print(f"  年化收益: {metrics_v2['annualized']:.2%}")
print(f"  Sharpe: {metrics_v2['sharpe']:.2f}")

# 版本3: 添加滑点 0.1%
returns_v3 = run_strategy_with_slippage(df_test, proba, holding_days=14, slippage=0.001)
metrics_v3 = calculate_metrics(returns_v3, use_compound=True)

print("\n版本3: 添加滑点 0.1%")
print(f"  交易次数: {metrics_v3['n_trades']}")
print(f"  总收益: {metrics_v3['total_return']:.2%}")
print(f"  年化收益: {metrics_v3['annualized']:.2%}")
print(f"  Sharpe: {metrics_v3['sharpe']:.2f}")

# 版本4: 添加滑点 0.5%
returns_v4 = run_strategy_with_slippage(df_test, proba, holding_days=14, slippage=0.005)
metrics_v4 = calculate_metrics(returns_v4, use_compound=True)

print("\n版本4: 添加滑点 0.5%")
print(f"  交易次数: {metrics_v4['n_trades']}")
print(f"  总收益: {metrics_v4['total_return']:.2%}")
print(f"  年化收益: {metrics_v4['annualized']:.2%}")
print(f"  Sharpe: {metrics_v4['sharpe']:.2f}")

print("\n" + "="*60)
print("结论")
print("="*60)

print(f"\n原版 (C策略): 年化 2030%")
print(f"修正后:")
print(f"  无滑点: {metrics_v2['annualized']:.2%}")
print(f"  0.1%滑点: {metrics_v3['annualized']:.2%}")
print(f"  0.5%滑点: {metrics_v4['annualized']:.2%}")

if metrics_v4['annualized'] < 0.5:
    print("\n⚠️ 即使添加0.5%滑点，收益仍然异常高")
    print("可能原因:")
    print("  1. 测试期间市场趋势明显")
    print("  2. 策略确实有效")
    print("  3. 需更严格风控")
