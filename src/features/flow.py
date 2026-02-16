"""资金流特征集（预留扩展）."""

import numpy as np
import pandas as pd

from src.features.registry import register_feature_set


@register_feature_set("flow")
def build_flow_features(df: pd.DataFrame) -> pd.DataFrame:
    """构建资金流相关特征（低内存优化版）.

    这些特征依赖 Binance 数据中的 taker_buy 等字段。
    如果字段不存在，则使用 quote_volume 和 trades 等替代指标。

    使用 dict + concat 模式避免 DataFrame 碎片化导致的 OOM。

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV 数据（可能包含 quote_volume, trades 等扩展列）

    Returns
    -------
    pd.DataFrame
        新增资金流特征列后的 DataFrame
    """
    close = df["close"]
    volume = df["volume"]

    # 收集新列，最后一次性拼接
    new_cols = {}

    # ---------- 净买入量估算 (如果有 trades 列) ----------
    if "trades" in df.columns:
        trades = df["trades"]
        for w in [5, 10, 20]:
            trades_sma = trades.rolling(w).mean()
            new_cols[f"trades_sma_{w}"] = trades_sma
            new_cols[f"trades_ratio_{w}"] = trades / (trades_sma + 1e-10)
        new_cols["trades_change_1d"] = trades.pct_change(1)
        new_cols["trades_change_5d"] = trades.pct_change(5)

    # ---------- 单笔成交量 ----------
    if "trades" in df.columns:
        avg_trade_size = volume / (trades + 1e-10)
        new_cols["avg_trade_size"] = avg_trade_size
        for w in [5, 10, 20]:
            avg_sma = avg_trade_size.rolling(w).mean()
            new_cols[f"avg_trade_size_sma_{w}"] = avg_sma
            new_cols[f"avg_trade_size_ratio_{w}"] = avg_trade_size / (avg_sma + 1e-10)

    # ---------- 资金流强度 (quote_volume 基础) ----------
    if "quote_volume" in df.columns:
        qv = df["quote_volume"]
        # 资金流变化率
        for w in [1, 3, 5, 10]:
            new_cols[f"flow_change_{w}d"] = qv.pct_change(w)

        # 资金流动量
        for w in [5, 10, 20]:
            new_cols[f"flow_momentum_{w}"] = qv.rolling(w).mean().pct_change(w)

        # 量价背离指标
        for w in [10, 20]:
            price_ret = close.pct_change(w)
            flow_ret = qv.pct_change(w)
            new_cols[f"flow_price_divergence_{w}"] = flow_ret - price_ret

    # ---------- 成交密度 (volume per price range) ----------
    price_range = df["high"] - df["low"]
    volume_density = volume / (price_range + 1e-10)
    new_cols["volume_density"] = volume_density
    for w in [5, 10]:
        new_cols[f"volume_density_sma_{w}"] = volume_density.rolling(w).mean()

    # ✅ 一次性拼接（避免 DataFrame 碎片化）
    if new_cols:
        df = pd.concat([df, pd.DataFrame(new_cols, index=df.index)], axis=1)

    return df
