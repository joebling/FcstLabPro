"""增强型标签生成器.

改进 reversal 标签：
  1. 支持双向独立标签（同时满足涨跌条件时不互斥）
  2. 支持 future_return 回归标签
  3. 改进的二分类标签（基于 T 日收益率而非极值）
"""

import logging

import numpy as np
import pandas as pd

from src.labels.registry import register_label_strategy

logger = logging.getLogger(__name__)


@register_label_strategy("directional")
def generate_directional_labels(
    df: pd.DataFrame,
    T: int = 14,
    X: float = 0.05,
) -> pd.Series:
    """生成方向性标签 — 基于 T 日后的实际收盘价变化.

    与 reversal 标签的核心区别:
      - reversal: 看 T 日窗口内的极值（max/min），容易同时触发涨跌
      - directional: 看 T 日后的实际收盘价变化，方向明确
    
    三分类:
      0 = 下跌超过 X%
      1 = 震荡 (-X% ~ +X%)
      2 = 上涨超过 X%

    Parameters
    ----------
    df : pd.DataFrame
        必须包含 'close' 列
    T : int
        前瞻窗口长度（天数）
    X : float
        方向阈值（如 0.05 表示 5%）

    Returns
    -------
    pd.Series
        标签序列
    """
    close = df["close"]

    # T 日后的收益率（方向明确，不会同时触发涨跌）
    future_return = close.pct_change(T).shift(-T)

    # 生成标签
    label = pd.Series(1, index=df.index, name="label")  # 默认震荡
    label[future_return >= X] = 2   # 上涨
    label[future_return <= -X] = 0  # 下跌

    # 去掉末尾 T 行
    label.iloc[-T:] = np.nan

    # 统计
    valid = label.dropna()
    counts = valid.value_counts().sort_index()
    total = len(valid)
    logger.info(f"方向性标签生成完成 (T={T}, X={X}): "
                f"下跌={counts.get(0, 0)}({counts.get(0, 0)/total*100:.1f}%), "
                f"震荡={counts.get(1, 0)}({counts.get(1, 0)/total*100:.1f}%), "
                f"上涨={counts.get(2, 0)}({counts.get(2, 0)/total*100:.1f}%)")

    return label


@register_label_strategy("return_sign")
def generate_return_sign_labels(
    df: pd.DataFrame,
    T: int = 7,
    X: float = 0.0,
) -> pd.Series:
    """生成收益符号标签 — 最简单的二分类.

    0 = T 日后下跌（或持平）
    1 = T 日后上涨
    
    X 参数在此策略中不使用（阈值固定为 0）。
    """
    close = df["close"]
    future_return = close.pct_change(T).shift(-T)

    label = (future_return > 0).astype(float)
    label.iloc[-T:] = np.nan
    label.name = "label"

    valid = label.dropna()
    pos_rate = valid.mean()
    logger.info(f"收益符号标签 (T={T}): 上涨={pos_rate:.1%}, 下跌={1-pos_rate:.1%}")

    return label
