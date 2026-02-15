"""收益率标签生成器 - 用于回归目标预测."""

import logging

import numpy as np
import pandas as pd

from src.labels.registry import register_label_strategy

logger = logging.getLogger(__name__)


@register_label_strategy("return_rate")
def generate_return_rate_labels(
    df: pd.DataFrame,
    T: int = 14,
    X: float = 0.0,  # 参数保留以兼容配置
) -> pd.Series:
    """生成收益率标签 - 回归目标.

    直接预测未来 T 天的收益率百分比。

    Parameters
    ----------
    df : pd.DataFrame
        必须包含 'close' 列
    T : int
        前瞻窗口长度（天数）

    Returns
    -------
    pd.Series
        标签序列, 值为未来 T 天的收益率百分比
    """
    close = df["close"]

    # 未来 T 天的收益率
    future_return = close.pct_change(T).shift(-T) * 100  # 转换为百分比

    future_return.name = "label"

    # 去掉末尾 T 行（没有完整前瞻窗口）
    future_return.iloc[-T:] = np.nan

    # 统计
    valid = future_return.dropna()
    logger.info(f"收益率标签生成完成 (T={T}): "
                f"均值={valid.mean():.2f}%, "
                f"标准差={valid.std():.2f}%, "
                f"最小={valid.min():.2f}%, "
                f"最大={valid.max():.2f}%")

    return future_return
