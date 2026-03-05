"""路径依赖的触达标签生成器 (touch_X_within_T).

与 directional_filtered 的区别：
- directional_filtered: 第 T 天收盘价 >= 入场价 * (1+X) 才算正例
- touch_filtered: 窗口 [1, T] 内任一天最高价 >= 入场价 * (1+X) 即算正例

这与生产策略的 --take-profit 逻辑一致：
止盈是"路径内触达即平仓"，而非"持有到期才看收益"。

标签-策略一致性是本策略的核心价值。
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


def _check_touch_within_window(
    high: pd.Series,
    close: pd.Series,
    T: int,
    X: float,
) -> pd.Series:
    """检查未来 T 天内最高价是否触达 close * (1+X).

    Parameters
    ----------
    high : pd.Series
        每日最高价
    close : pd.Series
        每日收盘价（作为入场基准）
    T : int
        前瞻窗口长度
    X : float
        触达阈值（如 0.04 = 4%）

    Returns
    -------
    pd.Series
        bool 序列，True 表示窗口内触达过目标价
    """
    n = len(close)
    touched = pd.Series(False, index=close.index)

    for i in range(n - T):
        target_price = close.iloc[i] * (1 + X)
        future_highs = high.iloc[i + 1 : i + 1 + T]
        if future_highs.max() >= target_price:
            touched.iloc[i] = True

    return touched


@register_label_strategy("touch_filtered")
def generate_touch_filtered_labels(
    df: pd.DataFrame,
    T: int = 21,
    X: float = 0.04,
    rsi_window: int = 14,
    rsi_threshold: float = 45.0,
    ma_window: int = 50,
    require_below_ma: bool = True,
) -> pd.Series:
    """生成路径依赖的触达标签（带技术过滤）.

    Label = 1 if:
      (1) 未来 T 天内最高价曾触达 close * (1+X)
      AND
      (2) 当前满足技术过滤条件（RSI 超卖、价格在 MA 之下等）

    Parameters
    ----------
    df : pd.DataFrame
        必须包含 'close' 和 'high' 列
    T : int
        前瞻窗口长度（天数）
    X : float
        触达阈值（如 0.04 = 4%）
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
    high = df["high"]

    # 计算技术指标
    rsi = _calculate_rsi(close, rsi_window)
    sma = _calculate_sma(close, ma_window)

    # 路径依赖：窗口内是否触达目标价
    touched = _check_touch_within_window(high, close, T, X)

    # 技术过滤条件
    rsi_filter = rsi < rsi_threshold
    ma_filter = (close < sma) if require_below_ma else pd.Series(True, index=df.index)

    # 生成标签
    label = pd.Series(0, index=df.index, name="label")
    label[touched & rsi_filter & ma_filter] = 1

    # 去掉末尾 T 行（无法计算前瞻窗口）
    label.iloc[-T:] = np.nan

    # 统计
    valid = label.dropna()
    pos_count = int(valid.sum())
    total = len(valid)
    pos_rate = pos_count / total if total > 0 else 0

    logger.info(
        f"触达标签 touch_filtered (T={T}, X={X*100:.1f}%, "
        f"RSI<{rsi_threshold}, {'Price<SMA' if require_below_ma else 'No MA filter'}): "
        f"做多信号={pos_count}({pos_rate:.1%}), "
        f"不做多={total - pos_count}({1 - pos_rate:.1%})"
    )

    return label
