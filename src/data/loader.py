"""数据加载与校验模块."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# 必需列
REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}


def load_csv(
    path: str | Path,
    *,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """加载 CSV 数据文件并做基本校验.

    Parameters
    ----------
    path : str | Path
        CSV 文件路径
    start : str | None
        起始日期 (含, 如 '2018-01-01'); None 不过滤
    end : str | None
        结束日期 (含, 如 '2025-12-31'); None 不过滤
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

    # 日期过滤 (含边界) — 修复根因3: 之前 config 的 start/end 被忽略
    if start is not None:
        df = df[df.index >= pd.to_datetime(start)]
    if end is not None:
        df = df[df.index <= pd.to_datetime(end)]
    if len(df) == 0:
        raise ValueError(f"日期过滤后无数据: start={start}, end={end}")

    logger.info(f"数据加载完成: {path.name}, "
                f"时间范围 {df.index[0].date()} ~ {df.index[-1].date()}, "
                f"共 {len(df)} 条")
    return df
