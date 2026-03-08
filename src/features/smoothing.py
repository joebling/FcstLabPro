"""数据平滑/去噪模块.

灵感来源: 论文 arXiv:2506.05764v2 (Wang, 2025)
"Better Inputs Matter More Than Stacking Another Hidden Layer"

论文核心发现: Savitzky-Golay 平滑是提升预测性能的最大单一因素,
在所有模型和所有预测窗口上均有显著提升。

本模块提供:
  1. Savitzky-Golay 因果平滑 (无未来泄漏)
  2. 可配置的平滑目标列
  3. 与 builder.py 的无缝集成

重要: 使用 causal (单侧) 滤波避免 look-ahead bias。
标准 SG 滤波是双侧的，会使用未来数据点，在金融时序中不可接受。
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 默认需要平滑的 OHLCV 列
DEFAULT_SMOOTH_COLUMNS = ["close", "high", "low", "volume"]


def _savgol_causal(
    series: np.ndarray,
    window: int = 11,
    polyorder: int = 3,
) -> np.ndarray:
    """因果 Savitzky-Golay 平滑 (只用过去数据点, 无未来泄漏).

    标准 SG 滤波用 [-m, +m] 的双侧窗口,
    因果版本只用 [-window+1, 0] 的单侧窗口。

    实现方式: 对每个时间点 t, 用 [t-window+1, t] 的数据
    拟合 polyorder 阶多项式, 取 t 处的拟合值。

    Parameters
    ----------
    series : np.ndarray
        输入时间序列
    window : int
        滑动窗口大小 (必须 > polyorder)
    polyorder : int
        多项式阶数

    Returns
    -------
    np.ndarray
        平滑后的序列 (前 window-1 个点保持原值)
    """
    if window <= polyorder:
        raise ValueError(
            f"window ({window}) 必须大于 polyorder ({polyorder})"
        )

    n = len(series)
    result = series.copy()

    if n < window:
        return result

    # 预计算 Vandermonde 矩阵 (固定窗口大小, 只算一次)
    x = np.arange(window, dtype=float)
    V = np.vander(x, N=polyorder + 1, increasing=True)
    # 求解系数的伪逆 (V^T V)^{-1} V^T
    VtV_inv_Vt = np.linalg.pinv(V)
    # 我们只需要最后一个点 (x = window-1) 的拟合值
    # = V[window-1] @ coefficients = V[-1] @ (VtV_inv_Vt @ y)
    # 合并为一步: weights = V[-1] @ VtV_inv_Vt
    weights = V[-1] @ VtV_inv_Vt  # shape: (window,)

    # 滑动卷积
    for t in range(window - 1, n):
        result[t] = weights @ series[t - window + 1: t + 1]

    return result


def apply_smoothing(
    df: pd.DataFrame,
    method: Literal["savgol", "none"] = "savgol",
    window: int = 11,
    polyorder: int = 3,
    columns: Optional[list[str]] = None,
    suffix: str = "",
    keep_original: bool = False,
) -> pd.DataFrame:
    """对 DataFrame 指定列应用平滑去噪.

    Parameters
    ----------
    df : pd.DataFrame
        输入数据
    method : str
        平滑方法: "savgol" | "none"
    window : int
        SG 滤波窗口大小 (必须为奇数, 自动修正)
    polyorder : int
        SG 多项式阶数
    columns : list[str] | None
        要平滑的列名, None 时使用默认 OHLCV 列
    suffix : str
        平滑后列名后缀, 空字符串表示替换原列
    keep_original : bool
        如果 True 且 suffix 非空, 保留原列的同时添加平滑列

    Returns
    -------
    pd.DataFrame
        平滑后的 DataFrame
    """
    if method == "none":
        return df

    df = df.copy()
    columns = columns or DEFAULT_SMOOTH_COLUMNS

    # 确保 window 为奇数 (SG 滤波的常规要求)
    if window % 2 == 0:
        window += 1
        logger.info(f"SG window 修正为奇数: {window}")

    smoothed_count = 0

    for col in columns:
        if col not in df.columns:
            continue

        values = df[col].values.astype(float)

        # 跳过全 NaN 列
        if np.all(np.isnan(values)):
            continue

        # 处理 NaN: 先前向填充, 平滑后还原 NaN 位置
        nan_mask = np.isnan(values)
        if nan_mask.any():
            values = pd.Series(values).ffill().bfill().values

        if method == "savgol":
            smoothed = _savgol_causal(values, window, polyorder)
        else:
            raise ValueError(f"未知平滑方法: {method}")

        # 还原 NaN
        if nan_mask.any():
            smoothed[nan_mask] = np.nan

        target_col = f"{col}{suffix}" if suffix else col

        if suffix and keep_original:
            df[target_col] = smoothed
        else:
            df[target_col] = smoothed

        smoothed_count += 1

    logger.info(
        f"数据平滑完成: method={method}, window={window}, "
        f"polyorder={polyorder}, 平滑了 {smoothed_count} 列"
    )

    return df
