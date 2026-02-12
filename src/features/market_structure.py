"""市场结构特征集 — 模拟资金面/微观结构信号.

基于 Binance Kline 可直接获得的字段（quote_volume, trades, taker_buy 等）
以及价格行为衍生的资金面代理指标。
"""

import numpy as np
import pandas as pd

from src.features.registry import register_feature_set


@register_feature_set("market_structure")
def build_market_structure_features(df: pd.DataFrame) -> pd.DataFrame:
    """构建市场结构/资金面特征.

    包含：模拟资金费率、未平仓量代理、CVD、稳定币流入代理、
    主动买入比率、单笔平均成交额、量价背离等。
    """
    df = df.copy()
    close = df["close"]
    volume = df["volume"]
    high = df["high"]
    low = df["low"]
    op = df["open"]

    # ========== 模拟资金费率（基于价格动量） ==========
    for w in [7, 14, 24]:
        df[f"funding_rate_{w}"] = close.pct_change().rolling(w).mean() * 100

    # ========== 模拟未平仓合约（基于成交量累积） ==========
    for w in [7, 14, 24]:
        df[f"open_interest_{w}"] = volume.rolling(w).sum()

    # ========== CVD (Cumulative Volume Delta) ==========
    # 用 close vs open 判断买卖方向
    direction = np.sign(close - op)
    cvd_raw = direction * volume
    df["cvd"] = cvd_raw.cumsum()
    for w in [7, 14, 21]:
        df[f"cvd_ma_{w}"] = df["cvd"].rolling(w).mean()
        df[f"cvd_change_{w}"] = df["cvd"].pct_change(w)

    # ========== 模拟稳定币流入（价格下跌时的成交额代理） ==========
    price_change_7 = close.pct_change(7)
    vol_avg_7 = volume.rolling(7).mean()
    df["stablecoin_inflow_proxy"] = -price_change_7 * vol_avg_7

    # ========== 主动买入比率（Buy Pressure Proxy） ==========
    # 基于 K 线形态：(close - low) / (high - low) 作为买入压力代理
    df["buy_pressure"] = (close - low) / (high - low + 1e-10)
    for w in [5, 10, 20]:
        df[f"buy_pressure_ma_{w}"] = df["buy_pressure"].rolling(w).mean()

    # ========== 如果有 quote_volume：资金流强度 ==========
    if "quote_volume" in df.columns:
        qv = df["quote_volume"]
        for w in [5, 10, 20]:
            df[f"qvol_sma_{w}"] = qv.rolling(w).mean()
            df[f"qvol_ratio_{w}"] = qv / (df[f"qvol_sma_{w}"] + 1e-10)
        # 资金流变化率
        for w in [1, 3, 5, 10]:
            df[f"flow_change_{w}d"] = qv.pct_change(w)
        # 量价背离
        for w in [10, 20]:
            price_ret = close.pct_change(w)
            flow_ret = qv.pct_change(w)
            df[f"flow_price_divergence_{w}"] = flow_ret - price_ret

    # ========== 如果有 trades：交易活跃度 ==========
    if "trades" in df.columns:
        trades = df["trades"]
        for w in [5, 10, 20]:
            df[f"trades_sma_{w}"] = trades.rolling(w).mean()
            df[f"trades_ratio_{w}"] = trades / (df[f"trades_sma_{w}"] + 1e-10)
        df["trades_change_1d"] = trades.pct_change(1)
        df["trades_change_5d"] = trades.pct_change(5)

        # 单笔平均成交额
        avg_trade_size = volume / (trades + 1e-10)
        df["avg_trade_size"] = avg_trade_size
        for w in [5, 10, 20]:
            df[f"avg_trade_size_ma_{w}"] = avg_trade_size.rolling(w).mean()
            df[f"avg_trade_size_ratio_{w}"] = avg_trade_size / (df[f"avg_trade_size_ma_{w}"] + 1e-10)

    # ========== 成交密度 (volume per price range) ==========
    price_range = high - low
    df["volume_density"] = volume / (price_range + 1e-10)
    for w in [5, 10]:
        df[f"volume_density_ma_{w}"] = df["volume_density"].rolling(w).mean()

    return df
