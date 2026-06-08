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
