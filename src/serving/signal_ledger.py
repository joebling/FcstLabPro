"""信号账本 + 监控产物 — Phase 4 运行审计.

对应 docs/reviews/cr_0529 §2 (shadow/live/archive) 和 §9 (监控产物)。
不依赖数据库, 用文件系统实现 RiskDetect 式的版本账本:

  data/signals/live/{model}.json           # 每个模型最新一条 (单版本)
  data/signals/archive/{model}/{date}.json # 历史全量 (多版本可审计)
  data/live/monitoring/{model}/{date}.json # 每日监控指标

每条记录强制带 model lineage (name/hash/variant/input_data_end) 以便回溯。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SIGNALS_DIR = PROJECT_ROOT / "data" / "signals"
MONITORING_DIR = PROJECT_ROOT / "data" / "live" / "monitoring"

# 合法写入模式
MODES = ("live", "shadow", "dry-run")


def _provenance(
    model_name: str,
    model_hash: str,
    variant: str,
    input_data_end: str,
    feature_cols_sha256: str | None,
) -> dict:
    """模型谱系戳 — 每条信号必带, 用于回溯切版影响."""
    return {
        "model_name": model_name,
        "model_hash": model_hash,
        "strategy_variant": variant,
        "input_data_end": input_data_end,
        "feature_cols_sha256": feature_cols_sha256,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _now_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def record_signal(
    signal_payload: dict,
    *,
    model_name: str,
    model_hash: str,
    variant: str,
    input_data_end: str,
    mode: str = "live",
    feature_cols_sha256: str | None = None,
) -> dict[str, Path]:
    """把信号写入账本.

    Parameters
    ----------
    signal_payload : 原始信号 dict (build_signal_json 的产物)
    mode : "live"    → 写 live + archive
           "shadow"  → 只写 archive (标 score_source=shadow, 不动 live)
           "dry-run" → 不落盘, 仅日志

    Returns
    -------
    dict[str, Path] : 实际写入的文件路径 (键: live / archive)
    """
    if mode not in MODES:
        raise ValueError(f"未知 mode: {mode}, 合法: {MODES}")

    prov = _provenance(
        model_name, model_hash, variant, input_data_end, feature_cols_sha256
    )
    record = {**signal_payload, "score_source": mode, "provenance": prov}
    date_str = signal_payload.get("date") or _now_date()

    written: dict[str, Path] = {}
    if mode == "dry-run":
        logger.info("dry-run: 信号未落盘 (model=%s)", model_name)
        return written

    # archive 总是写 (live 和 shadow 都进归档, 可审计)
    archive_path = SIGNALS_DIR / "archive" / model_name / f"{date_str}.json"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    written["archive"] = archive_path

    # 只有 live 模式更新 live 单版本指针
    if mode == "live":
        live_path = SIGNALS_DIR / "live" / f"{model_name}.json"
        live_path.parent.mkdir(parents=True, exist_ok=True)
        live_path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
        written["live"] = live_path

    logger.info("信号已记录 (model=%s mode=%s): %s", model_name, mode,
                ", ".join(str(p.relative_to(PROJECT_ROOT)) for p in written.values()))
    return written


def write_monitoring(
    *,
    model_name: str,
    n_rows: int,
    data_last_date: str,
    signal: str,
    probability: float | None = None,
    feature_missing_rate: dict | None = None,
    extra: dict | None = None,
) -> Path:
    """生成每日监控产物 (供漂移/暴露/缺失率追踪)."""
    date_str = _now_date()
    payload = {
        "model_name": model_name,
        "date": date_str,
        "n_rows": n_rows,
        "data_last_date": data_last_date,
        "signal": signal,
        "probability": probability,
        "feature_missing_rate": feature_missing_rate or {},
        **(extra or {}),
    }
    out = MONITORING_DIR / model_name / f"{date_str}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    logger.info("监控产物已写: %s", out.relative_to(PROJECT_ROOT))
    return out
