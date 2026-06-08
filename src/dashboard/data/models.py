"""模型治理数据读取 — active.yaml + manifest + 回测指标.

复用 src/serving/active_config 读 active.yaml (DRY)。
把模型谱系/角色/状态/回测指标摆出来给「模型页」。
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_DIR = PROJECT_ROOT / "models" / "production"
ACTIVE_YAML = PRODUCTION_DIR / "active.yaml"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def active_models() -> list[dict]:
    """active.yaml 里的模型槽位 + manifest 详情, 合成展示用 dict 列表."""
    from src.serving.active_config import load_active_models

    out = []
    try:
        slots = load_active_models(validate=False)
    except Exception:
        return out

    for slot, m in slots.items():
        manifest = _read_json(m.manifest_path)
        metrics = _read_json(m.artifact_dir / "metrics.json")
        pnl = _read_json(m.artifact_dir / "pnl_metrics.json")
        out.append({
            "slot": slot,
            "name": m.name,
            "role": m.role,
            "strategy_variant": m.strategy_variant,
            "status": m.status,
            "note": m.note,
            "model_hash": manifest.get("model", {}).get("sha256_prefix", ""),
            "label": manifest.get("strategy", {}).get("label", ""),
            "T": manifest.get("strategy", {}).get("T"),
            "source_experiment": manifest.get("source_experiment", {}),
            "promoted_at": manifest.get("promoted_at", ""),
            "metrics": metrics,
            "pnl_metrics": pnl,
        })
    return out


def freshness_gate() -> dict:
    """active.yaml 里的数据新鲜度门配置 (给模型页展示 SLA)."""
    try:
        raw = yaml.safe_load(ACTIVE_YAML.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return raw.get("data_freshness", {})
