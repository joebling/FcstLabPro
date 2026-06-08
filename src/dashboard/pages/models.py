"""模型页 — 模型治理可视化 (active.yaml/manifest/回测指标摆出来)."""
from __future__ import annotations

from src.dashboard.data import models


def build() -> dict:
    return {
        "models_detail": models.active_models(),
        "freshness": models.freshness_gate(),
    }
