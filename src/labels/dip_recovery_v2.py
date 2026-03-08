"""改进版 Dip + Recovery 标签生成器 V2.

修复 dip_recovery_v1 的核心问题：
1. 用未来最高点而不是 T 天后收盘价计算反弹
2. 增加"下跌必须在前 N 天内发生"的条件（避免先涨后跌）
3. 提高阈值，降低正例率
4. 可配置是否包含当天数据

Label = 1 if:
  (1) 未来 T 天内最低点相对当前下跌 > dip_threshold
  AND
  (2) 最低点必须在前 dip_window 天内出现（避免先涨后跌）
  AND
  (3) 从最低点到未来 T 天内最高点的反弹 > recovery_threshold
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.labels.registry import register_label_strategy

logger = logging.getLogger(__name__)


@register_label_strategy("dip_recovery_v2")
def generate_dip_recovery_v2_labels(
    df: pd.DataFrame,
    T: int = 21,
    dip_threshold: float = 0.07,
    recovery_threshold: float = 0.05,
    dip_window: int = 10,
    include_today: bool = False,
) -> pd.Series:
    """生成改进版 Dip + Recovery V2 标签.

    Parameters
    ----------
    df : pd.DataFrame
        必须包含 'close', 'high', 'low' 列
    T : int
        前瞻窗口长度（天数）
    dip_threshold : float
        跌幅阈值（如 0.07 = 7%）
    recovery_threshold : float
        反弹阈值（如 0.05 = 5%）
    dip_window : int
        下跌必须在前 dip_window 天内出现（避免先涨后跌）
    include_today : bool
        是否包含当天数据

    Returns
    -------
    pd.Series
        标签序列, 1=跌后反弹, 0=其他
    """
    close = df["close"]
    low = df["low"] if "low" in df.columns else df["close"]
    high = df["high"] if "high" in df.columns else df["close"]

    n = len(df)
    label = pd.Series(0, index=df.index, name="label")

    # 确定起始偏移
    start_offset = 0 if include_today else 1

    for i in range(n - T):
        # 未来窗口的起始和结束位置（用位置索引而非标签索引
        window_start_pos = i + start_offset
        window_end_pos = min(i + T + 1, n)

        if window_start_pos >= window_end_pos:
            continue

        # 未来窗口的数据
        future_low_window = low.iloc[window_start_pos:window_end_pos]
        future_high_window = high.iloc[window_start_pos:window_end_pos]

        # 1. 找到未来 T 天内的最低点（用位置索引）
        min_pos_in_window = future_low_window.argmin()
        min_val = future_low_window.iloc[min_pos_in_window]

        # 计算跌幅
        dip = (min_val - close.iloc[i]) / close.iloc[i]

        # 2. 检查最低点是否在前 dip_window 天内（避免先涨后跌）
        days_to_min = min_pos_in_window  # 从窗口开始到最低点的天数
        dip_in_window = days_to_min <= dip_window

        # 3. 计算从最低点到未来最高点的反弹
        # 只考虑最低点之后的数据
        high_after_dip = future_high_window.iloc[min_pos_in_window:]
        max_after_dip = high_after_dip.max()
        recovery = (max_after_dip - min_val) / min_val

        # 标签赋值
        if (dip < -dip_threshold) and dip_in_window and (recovery > recovery_threshold):
            label.iloc[i] = 1

    # 最后 T 行设为 NaN
    label.iloc[-T:] = np.nan

    # 统计
    valid = label.dropna()
    pos_count = int(valid.sum())
    total = len(valid)
    pos_rate = pos_count / total if total > 0 else 0

    include_str = "含当天" if include_today else "不含当天"
    logger.info(
        f"Dip+Recovery V2 标签 (T={T}, dip={dip_threshold*100:.1f}%, recovery={recovery_threshold*100:.1f}%, "
        f"dip_window={dip_window}, {include_str}): "
        f"正例={pos_count}({pos_rate:.1%}), 负例={total-pos_count}({1-pos_rate:.1f})"
    )

    return label
