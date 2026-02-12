"""滞后与滚动衍生特征集.

对核心指标添加 lag 和 rolling 特征，
捕捉指标变化趋势和动态背离信号。
"""

import pandas as pd

from src.features.registry import register_feature_set


# 核心指标列表 — 这些指标的 lag/rolling 衍生对反转识别最有价值
CORE_FEATURES = [
    "rsi_14", "macd", "macd_hist", "atr_14",
    "buy_pressure", "mvrv", "lth_sopr", "sth_sopr",
    "fgi", "volume_density",
]

LAG_PERIODS = [1, 2, 3, 7, 14]
ROLLING_WINDOWS = [3, 7, 14, 30]


@register_feature_set("lag_rolling")
def build_lag_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """为核心指标添加滞后和滚动窗口衍生特征.

    包含：lag 特征、rolling mean/std、变化率等。
    """
    df = df.copy()

    for feature in CORE_FEATURES:
        if feature not in df.columns:
            continue

        col = df[feature]

        # ---------- Lag 特征 ----------
        for lag in LAG_PERIODS:
            df[f"{feature}_lag{lag}"] = col.shift(lag)

        # ---------- Rolling 均值和标准差 ----------
        for w in ROLLING_WINDOWS:
            df[f"{feature}_ma{w}"] = col.rolling(w).mean()
            df[f"{feature}_std{w}"] = col.rolling(w).std()

        # ---------- 与滚动均值的偏离 ----------
        if f"{feature}_ma7" in df.columns:
            df[f"{feature}_dev_ma7"] = (col - df[f"{feature}_ma7"]) / (df[f"{feature}_ma7"].abs() + 1e-10)

        # ---------- 变化率 ----------
        for w in [1, 3, 7]:
            df[f"{feature}_roc_{w}"] = col.pct_change(w)

    return df
