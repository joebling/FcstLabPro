"""实盘业绩监控页 — 净值/回撤/样本gating/Live vs Backtest 对照.

定位: 监控漂移与衰减, 非 alpha 验证 (后者是研究态 IC/walk-forward 的活)。
"""
from __future__ import annotations

from src.dashboard.data import perfmon


def _variant(model_name: str) -> str:
    """从 active.yaml 解析策略变体 (用于选回测基准口径)."""
    try:
        from src.serving.active_config import resolve_model
        return resolve_model(model_name).strategy_variant or "conservative"
    except Exception:
        return "conservative"


def build(model_name: str | None) -> dict:
    if not model_name:
        return {"has_data": False}
    ctx = perfmon.build(model_name, _variant(model_name))
    ctx["has_data"] = True
    return ctx
