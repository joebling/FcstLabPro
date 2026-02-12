"""成交量特征集."""

import numpy as np
import pandas as pd

from src.features.registry import register_feature_set


@register_feature_set("volume")
def build_volume_features(df: pd.DataFrame) -> pd.DataFrame:
    """构建成交量相关特征.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV 数据

    Returns
    -------
    pd.DataFrame
        新增成交量特征列后的 DataFrame
    """
    volume = df["volume"]
    close = df["close"]

    # ---------- 成交量均线 ----------
    for w in [5, 10, 20, 50]:
        df[f"vol_sma_{w}"] = volume.rolling(w).mean()
        df[f"vol_ratio_{w}"] = volume / (df[f"vol_sma_{w}"] + 1e-10)

    # ---------- 成交量变化率 ----------
    for w in [1, 3, 5]:
        df[f"vol_change_{w}d"] = volume.pct_change(w)

    # ---------- 量价关系 ----------
    df["vol_price_corr_10"] = volume.rolling(10).corr(close)
    df["vol_price_corr_20"] = volume.rolling(20).corr(close)

    # ---------- OBV (On-Balance Volume) ----------
    obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
    df["obv"] = obv
    df["obv_sma_10"] = obv.rolling(10).mean()
    df["obv_sma_20"] = obv.rolling(20).mean()

    # ---------- VWAP 近似 ----------
    typical_price = (df["high"] + df["low"] + close) / 3
    for w in [10, 20]:
        cum_tp_vol = (typical_price * volume).rolling(w).sum()
        cum_vol = volume.rolling(w).sum()
        df[f"vwap_{w}"] = cum_tp_vol / (cum_vol + 1e-10)
        df[f"price_vs_vwap_{w}"] = (close - df[f"vwap_{w}"]) / (df[f"vwap_{w}"] + 1e-10)

    # ---------- 成交量波动率 ----------
    for w in [10, 20]:
        df[f"vol_volatility_{w}"] = volume.pct_change().rolling(w).std()

    # ---------- 资金流量 (如有 quote_volume) ----------
    if "quote_volume" in df.columns:
        qv = df["quote_volume"]
        for w in [5, 10, 20]:
            df[f"qvol_sma_{w}"] = qv.rolling(w).mean()
            df[f"qvol_ratio_{w}"] = qv / (df[f"qvol_sma_{w}"] + 1e-10)

    return df
