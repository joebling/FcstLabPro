"""Triple Barrier 简化版标签生成器（推荐用于生产）.

基于 Marcos López de Prado 的 Triple Barrier 方法，但简化为二分类，
更贴近真实交易逻辑，避免事后诸葛亮问题。

标签规则：
  1 = 做多信号（T 天内先触及止盈，未触及止损）
  0 = 不做多（其他情况）

优势：
  - 完全符合真实交易（有明确的止盈止损）
  - 避免 dip_recovery 的"事后诸葛亮"问题
  - 风险收益比可控
  - 时间序列上可解释性强
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.labels.registry import register_label_strategy

logger = logging.getLogger(__name__)


@register_label_strategy("triple_barrier_simple")
def generate_triple_barrier_simple_labels(
    df: pd.DataFrame,
    T: int = 21,
    pt: float = 0.06,
    sl: float = 0.04,
    include_today: bool = False,
) -> pd.Series:
    """生成 Triple Barrier 简化版二分类标签.

    Parameters
    ----------
    df : pd.DataFrame
        必须包含 'close', 'high', 'low' 列
    T : int
        最大持仓天数（时间屏障）
    pt : float
        止盈阈值（如 0.06 = 6%）
    sl : float
        止损阈值（如 0.04 = 4%）
    include_today : bool
        是否包含当天数据（适用于 8 点触发场景：
        - True: 包含当天（已知道 0-8 点数据）
        - False: 从明天开始（更保守）

    Returns
    -------
    pd.Series
        标签序列: 1=做多信号, 0=不做多
    """
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    n = len(close)

    labels = np.full(n, np.nan)

    # 确定起始偏移
    start_offset = 0 if include_today else 1

    for i in range(n - T):
        entry_price = close[i]
        upper_barrier = entry_price * (1 + pt)
        lower_barrier = entry_price * (1 - sl)

        hit_pt = False
        hit_sl = False

        # 遍历未来 T 天
        for j in range(i + start_offset, min(i + T + 1, n)):
            # 先检查止损（保守策略：如果同时触及双屏障，按止损处理）
            if low[j] <= lower_barrier:
                hit_sl = True
                break
            if high[j] >= upper_barrier:
                hit_pt = True
                break

        # Label = 1：先触及止盈，且未触及止损
        if hit_pt and not hit_sl:
            labels[i] = 1
        else:
            labels[i] = 0

    label_series = pd.Series(labels, index=df.index, name="label")

    # 统计
    valid = label_series.dropna()
    pos_count = int(valid.sum())
    total = len(valid)
    pos_rate = pos_count / total if total > 0 else 0

    include_str = "含当天" if include_today else "不含当天"
    logger.info(
        f"Triple Barrier 简化版标签 (T={T}, pt={pt*100:.1f}%, sl={sl*100:.1f}%, {include_str}): "
        f"做多信号={pos_count}({pos_rate:.1%}), 不做多={total-pos_count}({1-pos_rate:.1f})"
    )

    return label_series
