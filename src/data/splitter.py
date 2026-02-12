"""数据集划分模块 — Walk-Forward / TimeSeriesCV."""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class FoldSplit:
    """一个 fold 的训练/测试索引."""
    fold_id: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int


def walk_forward_split(
    n_samples: int,
    init_train: int = 1500,
    oos_window: int = 63,
    step: int = 21,
) -> list[FoldSplit]:
    """Walk-Forward 数据划分.

    Parameters
    ----------
    n_samples : int
        样本总数
    init_train : int
        初始训练集大小
    oos_window : int
        样本外（测试）窗口大小
    step : int
        每次向前滑动的步长

    Returns
    -------
    list[FoldSplit]
        所有 fold 的划分信息
    """
    if init_train >= n_samples:
        raise ValueError(f"init_train({init_train}) >= n_samples({n_samples})")

    folds = []
    fold_id = 0
    train_end = init_train

    while train_end + oos_window <= n_samples:
        test_start = train_end
        test_end = min(train_end + oos_window, n_samples)

        folds.append(FoldSplit(
            fold_id=fold_id,
            train_start=0,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
        ))

        fold_id += 1
        train_end += step

    if not folds:
        raise ValueError("无法生成任何 fold，请检查参数")

    logger.info(f"Walk-Forward 划分: {len(folds)} folds, "
                f"init_train={init_train}, oos={oos_window}, step={step}")
    return folds


def expanding_window_split(
    n_samples: int,
    init_train: int = 1500,
    oos_window: int = 63,
    step: int = 21,
) -> list[FoldSplit]:
    """Expanding Window — 等同于 Walk-Forward（训练集持续扩大）.

    这个函数与 walk_forward_split 相同，保留作为语义别名。
    """
    return walk_forward_split(n_samples, init_train, oos_window, step)
