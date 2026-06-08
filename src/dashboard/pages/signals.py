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

    # 注: 不算 get_summary —— 信号页模板不用 summary (仅 overview 页用),
    # 以前白白多跑一次 load_live_ohlcv + 聚合 (~35ms 冷算), YAGNI 删除。

    return {
        "has_data": True,
        "latest": latest,
        "paper": paper,
        "batches": batches,
    }
