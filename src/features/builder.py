"""特征构建器 — 按配置组装特征集."""

import logging

import pandas as pd

from src.features.registry import get_feature_set

# 触发所有特征集的注册（导入即注册）
import src.features.technical  # noqa: F401
import src.features.volume     # noqa: F401
import src.features.flow       # noqa: F401

logger = logging.getLogger(__name__)


def build_features(
    df: pd.DataFrame,
    feature_sets: list[str],
    drop_na_method: str = "ffill_then_drop",
) -> pd.DataFrame:
    """按配置组装特征.

    Parameters
    ----------
    df : pd.DataFrame
        原始 OHLCV 数据
    feature_sets : list[str]
        要使用的特征集名称列表, 如 ["technical", "volume"]
    drop_na_method : str
        NaN 处理方式: "ffill_then_drop" | "drop"

    Returns
    -------
    pd.DataFrame
        构建完特征后的 DataFrame（已处理 NaN）
    """
    df = df.copy()
    n_cols_before = len(df.columns)

    for name in feature_sets:
        func = get_feature_set(name)
        df = func(df)
        logger.info(f"特征集 '{name}' 构建完成, 当前列数: {len(df.columns)}")

    n_features = len(df.columns) - n_cols_before
    logger.info(f"共构建 {n_features} 个特征")

    # 处理 NaN
    n_before = len(df)
    if drop_na_method == "ffill_then_drop":
        df = df.ffill().dropna()
    elif drop_na_method == "drop":
        df = df.dropna()
    else:
        raise ValueError(f"未知的 drop_na_method: {drop_na_method}")

    n_dropped = n_before - len(df)
    if n_dropped > 0:
        logger.info(f"NaN 处理后丢弃 {n_dropped} 行, 剩余 {len(df)} 行")

    return df


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """获取特征列名（排除 OHLCV 原始列和标签列）."""
    exclude = {"open", "high", "low", "close", "volume",
               "quote_volume", "trades", "taker_buy_base",
               "taker_buy_quote", "label", "date"}
    return [c for c in df.columns if c.lower() not in exclude]
