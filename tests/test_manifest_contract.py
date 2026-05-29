"""测试 src/serving/contracts.py + 真实生产 manifest 契约完整性.

覆盖:
  1. build_data_manifest: hash / 区间 / 行数
  2. build_execution_policy: 合法 variant / 非法 variant 拒绝 / 关键字段
  3. build_validation_gates: kappa 门槛逻辑
  4. build_lifecycle: 角色描述
  5. 真实 E1/E8 manifest 必须含 lifecycle/validation_gates/fallback (回归)
  6. 真实 E1/E8 必须有 execution_policy.yaml + data_manifest.json
  7. deployment.variant 与 active.yaml 一致 (训推绑定回归)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from src.serving.contracts import (
    build_data_manifest,
    build_execution_policy,
    build_lifecycle,
    build_validation_gates,
)

ROOT = Path(__file__).resolve().parent.parent
PROD = ROOT / "models" / "production"
BASELINE_CSV = ROOT / "baseline_snapshot" / "btc_baseline_693b7b1.csv"


# ----------------------------------------------------- contract builders


def test_build_data_manifest() -> None:
    dm = build_data_manifest(BASELINE_CSV)
    raw = dm["raw_ohlcv"]
    assert raw["rows"] == 2240
    assert raw["start"] == "2020-01-01"
    assert raw["end"] == "2026-02-17"
    assert len(raw["sha256"]) == 64
    assert dm["freshness_sla_days"] == 1


def test_build_execution_policy_fields() -> None:
    ep = build_execution_policy("conservative")
    ex = ep["execution"]
    assert ex["signal_time"] == "daily_close"
    assert ex["execution_time"] == "next_open"  # 防回测虚高
    assert ex["fee_bps"] > 0
    assert ex["slippage_bps"] > 0
    assert ep["verified"] is False  # 默认未验证
    assert "max_live_drawdown" in ep["kill_switch"]


def test_build_execution_policy_rejects_unknown_variant() -> None:
    with pytest.raises(ValueError, match="未知 variant"):
        build_execution_policy("yolo")


def test_build_validation_gates_kappa_logic() -> None:
    # 高 kappa → 疑似泄露 → no_data_leakage_suspicion=False
    g = build_validation_gates({"cohen_kappa": 0.6}, True, True)
    assert g["kappa_above_threshold"] is True
    assert g["no_data_leakage_suspicion"] is False

    # 低 kappa → 不达标
    g2 = build_validation_gates({"cohen_kappa": 0.05}, False, False)
    assert g2["kappa_above_threshold"] is False
    assert g2["pnl_backtested"] is False


def test_build_lifecycle() -> None:
    lc = build_lifecycle("live", "risk_control")
    assert lc["status"] == "live"
    assert lc["role"] == "risk_control"
    assert "风控" in lc["role_desc"]
    assert lc["active_until"] is None


# ----------------------------------------------------- real manifest regression


@pytest.mark.parametrize("name", ["e1-conservative", "e8-touch"])
def test_real_manifest_has_phase2_fields(name: str) -> None:
    mf = json.loads((PROD / name / "manifest.json").read_text())
    assert "lifecycle" in mf, f"{name} manifest 缺 lifecycle"
    assert "validation_gates" in mf, f"{name} manifest 缺 validation_gates"
    assert "fallback" in mf, f"{name} manifest 缺 fallback"
    assert mf["lifecycle"]["role"]
    assert mf["fallback"]["trigger"]


@pytest.mark.parametrize("name", ["e1-conservative", "e8-touch"])
def test_real_model_has_contract_artifacts(name: str) -> None:
    d = PROD / name
    assert (d / "execution_policy.yaml").exists(), f"{name} 缺 execution_policy.yaml"
    assert (d / "data_manifest.json").exists(), f"{name} 缺 data_manifest.json"

    ep = yaml.safe_load((d / "execution_policy.yaml").read_text())
    assert ep["execution"]["execution_time"] == "next_open"

    dm = json.loads((d / "data_manifest.json").read_text())
    assert dm["raw_ohlcv"]["rows"] > 0


@pytest.mark.parametrize("name", ["e1-conservative", "e8-touch"])
def test_deployment_variant_matches_active(name: str) -> None:
    """manifest deployment.variant 必须与 active.yaml 声明一致 (训推绑定回归)."""
    from src.serving import resolve_model

    mf = json.loads((PROD / name / "manifest.json").read_text())
    manifest_variant = mf["deployment"]["variant"]
    active = resolve_model(name)
    assert active.strategy_variant == manifest_variant
