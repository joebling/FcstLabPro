#!/usr/bin/env python3
"""四组对照实验.

验证三重MA是否真alpha:
- A: 反转 + 三重 MA
- B: 反转 + MA200
- C: 反转 + 无 MA
- D: 纯 MA

判断标准:
- A Sharpe > D Sharpe
- A Calmar > D Calmar
- A IC > D IC
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
import argparse

from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns
import src.labels.reversal
from src.labels.registry import get_label_strategy


def load_config(config_path):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def calculate_metrics(returns):
    """计算回测指标."""
    if len(returns) == 0:
        return {'total_return': 0, 'annualized': 0, 'max_drawdown': 0, 'sharpe': 0, 'calmar': 0}

    # 总收益
    total_return = np.prod(1 + returns) - 1

    # 年化收益
    n_days = len(returns)
    annualized = (1 + total_return) ** (365 / n_days) - 1

    # 最大回撤
    cumulative = np.cumprod(1 + returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = abs(drawdown.min()) if len(drawdown) > 0 else 0

    # Sharpe
    daily_risk_free = 0.0  # 简化
    excess_returns = returns - daily_risk_free
    sharpe = np.mean(excess_returns) / (np.std(excess_returns) + 1e-10) * np.sqrt(365) if np.std(excess_returns) > 0 else 0

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


def run_strategy(df, proba, prices, signal_type='invert', ma_filter=None, holding_days=14, transaction_cost=0.0004):
    """
    运行策略回测.

    Parameters:
    - signal_type: 'invert' (反转) 或 'normal' (正常)
    - ma_filter: None, 'MA200', 'triple_MA'
    - holding_days: 持仓天数
    """
    close = df['close'].values
    ma50 = df['close'].rolling(50).mean().values
    ma150 = df['close'].rolling(150).mean().values
    ma200 = df['close'].rolling(200).mean().values

    # 生成信号
    if signal_type == 'invert':
        # 反转: prob < 0.5 时买入
        base_signal = (proba < 0.5).astype(int)
    else:
        # 正常: prob >= 0.5 时买入
        base_signal = (proba >= 0.5).astype(int)

    # 应用 MA 过滤
    if ma_filter == 'MA200':
        ma_condition = close > ma200
    elif ma_filter == 'triple_MA':
        ma_condition = (close > ma50) & (close > ma150) & (close > ma200)
    else:
        # 无 MA 过滤
        ma_condition = np.ones(len(close), dtype=bool)

    # 最终信号
    signal = base_signal & ma_condition

    # 模拟交易
    returns = []
    position = 0
    entry_price = 0
    entry_idx = 0

    for i in range(len(signal)):
        if position == 0 and signal[i]:
            # 买入
            position = 1
            entry_price = close[i]
            entry_idx = i

        elif position == 1:
            # 检查是否卖出
            days_held = i - entry_idx

            # 持仓超过 holding_days 或 MA 过滤失败
            if days_held >= holding_days:
                # 卖出
                ret = (close[i] - entry_price) / entry_price - transaction_cost * 2
                returns.append(ret)
                position = 0
            elif ma_filter and not ma_condition[i]:
                # 跌破 MA 卖出
                ret = (close[i] - entry_price) / entry_price - transaction_cost * 2
                returns.append(ret)
                position = 0

    # 如果最后还有持仓，按最后一天价格平仓
    if position == 1:
        ret = (close[-1] - entry_price) / entry_price - transaction_cost * 2
        returns.append(ret)

    return np.array(returns) if returns else np.array([0])


def run_control_experiment(bull_dir):
    """运行四组对照实验."""

    # 1. 加载配置和数据
    config_path = os.path.join(bull_dir, 'config.yaml')
    config = load_config(config_path)

    print("Loading data...")
    data_path = config['data']['path']
    df = load_csv(data_path)

    # 构建特征
    print("Building features...")
    feature_sets = config['features']['sets']
    df = build_features(df, feature_sets)

    # 获取特征列
    feature_cols = get_feature_columns(df)

    # 生成标签
    label_func = get_label_strategy(config['label']['strategy'])
    labels = label_func(df, T=config['label']['T'], X=config['label']['X'])

    if 'map' in config['label']:
        mapping = {int(k): int(v) for k, v in config['label']['map'].items()}
        labels = labels.map(mapping)

    df['label'] = labels
    df = df.dropna(subset=['label'])
    df['label'] = df['label'].astype(int)

    # 2. 加载模型
    print("Loading model...")
    model_path = os.path.join(bull_dir, 'model.joblib')
    model = joblib.load(model_path)

    scaler_path = os.path.join(bull_dir, 'scaler.joblib')
    scaler = joblib.load(scaler_path)

    # 3. 预测
    init_train = config['evaluation'].get('init_train', 1500)
    X_test = df[feature_cols].values[init_train:]
    timestamps_test = df.index[init_train:]
    df_test = df.iloc[init_train:].copy()

    print(f"Predicting {len(X_test)} samples...")
    X_test_scaled = scaler.transform(X_test)
    proba = model.predict_proba(X_test_scaled)[:, 1]

    # 4. 运行四组策略
    print("\n" + "="*60)
    print("四组对照实验")
    print("="*60)

    # A: 反转 + 三重 MA
    print("\n运行策略 A: 反转 + 三重 MA...")
    returns_A = run_strategy(df_test, proba, df_test['close'].values,
                             signal_type='invert', ma_filter='triple_MA', holding_days=14)

    # B: 反转 + MA200
    print("运行策略 B: 反转 + MA200...")
    returns_B = run_strategy(df_test, proba, df_test['close'].values,
                             signal_type='invert', ma_filter='MA200', holding_days=14)

    # C: 反转 + 无 MA
    print("运行策略 C: 反转 + 无 MA...")
    returns_C = run_strategy(df_test, proba, df_test['close'].values,
                             signal_type='invert', ma_filter=None, holding_days=14)

    # D: 纯 MA (只靠三重 MA 判断，不看模型)
    print("运行策略 D: 纯 MA...")
    # D: 始终持有，只在 MA 条件满足时
    returns_D = run_strategy(df_test, np.full(len(proba), 0.5), df_test['close'].values,
                             signal_type='invert', ma_filter='triple_MA', holding_days=14)

    # 5. 计算指标
    print("\n" + "="*60)
    print("结果汇总")
    print("="*60)

    strategies = {
        'A (反转+三重MA)': returns_A,
        'B (反转+MA200)': returns_B,
        'C (反转+无MA)': returns_C,
        'D (纯MA)': returns_D,
    }

    results = []
    for name, returns in strategies.items():
        metrics = calculate_metrics(returns)
        results.append({
            'strategy': name,
            **metrics
        })
        print(f"\n{name}:")
        print(f"  交易次数: {metrics['n_trades']}")
        print(f"  总收益: {metrics['total_return']:.2%}")
        print(f"  年化收益: {metrics['annualized']:.2%}")
        print(f"  最大回撤: {metrics['max_drawdown']:.2%}")
        print(f"  Sharpe: {metrics['sharpe']:.2f}")
        print(f"  Calmar: {metrics['calmar']:.2f}")

    # 6. 判断标准
    print("\n" + "="*60)
    print("判断: A > D ?")
    print("="*60)

    A = results[0]
    D = results[3]

    print(f"\nA Sharpe ({A['sharpe']:.2f}) > D Sharpe ({D['sharpe']:.2f}): {A['sharpe'] > D['sharpe']}")
    print(f"A Calmar ({A['calmar']:.2f}) > D Calmar ({D['calmar']:.2f}): {A['calmar'] > D['calmar']}")
    print(f"A 年化 ({A['annualized']:.2%}) > D 年化 ({D['annualized']:.2%}): {A['annualized'] > D['annualized']}")

    if A['sharpe'] > D['sharpe'] and A['calmar'] > D['calmar']:
        print("\n✅ 模型有贡献 (A > D)")
    else:
        print("\n⚠️ 模型可能没贡献 (A ≈ D)")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='四组对照实验')
    parser.add_argument('--bull-dir', type=str,
                       default='experiments/weekly/weekly_bull_v27_orion_v2',
                       help='Bull 模型目录')
    args = parser.parse_args()

    run_control_experiment(args.bull_dir)
