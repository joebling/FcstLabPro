"""可复现性工具."""

import random

import numpy as np


def set_global_seed(seed: int = 42) -> None:
    """设置全局随机种子以保证可复现性."""
    random.seed(seed)
    np.random.seed(seed)

    # 尝试设置 LightGBM 等库的种子（通过参数传入）
    # 这里只负责 Python 和 NumPy 的全局种子
