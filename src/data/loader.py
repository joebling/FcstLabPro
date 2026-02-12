"""数据加载与校验模块."""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# 必需列
REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}


def load_csv(path: str | Path) -> pd.DataFrame:
    """加载 CSV 数据文件并做基本校验.

    Parameters
    ----------
    path : str | Path
        CSV 文件路径

    Returns
    -------
    pd.DataFrame
        校验通过的 OHLCV 数据，index 为 DatetimeIndex
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"数据文件不存在: {path}")

    df = pd.read_csv(path, parse_dates=True, index_col=0)

    # 统一列名小写
    df.columns = [c.lower().strip() for c in df.columns]

    # 校验必需列
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"数据缺少必需列: {missing}")

    # 确保 index 是 datetime
    if not pd.api.types.is_datetime64_any_dtype(df.index):
        df.index = pd.to_datetime(df.index)

    df = df.sort_index()

    # 去重
    n_dup = df.index.duplicated().sum()
    if n_dup > 0:
        logger.warning(f"发现 {n_dup} 个重复日期，已去重")
        df = df[~df.index.duplicated(keep="last")]

    logger.info(f"数据加载完成: {path.name}, "
                f"时间范围 {df.index[0].date()} ~ {df.index[-1].date()}, "
                f"共 {len(df)} 条")
    return df
