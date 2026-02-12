"""反转标签生成器.

三分类标签:
  0 = 顶部反转 (未来 T 天跌幅 >= X%)
  1 = 正常
  2 = 底部反转 (未来 T 天涨幅 >= X%)
"""

import logging

import numpy as np
import pandas as pd

from src.labels.registry import register_label_strategy

logger = logging.getLogger(__name__)


@register_label_strategy("reversal")
def generate_reversal_labels(
    df: pd.DataFrame,
    T: int = 14,
    X: float = 0.08,
) -> pd.Series:
    """生成反转标签.

    Parameters
    ----------
    df : pd.DataFrame
        必须包含 'close' 列
    T : int
        前瞻窗口长度（天数）
    X : float
        反转阈值（如 0.08 表示 8%）

    Returns
    -------
    pd.Series
        标签序列, 0=顶部反转, 1=正常, 2=底部反转
    """
    close = df["close"]

    # 未来 T 天的最大涨跌幅
    future_max = close.rolling(T).max().shift(-T)
    future_min = close.rolling(T).min().shift(-T)

    future_max_return = (future_max - close) / close
    future_min_return = (future_min - close) / close

    # 生成标签
    label = pd.Series(1, index=df.index, name="label")  # 默认正常
    label[future_min_return <= -X] = 0  # 顶部反转（未来大跌）
    label[future_max_return >= X] = 2   # 底部反转（未来大涨）

    # 如果同时满足两个条件，以跌幅优先（保守策略）
    both = (future_min_return <= -X) & (future_max_return >= X)
    n_both = both.sum()
    if n_both > 0:
        logger.warning(f"有 {n_both} 个样本同时触发顶部和底部标签，已按跌幅优先处理")

    # 去掉末尾 T 行（没有完整前瞻窗口）
    label.iloc[-T:] = np.nan

    # 统计
    valid = label.dropna()
    counts = valid.value_counts().sort_index()
    total = len(valid)
    logger.info(f"标签生成完成 (T={T}, X={X}): "
                f"顶部={counts.get(0, 0)}({counts.get(0, 0)/total*100:.1f}%), "
                f"正常={counts.get(1, 0)}({counts.get(1, 0)/total*100:.1f}%), "
                f"底部={counts.get(2, 0)}({counts.get(2, 0)/total*100:.1f}%)")

    return label
