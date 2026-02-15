"""Regime 特征集 — 市场状态识别特征."""

import pandas as pd
import numpy as np
from src.features.registry import register_feature_set


@register_feature_set("regime")
def build_regime_features(df: pd.DataFrame) -> pd.DataFrame:
    """构建市场状态识别特征.

    基于价格与均线的位置关系识别当前市场状态:
    - Bull: 价格 > 200日均线
    - Bear: 价格 < 200日均线
    - Sideways: 价格接近200日均线
    """
    df = df.copy()

    # 200日均线
    sma_200 = df["close"].rolling(200).mean()
    df["sma_200"] = sma_200

    # 价格 vs 200MA 位置
    df["regime_price_vs_ma200"] = (df["close"] - sma_200) / (sma_200 + 1e-10)

    # Regime 指示器 (1=Bull, 0=Sideways, -1=Bear)
    df["regime_bull"] = (df["close"] > sma_200).astype(int)
    df["regime_bear"] = (df["close"] < sma_200).astype(int)

    # Sideways: 价格在 200MA 附近 5% 以内
    df["regime_sideways"] = (
        (df["close"] > sma_200 * 0.95) &
        (df["close"] < sma_200 * 1.05)
    ).astype(int)

    # 长期趋势强度
    for w in [50, 100, 200]:
        sma_w = df["close"].rolling(w).mean()
        df[f"regime_trend_{w}"] = (df["close"] - sma_w) / (sma_w + 1e-10)

    # 趋势持续性
    df["regime_ma200_rise"] = (sma_200 > sma_200.shift(20)).astype(int)
    df["regime_ma200_fall"] = (sma_200 < sma_200.shift(20)).astype(int)

    # 波动率 regime
    df["regime_vol_high"] = (df["close"].pct_change().rolling(20).std() > 0.03).astype(int)
    df["regime_vol_low"] = (df["close"].pct_change().rolling(20).std() < 0.015).astype(int)

    return df
