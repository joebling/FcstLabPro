"""数据新鲜度强校验 — live pipeline 的数据守门员 (决策 A: 缺失/过期一律 FATAL).

研究态 (run_experiment / backtest) **不应** import 这里。本模块只服务于
生产 pipeline (scripts/run_production_pipeline.py)，对应 docs/reviews/cr_0529 §B。

为什么不在 feature pipeline 里偷偷 ffill stale FGI:
  - src/features/external.py 会把最后一个 FGI 值一路前向填充到最新交易日,
    stale 81 天也照跑不误。研究回放可以接受 (历史数据本就完整),
    但 live 推理吃到 stale 情绪特征 = 信号失真却无人知晓。
  - 这里把「FGI 必须够新」从默契变成显式契约: 文件不存在 / 列不对 /
    last_date 落后超过 SLA → 抛 DataFreshnessError, pipeline 直接 halt。

SLA 来源: models/production/active.yaml::data_freshness (不硬编码)。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ACTIVE_YAML = PROJECT_ROOT / "models" / "production" / "active.yaml"
OHLCV_PATH = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"
FGI_PATH = PROJECT_ROOT / "data" / "external" / "fear_greed_index.csv"

# active.yaml 缺 data_freshness 时的兜底默认 (与文档 SLA=2 天一致)
_DEFAULT_OHLCV_SLA = 2
_DEFAULT_FGI_SLA = 2


def _rel(path: Path) -> str:
    """尽量用项目相对路径; 不在项目下 (如测试 tmp_path) 则回退绝对路径."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return os.fspath(path)


class DataFreshnessError(RuntimeError):
    """数据缺失或过期 — live pipeline 必须 halt 的硬错误."""


@dataclass(frozen=True)
class FreshnessReport:
    """单个数据源的新鲜度审计结果 (写入监控/账本用)."""

    source: str
    path: str
    rows: int
    start: str
    end: str
    stale_days: int
    sla_days: int
    ok: bool
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "path": self.path,
            "rows": self.rows,
            "start": self.start,
            "end": self.end,
            "stale_days": self.stale_days,
            "sla_days": self.sla_days,
            "ok": self.ok,
            "detail": self.detail,
        }


def load_freshness_sla(path: Path | None = None) -> dict[str, int]:
    """从 active.yaml 读取 freshness SLA (天). 缺失则用兜底默认."""
    path = path or ACTIVE_YAML
    cfg = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text()) or {}
        cfg = raw.get("data_freshness", {}) or {}
    return {
        "ohlcv_max_stale_days": int(cfg.get("ohlcv_max_stale_days", _DEFAULT_OHLCV_SLA)),
        "fgi_max_stale_days": int(cfg.get("fgi_max_stale_days", _DEFAULT_FGI_SLA)),
    }


def _read_dated_csv(path: Path, value_col: str | None = None) -> pd.DataFrame:
    """读 CSV 并标准化出 date 索引; 缺文件/缺列直接 FATAL."""
    if not path.exists():
        raise DataFreshnessError(
            f"数据文件不存在: {_rel(path)} — "
            f"live pipeline 拒绝在缺数据情况下出信号 (决策 A)。"
        )
    df = pd.read_csv(path)
    # 统一找 date 列 (兼容 index_col=0 的 OH列的 FGI)
    cols_lower = {c.lower(): c for c in df.columns}
    if "date" in cols_lower:
        df = df.rename(columns={cols_lower["date"]: "date"})
    else:
        df = df.rename(columns={df.columns[0]: "date"})
    df["date"] = pd.to_datetime(df["date"])
    if value_col is not None and value_col not in df.columns:
        raise DataFreshnessError(
            f"{path.name} 缺少必需列 '{value_col}' (实际列: {list(df.columns)})"
        )
    return df.sort_values("date")


def check_ohlcv_freshness(
    ohlcv_path: Path | None = None, sla_days: int | None = None
) -> FreshnessReport:
    """OHLCV 相对 '今天(UTC)' 的新鲜度. 超 SLA → FATAL."""
    ohlcv_path = ohlcv_path or OHLCV_PATH
    if sla_days is None:
        sla_days = load_freshness_sla()["ohlcv_max_stale_days"]

    df = _read_dated_csv(ohlcv_path)
    last = df["date"].max()
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    stale = (today - last.normalize()).days
    ok = stale <= sla_days
    report = FreshnessReport(
        source="ohlcv",
        path=_rel(ohlcv_path),
        rows=len(df),
        start=str(df["date"].min().date()),
        end=str(last.date()),
        stale_days=stale,
        sla_days=sla_days,
        ok=ok,
        detail=f"OHLCV last_date={last.date()} 落后今天(UTC) {stale} 天",
    )
    if not ok:
        raise DataFreshnessError(
            f"OHLCV 过期: last_date={last.date()}, 落后 {stale} 天 > SLA {sla_days} 天。"
            f" 请先重跑下载 stage (决策 A: 不出 stale 信号)。"
        )
    return report


def check_fgi_freshness(
    fgi_path: Path | None = None,
    ohlcv_path: Path | None = None,
    sla_days: int | None = None,
) -> FreshnessReport:
    """FGI 相对 OHLCV last_date 的新鲜度. 文件缺失/列缺失/超 SLA → FATAL.

    用 OHLCV last_date 而非 '今天' 作基准: 推理特征是对齐到 OHLCV 交易日的,
    真正要保证的是 'FGI 覆盖到了最新交易日附近', 而非绝对日历日。
    """
    fgi_path = fgi_path or FGI_PATH
    ohlcv_path = ohlcv_path or OHLCV_PATH
    if sla_days is None:
        sla_days = load_freshness_sla()["fgi_max_stale_days"]

    fgi = _read_dated_csv(fgi_path, value_col="fgi_value")
    ohlcv = _read_dated_csv(ohlcv_path)

    fgi_last = fgi["date"].max()
    ohlcv_last = ohlcv["date"].max()
    stale = (ohlcv_last.normalize() - fgi_last.normalize()).days
    ok = stale <= sla_days
    report = FreshnessReport(
        source="fgi",
        path=_rel(fgi_path),
        rows=len(fgi),
        start=str(fgi["date"].min().date()),
        end=str(fgi_last.date()),
        stale_days=stale,
        sla_days=sla_days,
        ok=ok,
        detail=(
            f"FGI last_date={fgi_last.date()} 落后 OHLCV last_date="
            f"{ohlcv_last.date()} {stale} 天"
        ),
    )
    if not ok:
        raise DataFreshnessError(
            f"FGI 过期: last_date={fgi_last.date()} 落后 OHLCV "
            f"({ohlcv_last.date()}) {stale} 天 > SLA {sla_days} 天。"
            f" 请先重跑 FGI 下载 stage (决策 A: 不 ffill stale 情绪特征)。"
        )
    return report


def check_all(
    *,
    require_fgi: bool = True,
    sla: dict[str, int] | None = None,
) -> list[FreshnessReport]:
    """跑全部新鲜度校验. 任一失败抛 DataFreshnessError.

    Parameters
    ----------
    require_fgi : 模型是否依赖 FGI (由 pipeline 根据 config.features.sets 判定)。
                  不依赖时跳过 FGI 校验, 避免误伤纯价量模型。
    sla : 覆盖 SLA (主要给测试用); None 则从 active.yaml 读。
    """
    sla = sla or load_freshness_sla()
    reports = [check_ohlcv_freshness(sla_days=sla["ohlcv_max_stale_days"])]
    if require_fgi:
        reports.append(check_fgi_freshness(sla_days=sla["fgi_max_stale_days"]))
    return reports
