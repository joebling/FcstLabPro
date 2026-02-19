#!/usr/bin/env python3
"""持仓期对比测试: 14天 vs 21天"""

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


def load_config(config_path):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def calculate_metrics(returns):
    if len(returns) == 0:
        return {'total_return': 0, 'annualized': 0, 'max_drawdown': 0, 'sharpe': 0}

    total_return = np.prod(1 + returns) - 1
    n_days = len(returns)
    annualized = (1 + total_return) ** (365 / n_days) - 1

    cumulative = np.cumprod(1 + returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = abs(drawdown.min()) if len(drawdown) > 0 else 0

    sharpe = np.mean(returns) / (np.std(returns) + 1e-10) * np.sqrt(365) if np.std(returns) > 0 else 0

    return {'total_return': total_return, 'annualized': annualized, 'max_drawdown': max_drawdown, 'sharpe': sharpe, 'n_trades': len(returns)}


def run_strategy(df, proba, holding_days=14, transaction_cost=0.0004):
    close = df['close'].values
    ma50 = df['close'].rolling(50).mean().values
    ma150 = df['close'].rolling(150).mean().values
    ma200 = df['close'].rolling(200).mean().values

    base_signal = (proba < 0.5).astype(int)
    ma_condition = (close > ma50) & (close > ma150) & (close > ma200)
    signal = base_signal & ma_condition

    returns = []
    position = 0
    entry_price = 0
    entry_idx = 0

    for i in range(len(signal)):
        if position == 0 and signal[i]:
            position = 1
            entry_price = close[i]
            entry_idx = i
        elif position == 1:
            days_held = i - entry_idx
            if days_held >= holding_days:
                ret = (close[i] - entry_price) / entry_price - transaction_cost * 2
                returns.append(ret)
                position = 0
            elif not ma_condition[i]:
                ret = (close[i] - entry_price) / entry_price - transaction_cost * 2
                returns.append(ret)
                position = 0

    if position == 1:
        ret = (close[-1] - entry_price) / entry_price - transaction_cost * 2
        returns.append(ret)

    return np.array(returns) if returns else np.array([0])


# 加载配置和数据
config = load_config('experiments/weekly/weekly_bull_v27_orion_v2/config.yaml')
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

# 测试不同持仓期
print("="*60)
print("持仓期对比测试")
print("="*60)

for holding in [7, 14, 21, 28]:
    returns = run_strategy(df_test, proba, holding_days=holding)
    metrics = calculate_metrics(returns)
    print(f"\n持仓 {holding} 天:")
    print(f"  交易次数: {metrics['n_trades']}")
    print(f"  总收益: {metrics['total_return']:.2%}")
    print(f"  年化: {metrics['annualized']:.2%}")
    print(f"  最大回撤: {metrics['max_drawdown']:.2%}")
    print(f"  Sharpe: {metrics['sharpe']:.2f}")
