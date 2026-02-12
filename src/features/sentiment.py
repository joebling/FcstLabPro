"""情绪与宏观特征集 — 基于价格/成交量行为模拟情绪指标.

在没有外部 API 时，使用价格动量和波动率
模拟 FGI、Google Trend、流动性等指标的代理特征。
"""

import numpy as np
import pandas as pd

from src.features.registry import register_feature_set


@register_feature_set("sentiment")
def build_sentiment_features(df: pd.DataFrame) -> pd.DataFrame:
    """构建模拟情绪与宏观特征.

    包含：FGI 代理、Google Trend 代理、VIX 代理、
    流动性代理、恐慌/贪婪极端值标记等。
    """
    df = df.copy()
    close = df["close"]
    volume = df["volume"]

    # ========== 恐惧贪婪指数代理 (FGI) ==========
    # 综合 30 日动量 + 波动率 + 成交量变化
    price_momentum = close.pct_change(30)
    volatility = close.pct_change().rolling(30).std()
    vol_momentum = volume.pct_change(7).rolling(7).mean()

    fgi_raw = 50 + price_momentum * 100 - volatility * 200 + vol_momentum * 20
    df["fgi"] = fgi_raw.clip(0, 100)
    df["fgi_ma_7"] = df["fgi"].rolling(7).mean()
    df["fgi_ma_14"] = df["fgi"].rolling(14).mean()

    # 极端值标记
    df["fgi_extreme_fear"] = (df["fgi"] < 20).astype(int)
    df["fgi_extreme_greed"] = (df["fgi"] > 80).astype(int)

    # ========== Google Trend 代理 ==========
    # 用成交量活跃度代理搜索热度
    df["gtrend_proxy"] = volume.rolling(7).mean() / (volume.rolling(30).mean() + 1e-10) * 50
    df["gtrend_proxy_ma_14"] = df["gtrend_proxy"].rolling(14).mean()

    # ========== VIX 代理（波动率指数） ==========
    for w in [14, 30, 60]:
        df[f"vix_proxy_{w}"] = close.pct_change().rolling(w).std() * 100

    # VIX 变化趋势
    df["vix_proxy_change_7"] = df["vix_proxy_30"].pct_change(7)

    # ========== 流动性代理 ==========
    # 用价格长期趋势和波动率反映宏观流动性
    df["liquidity_proxy"] = 100 - close.pct_change().rolling(90).std() * 1000

    # ========== 市场热度指标 ==========
    # 成交量爆发（相对均值的倍数）
    df["volume_spike_10"] = volume / (volume.rolling(10).mean() + 1e-10)
    df["volume_spike_30"] = volume / (volume.rolling(30).mean() + 1e-10)

    # 连续上涨/下跌天数
    daily_ret = close.pct_change()
    up = (daily_ret > 0).astype(int)
    down = (daily_ret < 0).astype(int)
    # 连续上涨天数
    streak_up = up.copy()
    for i in range(1, len(streak_up)):
        if streak_up.iloc[i] == 1:
            streak_up.iloc[i] = streak_up.iloc[i - 1] + 1
    df["consecutive_up_days"] = streak_up
    # 连续下跌天数
    streak_down = down.copy()
    for i in range(1, len(streak_down)):
        if streak_down.iloc[i] == 1:
            streak_down.iloc[i] = streak_down.iloc[i - 1] + 1
    df["consecutive_down_days"] = streak_down

    # ========== 价格极端位置（距离历史高/低点） ==========
    for w in [30, 90, 180, 365]:
        roll_max = close.rolling(w, min_periods=1).max()
        roll_min = close.rolling(w, min_periods=1).min()
        df[f"dist_from_high_{w}d"] = (close - roll_max) / (roll_max + 1e-10)
        df[f"dist_from_low_{w}d"] = (close - roll_min) / (roll_min + 1e-10)

    return df
