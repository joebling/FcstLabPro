"""生产持仓账本读取 — 与每日信号邮件同源.

读 ${FCST_DATA_DIR}/state/{model}_state.json (live_signal.py 的 PositionState
持久化的真实账本): 当前持仓 / regime / 真实交易历史 (开仓→平仓的实际 PnL)。

这是 dashboard 与邮件保持一致的「真实交易战绩」来源, 区别于 src/performance
的理论 T=21 信号质量回填 (那个假设每条信号死扛 21 天, 不懂 SELL/强平)。

战绩汇总直接复用 build_signal_json._parse_history, 保证与邮件数字逐位一致 (DRY)。
"""
from __future__ import annotations

import json
from pathlib import Path

from src.dashboard.config import STATE_DIR


def _state_path(model_name: str) -> Path:
    return STATE_DIR / f"{model_name}_state.json"


def load_state(model_name: str) -> dict:
    """读模型持仓 state (缺失/坏文件返回 {})."""
    p = _state_path(model_name)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def position(model_name: str) -> dict:
    """当前持仓 + regime 快照 (与邮件顶部一致)."""
    s = load_state(model_name)
    return {
        "has_state": bool(s),
        "in_position": s.get("in_position", False),
        "entry_date": s.get("entry_date"),
        "entry_price": s.get("entry_price"),
        "days_held": s.get("days_held", 0),
        "last_signal": s.get("last_signal"),
        "last_signal_date": s.get("last_signal_date"),
        "last_reason": s.get("last_reason", ""),
        "regime": s.get("last_regime", ""),
        "regime_detail": s.get("last_regime_detail", ""),
    }


def trade_history(model_name: str) -> dict:
    """真实交易战绩 — 与邮件 _build_history_card 同源.

    返回 {total_trades, wins, win_rate, avg_pnl, total_pnl, recent[], exit_stats}。
    """
    s = load_state(model_name)
    raw = s.get("history", [])
    from scripts.build_signal_json import _parse_history
    return _parse_history(raw)


def trade_history_by_cycle_regime(model_name: str) -> list[dict]:
    """按开仓日 RR regime 切片真实交易战绩.

    只读 state history; entry_date -> 当日 Reserve Risk rolling-2y 分位。
    这是 dashboard 弱耦合的研究视图, 不回写信号、不改变模型。
    """
    raw = load_state(model_name).get("history", [])
    return summarize_by_cycle_regime(raw)


def summarize_by_cycle_regime(raw_history: list[dict]) -> list[dict]:
    """Pure-ish helper for tests: group completed trades by entry-date cycle regime."""
    from src.dashboard.data import cycle_regime

    order = ["top", "neutral", "bottom", "unknown"]
    rows = {
        key: {
            "key": key,
            "label": cycle_regime.classify_pct(None)["label"],
            "count": 0,
            "wins": 0,
            "win_rate": 0.0,
            "avg_pnl": 0.0,
            "total_pnl": 0.0,
            "avg_rr_pct": None,
        }
        for key in order
    }
    # Keep display metadata DRY with cycle_regime.classify_pct.
    for key, probe in (("top", 100), ("neutral", 50), ("bottom", 0), ("unknown", None)):
        meta = cycle_regime.classify_pct(probe)
        rows[key].update({k: meta[k] for k in ("label", "bg", "text", "border")})

    pct_series = cycle_regime.rr_pct_series()
    rr_values = {key: [] for key in order}
    pnl_values = {key: [] for key in order}

    for t in raw_history:
        if t.get("pnl") is None or not t.get("entry_date"):
            continue
        meta = cycle_regime.context_for_date(t.get("entry_date"), pct_series)
        key = meta["key"]
        pnl = float(t.get("pnl", 0.0))
        rows[key]["count"] += 1
        rows[key]["wins"] += 1 if pnl > 0 else 0
        pnl_values[key].append(pnl)
        if meta.get("pct") is not None:
            rr_values[key].append(float(meta["pct"]))

    for key in order:
        n = rows[key]["count"]
        pnls = pnl_values[key]
        rows[key]["win_rate"] = rows[key]["wins"] / n if n else 0.0
        rows[key]["avg_pnl"] = sum(pnls) / n if n else 0.0
        rows[key]["total_pnl"] = sum(pnls)
        rows[key]["avg_rr_pct"] = (
            round(sum(rr_values[key]) / len(rr_values[key]), 1) if rr_values[key] else None
        )
    return [rows[k] for k in order]
