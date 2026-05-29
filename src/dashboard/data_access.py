"""Dashboard 数据读取层 — 调 performance 服务 (实时算+缓存), 不读中间文件.

对齐 RiskDetect: 真相源是 data/signals/archive/, 请求时实时回填聚合。
本层只负责: 调服务 + 容错兜底 + 把 computed_at 转成"新鲜度"给页面。
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.performance import service
from src.performance.cache import DEFAULT_TTL_SECONDS


def list_models() -> list[str]:
    """从 active.yaml 取模型列表 (单一真相源, 不硬编码)."""
    try:
        from src.serving.active_config import load_active_models
        return [m.name for m in load_active_models().values()]
    except Exception:
        return []


def _age_hours(epoch: float) -> float:
    return (datetime.now(timezone.utc).timestamp() - epoch) / 3600


def load_batches(model_name: str) -> dict:
    """批次表 + 缓存新鲜度. 服务异常时兜底不白屏."""
    try:
        rows, computed_at = service.get_batches(model_name)
    except Exception as e:  # noqa: BLE001 — dashboard 永不因数据问题崩
        return {"rows": [], "stale": True, "reason": "error", "error": str(e)}
    return {
        "rows": rows,
        "reason": "ok" if rows else "no_data",
        "stale": not rows,
        # computed_at 是"这份缓存何时算的", TTL 内不变; 给页面显示新鲜度
        "computed_age_minutes": round(_age_hours(computed_at) * 60, 1),
        "cache_ttl_minutes": DEFAULT_TTL_SECONDS // 60,
    }


def load_summary(model_name: str) -> dict:
    """汇总 KPI. 服务异常时返回空 dict."""
    try:
        summary, _ = service.get_summary(model_name)
        return summary
    except Exception:  # noqa: BLE001
        return {}
