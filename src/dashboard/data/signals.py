"""信号数据读取 — archive / 最新信号 / 双模型对比.

只读 data/signals/archive/ + data/live/paper_trading/。
performance 相关 (命中率/IC/批次表) 走 src/performance, 不在此重复。
"""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ARCHIVE_DIR = PROJECT_ROOT / "data" / "signals" / "archive"
PAPER_DIR = PROJECT_ROOT / "data" / "live" / "paper_trading"


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def latest_signal(model_name: str) -> dict | None:
    """该模型最新一条 archive 信号 (按文件名日期排序)."""
    base = ARCHIVE_DIR / model_name
    if not base.exists():
        return None
    files = sorted(base.glob("*.json"))
    return _read_json(files[-1]) if files else None


def signal_history(model_name: str, limit: int = 60) -> list[dict]:
    """最近 N 条信号 (倒序, 新的在前)."""
    base = ARCHIVE_DIR / model_name
    if not base.exists():
        return []
    files = sorted(base.glob("*.json"), reverse=True)[:limit]
    out = [s for f in files if (s := _read_json(f)) is not None]
    return out


def signal_distribution(model_name: str) -> dict[str, int]:
    """信号类型分布 (BUY / SILENT 计数) — 喂环形图."""
    dist: dict[str, int] = {}
    for s in signal_history(model_name, limit=10_000):
        sig = s.get("signal", "UNKNOWN")
        dist[sig] = dist.get(sig, 0) + 1
    return dist


def signal_calendar(model_name: str, year: int, month: int) -> dict[str, dict]:
    """某年月每天的信号 — 喂信号日历热力图.

    Returns {date_str: {signal, price, regime}}。
    """
    base = ARCHIVE_DIR / model_name
    if not base.exists():
        return {}
    prefix = f"{year:04d}-{month:02d}-"
    out = {}
    for f in base.glob(f"{prefix}*.json"):
        s = _read_json(f)
        if s:
            out[s["date"]] = {
                "signal": s.get("signal"),
                "price": s.get("price"),
                "regime": s.get("regime"),
            }
    return out


def latest_paper_comparison() -> dict | None:
    """最新一条 paper_trading 双模型对比 (含 consensus)."""
    if not PAPER_DIR.exists():
        return None
    files = sorted(PAPER_DIR.glob("signal_*.json"))
    return _read_json(files[-1]) if files else None
