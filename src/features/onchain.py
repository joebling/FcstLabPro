"""链上指标特征集 — 基于价格历史模拟链上行为.

⚠️ 废弃警告: 本模块所有特征均为 OHLCV 衡生的**代理**，非真实链上数据。
   mvrv / lth_sopr / sth_sopr / nupl_proxy 等名字具误导性 — 它们只是
   close 的各种变换，与真正的 UTXO/链上估值无关。
   生产模型 (E1/E8) 未启用本特征集。Phase 2 将接入 CoinMetrics 真 MVRV,
   到时本模块应被真数据替代。详见 docs/plans/feature_engineering_roadmap.md。
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from src.features.registry import register_feature_set

warnings.warn(
    "src.features.onchain 的特征均为 OHLCV 代理 (mvrv/sopr/nupl 等名不副实),"
    " 非真实链上数据。生产模型未启用。Phase 2 将用 CoinMetrics 真 MVRV 替代。",
    DeprecationWarning,
    stacklevel=2,
)


@register_feature_set("onchain")
def build_onchain_features(df: pd.DataFrame) -> pd.DataFrame:
    """构建模拟链上指标特征.

    包含：MVRV 代理、LTH/STH SOPR 代理、活跃地址代理、
    矿工流出代理、难度带代理、NUPL 代理等。
    """
    df = df.copy()
    close = df["close"]
    volume = df["volume"]

    # ========== MVRV 代理 (Market Value / Realized Value) ==========
    # 用 close / expanding_mean(close) 模拟
    realized_price = close.expanding().mean()
    df["mvrv"] = close / realized_price
    # MVRV 的变化和位置
    df["mvrv_change_7"] = df["mvrv"].pct_change(7)
    df["mvrv_change_14"] = df["mvrv"].pct_change(14)

    # ========== SOPR 代理 (Spent Output Profit Ratio) ==========
    # LTH: 长期持有者 (180天回报)
    df["lth_sopr"] = close / close.shift(180)
    df["lth_sopr_ma_7"] = df["lth_sopr"].rolling(7).mean()
    # STH: 短期持有者 (30天回报)
    df["sth_sopr"] = close / close.shift(30)
    df["sth_sopr_ma_7"] = df["sth_sopr"].rolling(7).mean()
    # SOPR 变化趋势
    df["lth_sopr_change_7"] = df["lth_sopr"].pct_change(7)
    df["sth_sopr_change_7"] = df["sth_sopr"].pct_change(7)

    # ========== 活跃地址代理 ==========
    # 用成交量的滚动均值和波动代理
    df["active_addr_proxy"] = volume.rolling(7).mean()
    df["active_addr_change_7"] = df["active_addr_proxy"].pct_change(7)
    df["active_addr_change_14"] = df["active_addr_proxy"].pct_change(14)

    # ========== 矿工流出代理 ==========
    # 用价格波动率 * 成交量模拟矿工卖压
    df["miner_outflow_proxy"] = close.pct_change().rolling(30).std() * volume
    df["miner_outflow_ma_14"] = df["miner_outflow_proxy"].rolling(14).mean()

    # ========== 难度带代理 (Difficulty Ribbon) ==========
    # 用不同周期 MA 的收敛程度代理
    ma_short = close.rolling(9).mean()
    ma_long = close.rolling(128).mean()
    df["difficulty_ribbon_proxy"] = (ma_short - ma_long) / (ma_long + 1e-10)

    # ========== NUPL 代理 (Net Unrealized Profit/Loss) ==========
    # 简化：(market_price - realized_price) / market_price
    df["nupl_proxy"] = (close - realized_price) / (close + 1e-10)
    df["nupl_ma_14"] = df["nupl_proxy"].rolling(14).mean()

    # ========== 实体调整后的交易量代理 ==========
    body_ratio = abs(close - df["open"]) / (df["high"] - df["low"] + 1e-10)
    df["entity_adjusted_vol"] = volume * body_ratio
    df["entity_adjusted_vol_ma_10"] = df["entity_adjusted_vol"].rolling(10).mean()

    return df
