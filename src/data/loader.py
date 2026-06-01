"""数据加载与校验模块.

2026-06-01 增强 (参考 docs/lessons/lesson_0601_data_governance_regime_shift.md):
- 加载时计算并打印 csv sha256 + effective range
- 支持 config 里 expected_sha256 / expected_effective_rows 可选校验 (不一致 WARN 不阻塞)
- 防御 BTC csv 被默默扩展导致 baseline 漂移
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# 必需列
REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}

# sha256 缓存 (避免同进程重复计算)
_SHA256_CACHE: dict[str, str] = {}


def _compute_file_sha256(path: Path) -> str:
    """计算文件完整 sha256, 带 mtime-aware 缓存."""
    key = f"{path}|{path.stat().st_mtime_ns}"
    if key in _SHA256_CACHE:
        return _SHA256_CACHE[key]

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    digest = h.hexdigest()
    _SHA256_CACHE[key] = digest
    return digest


def load_csv(
    path: str | Path,
    *,
    start: str | None = None,
    end: str | None = None,
    expected_sha256: str | None = None,
    expected_effective_rows: int | None = None,
) -> pd.DataFrame:
    """加载 CSV 数据文件并做基本校验.

    Parameters
    ----------
    path : str | Path
        CSV 文件路径
    start : str | None
        起始日期 (含, 如 '2020-01-01'); None 不过滤
    end : str | None
        结束日期 (含, 如 '2025-12-31'); None 不过滤
    expected_sha256 : str | None
        期望的 CSV 文件 sha256 (full hex). 不一致仅 WARN, 不阻塞.
        防御 BTC csv 被默默扩展 (lesson_0601).
    expected_effective_rows : int | None
        期望的过滤后行数. 不一致仅 WARN.

    Returns
    -------
    pd.DataFrame
        加载并过滤后的 DataFrame, attrs 含 sha256/rows/range 元数据.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"数据文件不存在: {path}")

    # ====== 文件级 sha256 校验 (在过滤前, 反映 csv 实际状态) ======
    actual_sha256 = _compute_file_sha256(path)
    file_size = path.stat().st_size

    if expected_sha256 is not None:
        if actual_sha256 != expected_sha256:
            logger.warning("=" * 70)
            logger.warning("⚠️  CSV SHA256 不一致! 数据文件可能被修改/扩展")
            logger.warning(f"    file:     {path.name}")
            logger.warning(f"    expected: {expected_sha256}")
            logger.warning(f"    actual:   {actual_sha256}")
            logger.warning("    参考: docs/lessons/lesson_0601_data_governance_regime_shift.md")
            logger.warning("=" * 70)
        else:
            logger.info(f"  ✅ CSV SHA256 验证通过: {actual_sha256[:16]}...")

    # ====== 加载 + 标准化 ======
    df = pd.read_csv(path, parse_dates=True, index_col=0)
    df.columns = [c.lower().strip() for c in df.columns]

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"数据缺少必需列: {missing}")

    if not pd.api.types.is_datetime64_any_dtype(df.index):
        df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    raw_rows = len(df)
    raw_start = df.index[0].date() if len(df) else None
    raw_end = df.index[-1].date() if len(df) else None

    # 去重
    n_dup = df.index.duplicated().sum()
    if n_dup > 0:
        logger.warning(f"发现 {n_dup} 个重复日期，已去重")
        df = df[~df.index.duplicated(keep="last")]

    # ====== 日期过滤 (含边界) ======
    if start is not None:
        df = df[df.index >= pd.to_datetime(start)]
    if end is not None:
        df = df[df.index <= pd.to_datetime(end)]
    if len(df) == 0:
        raise ValueError(f"日期过滤后无数据: start={start}, end={end}")

    eff_rows = len(df)
    eff_start = df.index[0].date()
    eff_end = df.index[-1].date()

    # ====== 富日志: 让数据治理一目了然 ======
    logger.info(
        f"[DATA] {path.name} | sha256={actual_sha256[:16]}... | "
        f"size={file_size:,}B | raw={raw_rows} rows ({raw_start}~{raw_end})"
    )
    logger.info(
        f"[DATA] effective={eff_rows} rows ({eff_start}~{eff_end}) | "
        f"filter start={start}, end={end}"
    )

    # ====== effective_rows 校验 ======
    if expected_effective_rows is not None and eff_rows != expected_effective_rows:
        logger.warning(
            f"⚠️  effective_rows 不一致: expected={expected_effective_rows}, "
            f"actual={eff_rows} (差 {eff_rows - expected_effective_rows:+d}). "
            f"参考: docs/lessons/lesson_0601_data_governance_regime_shift.md"
        )

    # ====== metadata 存入 attrs (下游 manifest 可读取) ======
    df.attrs["data_path"] = str(path)
    df.attrs["data_sha256"] = actual_sha256
    df.attrs["data_file_size_bytes"] = file_size
    df.attrs["data_raw_rows"] = raw_rows
    df.attrs["data_raw_start"] = str(raw_start)
    df.attrs["data_raw_end"] = str(raw_end)
    df.attrs["data_effective_rows"] = eff_rows
    df.attrs["data_effective_start"] = str(eff_start)
    df.attrs["data_effective_end"] = str(eff_end)
    df.attrs["data_filter_start"] = start
    df.attrs["data_filter_end"] = end

    return df
