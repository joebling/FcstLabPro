"""Dashboard 基础数据 — 模型列表 (侧边栏共享).

页面级数据在 src/dashboard/data/ (signals/market/models),
performance 在 src/performance/。本模块只留侧边栏要的模型列表。
"""
from __future__ import annotations


def list_models() -> list[str]:
    """从 active.yaml 取模型列表 (单一真相源, 不硬编码)."""
    try:
        from src.serving.active_config import load_active_models
        return [m.name for m in load_active_models().values()]
    except Exception:
        return []
