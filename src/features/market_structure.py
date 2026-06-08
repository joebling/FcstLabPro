"""市场结构特征集 — 基于 OHLCV 派生的微观结构代理信号.

基于 Binance Kline 可直接获得的字段（quote_volume, trades, taker_buy 等）
以及价格行为衡生的代理指标。

⚠️ 命名说明：本模块所有特征均为 OHLCV 衡生品，不含任何真实衔生品市场数据。
真实 funding rate / open interest 请看 src/features/external.py 的 ext_* 特征集。
历史上曾用 funding_rate_* / open_interest_* / stablecoin_inflow_proxy 命名，
已于 v0529 重命名为 price_mom_smooth_* / volume_cumsum_* / down_volume_proxy
以消除误导 (见 docs/reviews/cr_0522_feature_engineering.md §P0-1)。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.features.registry import register_feature_set


@register_feature_set("market_structure")
def build_market_structure_features(df: pd.DataFrame) -> pd.DataFrame:
    """构建市场结构/微观结构代理特征.

    包含：价格动量平滑、成交量累积、CVD、下跌成交额代理、
    主动买入比率、单笔平均成交额、量价背离等。均为 OHLCV 衡生品。
    """
    df = df.copy()
    close = df["close"]
    volume = df["volume"]
    high = df["high"]
    low = df["low"]
    op = df["open"]

    # ========== 价格动量平滑器 (原误导性命名 funding_rate, 实为 close 动量) ==========
    # ⚠️ 这不是真实资金费率。真实 funding rate 看 external.py 的 ext_funding_rate_*。
    for w in [7, 14, 24]:
        df[f"price_mom_smooth_{w}"] = close.pct_change().rolling(w).mean() * 100

    # ========== 成交量累积 (原误导性命名 open_interest, 实为 volume 滚动求和) ==========
    # ⚠️ 这不是真实未平仓量。
    for w in [7, 14, 24]:
        df[f"volume_cumsum_{w}"] = volume.rolling(w).sum()

    # ========== CVD (Cumulative Volume Delta) ==========
    # 用 close vs open 判断买卖方向
    direction = np.sign(close - op)
    cvd_raw = direction * volume
    df["cvd"] = cvd_raw.cumsum()
    for w in [7, 14, 21]:
        df[f"cvd_ma_{w}"] = df["cvd"].rolling(w).mean()
        df[f"cvd_change_{w}"] = df["cvd"].pct_change(w)

    # ========== 下跌成交额代理 (原误导性命名 stablecoin_inflow, 实为 跳价×量) ==========
    # ⚠️ 这不是真实稳定币流入。
    price_change_7 = close.pct_change(7)
    vol_avg_7 = volume.rolling(7).mean()
    df["down_volume_proxy"] = -price_change_7 * vol_avg_7

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
