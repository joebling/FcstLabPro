"""Triple Barrier 标签生成器.

参考 Marcos López de Prado《Advances in Financial Machine Learning》
Chapter 3: The Triple-Barrier Method.

三重屏障标签:
  - 上屏障 (take-profit): 价格在 T 日内涨幅达到 +pt%
  - 下屏障 (stop-loss):   价格在 T 日内跌幅达到 -sl%
  - 时间屏障 (timeout):   T 日内未触及任何屏障

标签规则:
  2 = 先触及上屏障 (做多盈利)
  0 = 先触及下屏障 (做多亏损)
  1 = 超时未触及 (震荡/无方向)

优势:
  - 比 reversal 更贴近真实交易逻辑（有止盈止损概念）
  - 标签与交易决策直接对应
  - 可设置动态阈值（基于 ATR 自适应波动率）
"""

import logging

import numpy as np
import pandas as pd

from src.labels.registry import register_label_strategy

logger = logging.getLogger(__name__)


@register_label_strategy("triple_barrier")
def generate_triple_barrier_labels(
    df: pd.DataFrame,
    T: int = 14,
    X: float = 0.05,
    sl_ratio: float = 1.0,
    dynamic_threshold: bool = False,
    atr_window: int = 14,
    atr_multiplier: float = 2.0,
) -> pd.Series:
    """生成 Triple Barrier 标签.

    Parameters
    ----------
    df : pd.DataFrame
        必须包含 'close', 'high', 'low' 列
    T : int
        最大持仓天数（时间屏障）
    X : float
        止盈阈值（上屏障），如 0.05 = 5%
    sl_ratio : float
        止损/止盈比率。1.0 表示对称 (sl = pt)，
        0.5 表示止损是止盈的一半 (sl = 0.5 * pt)
    dynamic_threshold : bool
        是否使用 ATR 动态阈值替代固定 X
    atr_window : int
        ATR 计算窗口（仅 dynamic_threshold=True 时有效）
    atr_multiplier : float
        ATR 乘数，用于设定动态阈值（仅 dynamic_threshold=True 时有效）

    Returns
    -------
    pd.Series
        标签序列: 0=止损, 1=超时, 2=止盈
    """
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    n = len(close)

    # 计算动态阈值（如果启用）
    if dynamic_threshold:
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1]),
            ),
        )
        tr = np.insert(tr, 0, high[0] - low[0])
        atr = pd.Series(tr).rolling(atr_window).mean().values
        pt_thresholds = atr_multiplier * atr / close  # 动态止盈阈值
        sl_thresholds = pt_thresholds * sl_ratio       # 动态止损阈值
        logger.info(
            f"动态阈值 (ATR×{atr_multiplier}): "
            f"中位 pt={np.nanmedian(pt_thresholds)*100:.1f}%, "
            f"中位 sl={np.nanmedian(sl_thresholds)*100:.1f}%"
        )
    else:
        pt_thresholds = np.full(n, X)
        sl_thresholds = np.full(n, X * sl_ratio)

    labels = np.full(n, np.nan)

    for i in range(n - T):
        entry_price = close[i]
        pt = pt_thresholds[i]
        sl = sl_thresholds[i]

        if np.isnan(pt) or np.isnan(sl):
            continue

        upper_barrier = entry_price * (1 + pt)
        lower_barrier = entry_price * (1 - sl)

        hit_label = 1  # 默认超时

        for j in range(i + 1, min(i + T + 1, n)):
            # 先检查止损（保守，日内如果高低价同时触及双屏障，按止损）
            if low[j] <= lower_barrier:
                hit_label = 0  # 止损
                break
            if high[j] >= upper_barrier:
                hit_label = 2  # 止盈
                break

        labels[i] = hit_label

    label_series = pd.Series(labels, index=df.index, name="label")

    # 统计
    valid = label_series.dropna()
    counts = valid.value_counts().sort_index()
    total = len(valid)

    sl_pct = counts.get(0, 0) / total * 100 if total > 0 else 0
    timeout_pct = counts.get(1, 0) / total * 100 if total > 0 else 0
    tp_pct = counts.get(2, 0) / total * 100 if total > 0 else 0

    mode_str = "动态ATR" if dynamic_threshold else f"固定(pt={X*100:.0f}%, sl={X*sl_ratio*100:.0f}%)"
    logger.info(
        f"Triple Barrier 标签生成完成 (T={T}, {mode_str}): "
        f"止损={counts.get(0, 0)}({sl_pct:.1f}%), "
        f"超时={counts.get(1, 0)}({timeout_pct:.1f}%), "
        f"止盈={counts.get(2, 0)}({tp_pct:.1f}%)"
    )

    return label_series
