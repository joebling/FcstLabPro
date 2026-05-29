"""Performance 服务层 — dashboard 的入口, 实时算 + TTL 缓存.

对齐 RiskDetect: 请求时实时回填+聚合 (信号量小, 毫秒级), 用 TTL 缓存挡
重复请求。真相源单一 = data/signals/archive/, 无中间 JSON 产物。
"""
from __future__ import annotations

import yaml

from src.performance.aggregate import build_batches, build_summary
from src.performance.backfill import load_ohlcv
from src.performance.cache import cached_with_meta
from src.serving.active_config import resolve_model


def _label_T(model_name: str) -> int:
    """从 active.yaml 解析的模型 config.yaml 读 label.T (单一真相源)."""
    model = resolve_model(model_name)
    cfg = yaml.safe_load(model.config_path.read_text()) or {}
    return int(cfg["label"]["T"])


def get_batches(model_name: str) -> tuple[list[dict], float]:
    """批次表 (实时算 + 缓存). 返回 (rows, computed_at_epoch)."""
    def _compute():
        T = _label_T(model_name)
        return build_batches(model_name, label_T=T, ohlcv=load_ohlcv())
    return cached_with_meta(f"batches_{model_name}", _compute)


def get_summary(model_name: str) -> tuple[dict, float]:
    """汇总 KPI (实时算 + 缓存). 返回 (summary, computed_at_epoch)."""
    def _compute():
        T = _label_T(model_name)
        return build_summary(model_name, label_T=T, ohlcv=load_ohlcv())
    return cached_with_meta(f"summary_{model_name}", _compute)
