"""带过滤的方向性标签生成器.

基于 directional 标签，但增加技术指标过滤条件，提高信号质量。

Label = 1 if:
  (1) 未来 T 天收益率 > X%
  AND
  (2) 当前满足技术过滤条件（如 RSI 超卖、价格在 MA 之下等）

优势：
  - 简单直接，易于理解
  - 技术过滤可以减少噪音
  - 与传统技术分析结合
"""

import logging

import numpy as np
import pandas as pd

from src.labels.registry import register_label_strategy

logger = logging.getLogger(__name__)


def _calculate_rsi(prices: pd.Series, window: int = 14) -> pd.Series:
    """计算 RSI 指标."""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _calculate_sma(prices: pd.Series, window: int) -> pd.Series:
    """计算 SMA."""
    return prices.rolling(window=window).mean()


@register_label_strategy("directional_filtered")
def generate_directional_filtered_labels(
    df: pd.DataFrame,
    T: int = 21,
    X: float = 0.05,
    rsi_window: int = 14,
    rsi_threshold: float = 40.0,
    ma_window: int = 50,
    require_below_ma: bool = True,
) -> pd.Series:
    """生成带技术过滤的方向性标签.

    Parameters
    ----------
    df : pd.DataFrame
        必须包含 'close' 列
    T : int
        前瞻窗口长度（天数）
    X : float
        上涨阈值（如 0.05 = 5%）
    rsi_window : int
        RSI 计算窗口
    rsi_threshold : float
        RSI 阈值（低于此值才考虑做多）
    ma_window : int
        移动平均窗口
    require_below_ma : bool
        是否要求价格在 MA 之下

    Returns
    -------
    pd.Series
        标签序列, 1=做多信号, 0=不做多
    """
    close = df["close"]

    # 计算技术指标
    rsi = _calculate_rsi(close, rsi_window)
    sma = _calculate_sma(close, ma_window)

    # 未来 T 天收益率
    future_return = close.pct_change(T).shift(-T)

    # 技术过滤条件
    rsi_filter = rsi < rsi_threshold
    ma_filter = (close < sma) if require_below_ma else pd.Series(True, index=df.index)

    # 生成标签
    label = pd.Series(0, index=df.index, name="label")
    label[(future_return >= X) & rsi_filter & ma_filter] = 1

    # 去掉末尾 T 行
    label.iloc[-T:] = np.nan

    # 统计
    valid = label.dropna()
    pos_count = int(valid.sum())
    total = len(valid)
    pos_rate = pos_count / total if total > 0 else 0

    logger.info(
        f"带过滤方向性标签 (T={T}, X={X*100:.1f}%, "
        f"RSI<{rsi_threshold}, {'Price<SMA' if require_below_ma else 'No MA filter'}): "
        f"做多信号={pos_count}({pos_rate:.1f}), 不做多={total-pos_count}({1-pos_rate:.1f})"
    )

    return label
