"""技术指标特征集."""

import numpy as np
import pandas as pd

from src.features.registry import register_feature_set


@register_feature_set("technical")
def build_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """构建技术指标特征.

    包含: 移动平均线、RSI、MACD、布林带、ATR、动量指标等。

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV 数据, 必须包含 close, high, low 列

    Returns
    -------
    pd.DataFrame
        新增技术指标列后的 DataFrame
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # ---------- 移动平均线 ----------
    for w in [5, 10, 20, 50, 100, 200]:
        df[f"sma_{w}"] = close.rolling(w).mean()
        df[f"ema_{w}"] = close.ewm(span=w, adjust=False).mean()

    # 均线交叉信号
    df["sma_cross_5_20"] = df["sma_5"] - df["sma_20"]
    df["sma_cross_10_50"] = df["sma_10"] - df["sma_50"]
    df["sma_cross_50_200"] = df["sma_50"] - df["sma_200"]

    # 价格相对均线位置
    for w in [20, 50, 200]:
        df[f"price_vs_sma_{w}"] = (close - df[f"sma_{w}"]) / df[f"sma_{w}"]

    # ---------- RSI ----------
    for w in [6, 14, 28]:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(w).mean()
        avg_loss = loss.rolling(w).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        df[f"rsi_{w}"] = 100 - (100 / (1 + rs))

    # ---------- MACD ----------
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # ---------- 布林带 ----------
    for w in [20]:
        mid = close.rolling(w).mean()
        std = close.rolling(w).std()
        df[f"bb_upper_{w}"] = mid + 2 * std
        df[f"bb_lower_{w}"] = mid - 2 * std
        df[f"bb_width_{w}"] = (df[f"bb_upper_{w}"] - df[f"bb_lower_{w}"]) / mid
        df[f"bb_pctb_{w}"] = (close - df[f"bb_lower_{w}"]) / (df[f"bb_upper_{w}"] - df[f"bb_lower_{w}"] + 1e-10)

    # ---------- ATR (Average True Range) ----------
    for w in [14, 21]:
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        df[f"atr_{w}"] = tr.rolling(w).mean()
        df[f"atr_pct_{w}"] = df[f"atr_{w}"] / close

    # ---------- 动量指标 ----------
    for w in [1, 3, 5, 7, 14, 21]:
        df[f"return_{w}d"] = close.pct_change(w)

    for w in [5, 10, 20]:
        df[f"volatility_{w}d"] = close.pct_change().rolling(w).std()

    # ---------- 最高最低价距离 ----------
    for w in [14, 21, 50]:
        df[f"high_{w}d_dist"] = (close - high.rolling(w).max()) / close
        df[f"low_{w}d_dist"] = (close - low.rolling(w).min()) / close

    # ---------- K/D 随机指标 ----------
    for w in [14]:
        lowest = low.rolling(w).min()
        highest = high.rolling(w).max()
        df[f"stoch_k_{w}"] = 100 * (close - lowest) / (highest - lowest + 1e-10)
        df[f"stoch_d_{w}"] = df[f"stoch_k_{w}"].rolling(3).mean()

    return df
