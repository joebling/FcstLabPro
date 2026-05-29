"""Dashboard 唯一数据读取层 — 只读 performance JSON, 不计算.

所有读文件逻辑收口此处 (DRY + 可测试)。routes 不直接碰文件系统。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.dashboard.config import PERF_DIR, STALE_THRESHOLD_HOURS


def list_models() -> list[str]:
    """从 active.yaml 取模型列表 (单一真相源, 不硬编码).

    active.yaml 读取失败时回退到 PERF_DIR 下已有的子目录, 保证 dashboard
    即使脱离主项目配置也能展示已生成的数据。
    """
    try:
        from src.serving.active_config import load_active_models
        return [m.name for m in load_active_models().values()]
    except Exception:
        if PERF_DIR.exists():
            return sorted(p.name for p in PERF_DIR.iterdir() if p.is_dir())
        return []


def _stale_meta(path: Path) -> dict:
    age_h = (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / 3600
    return {
        "stale": age_h > STALE_THRESHOLD_HOURS,
        "generated_age_hours": round(age_h, 1),
    }


def load_batches(model_name: str) -> dict:
    """读 batches.json. 带 stale 检测 + 损坏兜底 (不白屏)."""
    path = PERF_DIR / model_name / "batches.json"
    if not path.exists():
        return {"rows": [], "stale": True, "reason": "no_data"}
    try:
        rows = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"rows": [], "stale": True, "reason": "corrupt"}
    return {"rows": rows, "reason": "ok", **_stale_meta(path)}


def load_summary(model_name: str) -> dict:
    """读 summary.json (KPI + 趋势)."""
    path = PERF_DIR / model_name / "summary.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
