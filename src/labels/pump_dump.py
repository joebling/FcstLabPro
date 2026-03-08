"""Pump + Dump 标签生成器.

dip_recovery 的镜像策略：预测"涨后是否会回落"

Label = 1 if (未来 T 天先涨 > pump_threshold) AND (从高点回落 > dump_threshold)

语义：
  - pump: 未来 T 天内最高点相对当前价格的涨幅
  - dump: 未来 T 天收盘价相对未来最高点的跌幅

与 dip_recovery 的对称关系：
  dip_recovery:  先跌后弹 (看多信号)
  pump_dump:     先涨后跌 (看空信号)
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.labels.registry import register_label_strategy

logger = logging.getLogger(__name__)


@register_label_strategy("pump_dump")
def generate_pump_dump_labels(
    df: pd.DataFrame,
    T: int = 21,
    pump_threshold: float = 0.05,
    dump_threshold: float = 0.03,
) -> pd.Series:
    """Generate Pump + Dump labels.

    Predict whether the price will "pump then dump" within the next T days.
    This is the mirror image of dip_recovery.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain 'close' and 'high' columns.
    T : int
        Look-ahead window in days.
    pump_threshold : float
        Pump threshold (e.g. 0.05 = 5% rise from current price to future high).
    dump_threshold : float
        Dump threshold (e.g. 0.03 = 3% drop from future high to future close).

    Returns
    -------
    pd.Series
        Label series. 1 = pump then dump, 0 = otherwise.
    """
    close = df["close"]
    high = df["high"] if "high" in df.columns else df["close"]

    # 从现在到未来 T 天的最高点 (包含当天)
    future_high = high.rolling(T, min_periods=1).max()

    # Pump: how much the price rises from current close to future high
    pump = (future_high - close) / close

    # Future close: close price T days from now
    future_close = close.shift(-T)

    # Dump: how much the price falls from future high to future close
    # Negative value = price dropped from peak
    dump = (future_close - future_high) / future_high

    # Label = 1 when pump exceeds threshold AND dump exceeds threshold
    label = pd.Series(0, index=df.index, name="label")
    label[(pump > pump_threshold) & (dump < -dump_threshold)] = 1

    # NaN out the last T rows (no future data)
    label.iloc[-T:] = np.nan

    # Log distribution
    valid = label.dropna()
    pos_count = int(valid.sum())
    total = len(valid)
    pos_rate = pos_count / total if total > 0 else 0
    logger.info(
        f"Pump+Dump 标签 (T={T}, pump={pump_threshold}, dump={dump_threshold}): "
        f"正例={pos_count}({pos_rate:.1%}), 负例={total - pos_count}({1 - pos_rate:.1%})"
    )

    return label
