"""Dip + Recovery 标签生成器.

反转策略核心标签：预测"跌后是否能反弹"

Label = 1 if (未来 T 天先跌 > dip_threshold) AND (从低点反弹 > recovery_threshold)

语义：
  - dip: 从现在到未来 T 天内最低点相对当前价格的跌幅
  - recovery: 未来 T 天收盘价相对未来最低点的反弹幅度

注意：此版本包含当天的 low，即从今天到 T 天后的最低点，
这更贴近实际交易场景——交易者关心的是"从现在起到未来 T 天内会跌多深"。
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.labels.registry import register_label_strategy

logger = logging.getLogger(__name__)


@register_label_strategy("dip_recovery")
def generate_dip_recovery_labels(
    df: pd.DataFrame,
    T: int = 21,
    dip_threshold: float = 0.05,
    recovery_threshold: float = 0.03,
) -> pd.Series:
    """生成 Dip + Recovery 标签.

    预测未来 T 天内是否会"先跌后弹"。

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

    # 从现在到未来 T 天的最低点 (包含当天的 low)
    future_low = low.rolling(T, min_periods=1).min()

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
    logger.info(f"Dip+Recovery 标签 (T={T}, dip={dip_threshold}, recovery={recovery_threshold}): "
                f"正例={pos_count}({pos_rate:.1%}), 负例={total-pos_count}({1-pos_rate:.1%})")

    return label


@register_label_strategy("excess_return")
def generate_excess_return_labels(
    df: pd.DataFrame,
    T: int = 21,
    rolling_window: int = 63,
) -> pd.Series:
    """生成超额收益标签.

    预测未来 T 天收益是否跑赢近期滚动平均。

    Parameters
    ----------
    df : pd.DataFrame
        必须包含 'close' 列
    T : int
        前瞻窗口长度（天数）
    rolling_window : int
        滚动平均窗口（天数）

    Returns
    -------
    pd.Series
        标签序列, 1=跑赢平均, 0=跑输平均
    """
    close = df["close"]

    past_return = close.pct_change(T)

    rolling_mean = past_return.rolling(rolling_window, min_periods=1).mean()

    future_return = close.pct_change(T).shift(-T)

    label = (future_return > rolling_mean).astype(float)

    label.iloc[-T:] = np.nan
    label.name = "label"

    valid = label.dropna()
    pos_rate = valid.mean()
    logger.info(f"超额收益标签 (T={T}, rolling={rolling_window}): "
                f"跑赢={pos_rate:.1%}, 跑输={1-pos_rate:.1%}")

    return label


@register_label_strategy("simple_return")
def generate_simple_return_labels(
    df: pd.DataFrame,
    T: int = 21,
) -> pd.Series:
    """生成简单正负收益标签.

    预测未来 T 天是涨还是跌。

    Parameters
    ----------
    df : pd.DataFrame
        必须包含 'close' 列
    T : int
        前瞻窗口长度（天数）

    Returns
    -------
    pd.Series
        标签序列, 1=涨, 0=跌
    """
    close = df["close"]

    future_return = close.pct_change(T).shift(-T)

    label = (future_return > 0).astype(float)

    label.iloc[-T:] = np.nan
    label.name = "label"

    valid = label.dropna()
    pos_rate = valid.mean()
    logger.info(f"简单收益标签 (T={T}): 涨={pos_rate:.1%}, 跌={1-pos_rate:.1%}")

    return label
