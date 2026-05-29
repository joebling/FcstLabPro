"""生产模型契约构建 — data_manifest / execution_policy / manifest 增强.

对应 docs/reviews/cr_0529 §5/§8/§10。把「报告里口头说的假设」变成
「机器可读、可审计、可作为晋升门禁的产物」。

产物:
  - data_manifest.json   : 训练数据 + 外部源的 hash / 区间 / freshness
  - execution_policy.yaml: 成本 / 滑点 / 执行延迟 / kill-switch (交易层合同)
  - manifest.json 增强字段: role / lifecycle / validation_gates / fallback
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# 复用 active_config 的单一 variant 定义 (消除 DRY)
from src.serving.active_config import VARIANT_FLAGS

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 模型角色 → 默认元信息 (lifecycle 由调用方按 status 决定)
ROLE_DEFAULTS = {
    "risk_control": "风控优先 (MaxDD 更低)",
    "return_enhancement": "收益优先 (Return/Sharpe 更高, 回撤更大)",
    "sota_candidate": "离线 SOTA 候选, 待 PnL 验证",
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def build_data_manifest(data_path: Path) -> dict:
    """从训练数据 CSV 生成数据谱系 (hash / 区间 / 行数 / freshness)."""
    df = pd.read_csv(data_path, parse_dates=[0], index_col=0)
    start = df.index.min()
    end = df.index.max()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "raw_ohlcv": {
            "path": str(data_path.relative_to(PROJECT_ROOT))
            if data_path.is_relative_to(PROJECT_ROOT) else str(data_path),
            "sha256": _sha256_file(data_path),
            "rows": int(len(df)),
            "start": str(start.date()),
            "end": str(end.date()),
        },
        # 外部源 (FGI / funding / macro) — 当前由 feature pipeline 内部处理,
        # 暂以占位记录, 待 Phase 3 serving 重构时接入真实 lineage。
        "external_sources": {
            "fear_greed_index": {"status": "embedded_in_pipeline", "verified": False},
        },
        "freshness_sla_days": 1,
    }


def build_execution_policy(variant: str) -> dict:
    """生成执行层合同模板 (成本 / 滑点 / 延迟 / kill-switch).

    ⚠️ 数值为机构默认假设, 标 verified=false; 上线前必须人工确认实际成本结构。
    """
    if variant not in VARIANT_FLAGS:
        raise ValueError(f"未知 variant: {variant}, 合法: {list(VARIANT_FLAGS)}")
    return {
        "_note": "执行层合同 — 数值为默认假设, 上线前人工确认后将 verified 改 true",
        "verified": False,
        "execution": {
            "signal_time": "daily_close",       # T 日收盘出信号
            "execution_time": "next_open",      # T+1 开盘成交 (避免回测虚高)
            "instrument": "spot",
            "fee_bps": 10,                       # 单边手续费 (basis points)
            "slippage_bps": 5,                   # 单边滑点
            "funding_included": False,           # 现货无资金费率
            "max_position": 1.0,
            "vol_target": None,                  # 未启用波动率目标
            "variant": variant,
            "cli_flags": VARIANT_FLAGS[variant],
        },
        "kill_switch": {
            "max_live_drawdown": 0.15,           # 实盘回撤超 15% 停机
            "max_consecutive_losses": 5,
        },
    }


def build_validation_gates(metrics: dict, has_pnl: bool, decontaminated: bool) -> dict:
    """机器可读的晋升门禁状态 (供 manifest + 审计)."""
    kappa = metrics.get("cohen_kappa", 0)
    return {
        "experiment_completed": True,
        "non_overlapping_confirmed": True,   # 由 config 校验保证 (Phase 1b)
        "walk_forward_confirmed": True,       # 同上
        "kappa_above_threshold": kappa >= 0.10,
        "no_data_leakage_suspicion": kappa < 0.50,
        "pnl_backtested": has_pnl,
        "decontaminated": decontaminated,
        "execution_policy_present": True,     # 由 promote 生成保证
        "data_manifest_present": True,
        "reproducibility_verified": False,    # 需人工跑 verify_reproducibility.py 后置 true
        "python_version": "3.10",
    }


def build_lifecycle(status: str, role: str) -> dict:
    """模型角色与生命周期 (机器可读, 替代散落文档的口头描述)."""
    return {
        "role": role,
        "role_desc": ROLE_DEFAULTS.get(role, role),
        "status": status,        # live / paper / offline_only / deprecated
        "active_from": datetime.now(timezone.utc).date().isoformat(),
        "active_until": None,
    }
