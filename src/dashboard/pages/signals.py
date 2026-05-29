"""信号页 — 信号完整生命周期.

当前信号大卡 + 信号实现明细表 (复用 performance) + 双模型对比。
"""
from __future__ import annotations

from src.dashboard.data import signals
from src.performance import service


def build(model_name: str | None) -> dict:
    if not model_name:
        return {"has_data": False}

    latest = signals.latest_signal(model_name) or {}
    paper = signals.latest_paper_comparison()

    try:
        batches, _ = service.get_batches(model_name)
    except Exception:
        batches = []
    try:
        summary, _ = service.get_summary(model_name)
    except Exception:
        summary = {}

    return {
        "has_data": True,
        "latest": latest,
        "paper": paper,
        "batches": batches,
        "summary": summary,
    }
