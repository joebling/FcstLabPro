"""Dip + Recovery V1 标签生成器 (原始版本).

用于复现线上 v0302 部署版本

Label = 1 if (未来 T 天先跌 > dip_threshold) AND (从低点反弹 > recovery_threshold)

注意：此版本不包含当天的 low，即从明天开始 T 天的最低点。
这是原始 V1 版本使用的算法。
"""

import logging

import numpy as np
import pandas as pd

from src.labels.registry import register_label_strategy

logger = logging.getLogger(__name__)


@register_label_strategy("dip_recovery_v1")
def generate_dip_recovery_v1_labels(
    df: pd.DataFrame,
    T: int = 21,
    dip_threshold: float = 0.05,
    recovery_threshold: float = 0.03,
) -> pd.Series:
    """生成 Dip + Recovery V1 标签 (原始版本).

    预测未来 T 天内是否会"先跌后弹"（不包含当天）。

    Parameters
    ----------
    df : pd.DataFrame
        必须包含 'close' 和 'low' 列
    T : int
        前瞻窗口长度（天数）
    dip_threshold : float
        跌幅阈值（如 0.05 表示 5%）
    recovery_threshold : float
        反弹阈值（如 0.03 表示 3%）

    Returns
    -------
    pd.Series
        标签序列, 1=跌后反弹, 0=其他
    """
    close = df["close"]
    low = df["low"] if "low" in df.columns else df["close"]

    # 从明天开始 T 天的最低点（不包含当天）
    future_low = low.shift(-1).rolling(T, min_periods=1).min()

    # 相对当前价格的跌幅
    dip = (future_low - close) / close

    # T 天后的收盘价
    future_close = close.shift(-T)

    # 从最低点到 T 天后收盘价的反弹幅度
    recovery = (future_close - future_low) / future_low

    label = pd.Series(0, index=df.index, name="label")
    label[(dip < -dip_threshold) & (recovery > recovery_threshold)] = 1

    label.iloc[-T:] = np.nan

    valid = label.dropna()
    pos_count = valid.sum()
    total = len(valid)
    pos_rate = pos_count / total if total > 0 else 0
    logger.info(f"Dip+Recovery V1 标签 (T={T}, dip={dip_threshold}, recovery={recovery_threshold}): "
                f"正例={pos_count}({pos_rate:.1%}), 负例={total-pos_count}({1-pos_rate:.1%})")

    return label
