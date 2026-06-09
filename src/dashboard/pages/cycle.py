"""周期研判页 — 整合顶部/底部, 单一 regime gate 路由。"""
from __future__ import annotations

from src.dashboard.data import cycle


def build() -> dict:
    return cycle.build()
