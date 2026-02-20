"""
Label Factory - 生成不同类型的 Label
=====================================

支持 4 种 Label 策略:
- A1: 简单正负收益 (forward_return > 0)
- A2: 超额收益 (forward_return > rolling_mean)
- B: Dip+Recovery (跌后反弹)
- C: 回归 (连续值)

Author: FcstLabPro
Date: 2026-02-20
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from typing import Tuple


def generate_label_simple(df: pd.DataFrame, T: int = 21) -> pd.Series:
    """
    A1: 简单正负收益
    ==================
    Label = 1 if forward_return > 0 else 0

    语义: 预测未来 T 天是涨还是跌
    """
    future_return = df['close'].shift(-T) / df['close'] - 1
    label = (future_return > 0).astype(int)
    return label


def generate_label_excess(df: pd.DataFrame, T: int = 21, rolling_window: int = 63) -> pd.Series:
    """
    A2: 超额收益
    =============
    Label = 1 if forward_return > rolling_mean else 0

    语义: 预测未来 T 天是否跑赢近期平均
    """
    # 过去的 T 天收益
    past_return = df['close'] / df['close'].shift(T) - 1

    # 滚动平均
    rolling_mean = past_return.rolling(rolling_window).mean()

    # 未来收益
    future_return = df['close'].shift(-T) / df['close'] - 1

    # 超额收益
    label = (future_return > rolling_mean).astype(int)
    return label


def generate_label_dip_recovery(
    df: pd.DataFrame,
    T: int = 21,
    dip_threshold: float = 0.05,
    recovery_threshold: float = 0.03
) -> pd.Series:
    """
    B: Dip + Recovery
    ==================
    Label = 1 if (未来 T 天先跌 > dip_threshold) AND (从低点反弹 > recovery_threshold) else 0

    语义: 跌后是否能反弹（反转策略的核心）
    """
    # 未来 T 天的最低点相对当前价格的跌幅
    future_min = df['close'].shift(-T).rolling(T).min()
    dip = (future_min - df['close']) / df['close']

    # 从最低点反弹的幅度
    # 找到 T 天内的最低价
    rolling_min = df['close'].rolling(T).min()

    # 未来 T 天收盘价相对最低点的涨幅
    future_close = df['close'].shift(-T)
    recovery = (future_close - rolling_min) / rolling_min

    # Label: 先跌够阈值，再反弹够阈值
    label = ((dip < -dip_threshold) & (recovery > recovery_threshold)).astype(int)

    return label


def generate_label_regression(df: pd.DataFrame, T: int = 21) -> pd.Series:
    """
    C: 回归（连续值）
    =================
    Label = forward_return (连续值)

    语义: 直接预测未来收益

    注意: 这是回归任务，不是分类
    """
    future_return = df['close'].shift(-T) / df['close'] - 1
    return future_return


# Registry for label strategies
LABEL_STRATEGIES = {
    'simple': generate_label_simple,           # A1
    'excess': generate_label_excess,           # A2
    'dip_recovery': generate_label_dip_recovery,  # B
    'regression': generate_label_regression,   # C
}


def get_label(strategy: str, df: pd.DataFrame, T: int = 21, **kwargs) -> pd.Series:
    """
    生成指定策略的 Label

    Args:
        strategy: 'simple', 'excess', 'dip_recovery', 'regression'
        df: DataFrame with 'close' column
        T: 预测期限
        **kwargs: 其他参数 (如 rolling_window, dip_threshold 等)

    Returns:
        pd.Series: Label
    """
    if strategy not in LABEL_STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy}. Available: {list(LABEL_STRATEGIES.keys())}")

    func = LABEL_STRATEGIES[strategy]

    # 添加默认参数
    if strategy == 'excess':
        kwargs.setdefault('rolling_window', 63)
    elif strategy == 'dip_recovery':
        kwargs.setdefault('dip_threshold', 0.05)
        kwargs.setdefault('recovery_threshold', 0.03)

    return func(df, T=T, **kwargs)


def get_label_info(strategy: str) -> dict:
    """获取 Label 策略的描述信息"""
    info = {
        'simple': {
            'name': 'A1: 简单正负收益',
            'description': 'Label = 1 if future_return > 0 else 0',
            'semantic': '预测未来 T 天是涨还是跌',
            'task': 'binary',
        },
        'excess': {
            'name': 'A2: 超额收益',
            'description': 'Label = 1 if future_return > rolling_mean else 0',
            'semantic': '预测是否跑赢近期平均',
            'task': 'binary',
        },
        'dip_recovery': {
            'name': 'B: Dip+Recovery',
            'description': 'Label = 1 if (dip > 5%) and (recovery > 3%)',
            'semantic': '跌后是否能反弹',
            'task': 'binary',
        },
        'regression': {
            'name': 'C: 回归',
            'description': 'Label = future_return (continuous)',
            'semantic': '直接预测未来收益',
            'task': 'regression',
        },
    }
    return info.get(strategy, {})


# Test
if __name__ == '__main__':
    from src.data.loader import load_csv

    DATA_PATH = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"

    print("Testing label_factory...")
    df = load_csv(str(DATA_PATH))
    df = df.head(500)  # Test with first 500 rows

    for strategy in LABEL_STRATEGIES.keys():
        label = get_label(strategy, df, T=21)
        print(f"\n{strategy}:")
        print(f"  Shape: {label.shape}")
        print(f"  Value counts: {label.value_counts().to_dict()}")
