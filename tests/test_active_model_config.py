"""测试 src/serving/active_config.py —— 生产模型唯一真相源加载器.

覆盖场景:
  1. 加载真实 active.yaml → primary/challenger 解析正确
  2. resolve_model 默认返回 primary
  3. resolve_model 支持按槽位名 / 模型名查找
  4. variant 绑定门: active.yaml 与 manifest 冲突 → ValueError
  5. 产物缺失 (model.joblib) → FileNotFoundError
  6. 未知 variant → ValueError
  7. cli_flags 映射正确
  8. 空 active.yaml → ValueError
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.serving.active_config import (
    VARIANT_FLAGS,
    load_active_models,
    resolve_model,
)


# --------------------------------------------------------------------- helpers


def _write_active(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "active.yaml"
    p.write_text(body)
    return p


def _make_model_dir(tmp_path: Path, name: str, variant: str | None) -> Path:
    """造一个最小可校验的模型目录 (model.joblib + config.yaml + 可选 manifest)."""
    d = tmp_path / "models" / "production" / name
    d.mkdir(parents=True)
    (d / "model.joblib").write_bytes(b"")
    (d / "config.yaml").write_text("dummy: true\n")
    if variant is not None:
        (d / "manifest.json").write_text(
            json.dumps({"deployment": {"variant": variant}})
        )
    return d


# ----------------------------------------------------- real active.yaml tests


def test_loads_real_active_yaml() -> None:
    """真实 active.yaml 应能解析出 primary 且校验通过."""
    models = load_active_models()
    assert "primary" in models
    assert models["primary"].name == "e1-conservative"
    assert models["primary"].status == "live"


def test_resolve_default_returns_primary() -> None:
    assert resolve_model().slot == "primary"


def test_resolve_by_name_and_slot() -> None:
    assert resolve_model("challenger").name == "e8-touch"
    assert resolve_model("e8-touch").slot == "challenger"


def test_resolve_unknown_raises() -> None:
    with pytest.raises(KeyError, match="找不到模型"):
        resolve_model("does-not-exist")


# ----------------------------------------------------- variant binding gate


def test_variant_binding_gate_blocks_conflict(tmp_path: Path) -> None:
    """active.yaml 写 base 但 manifest 是 conservative → 必须 fail."""
    _make_model_dir(tmp_path, "m1", variant="conservative")
    cfg = _write_active(tmp_path, f"""primary:
  artifact_dir: {tmp_path}/models/production/m1
  role: risk_control
  strategy_variant: base
  status: live
""")
    # 注意: artifact_dir 用绝对路径, PROJECT_ROOT / abs = abs, 所以能找到
    with pytest.raises(ValueError, match="strategy_variant 冲突"):
        load_active_models(path=cfg)


def test_variant_binding_passes_when_aligned(tmp_path: Path) -> None:
    _make_model_dir(tmp_path, "m2", variant="conservative")
    cfg = _write_active(tmp_path, f"""primary:
  artifact_dir: {tmp_path}/models/production/m2
  role: risk_control
  strategy_variant: conservative
  status: live
""")
    models = load_active_models(path=cfg)
    assert models["primary"].strategy_variant == "conservative"


def test_missing_manifest_skips_binding_check(tmp_path: Path) -> None:
    """没有 manifest.json 的老模型 → 跳过 variant 绑定 (向后兼容)."""
    _make_model_dir(tmp_path, "m3", variant=None)
    cfg = _write_active(tmp_path, f"""primary:
  artifact_dir: {tmp_path}/models/production/m3
  role: risk_control
  strategy_variant: moderate
  status: live
""")
    models = load_active_models(path=cfg)
    assert models["primary"].strategy_variant == "moderate"


# ----------------------------------------------------- integrity / validation


def test_missing_model_artifact_raises(tmp_path: Path) -> None:
    d = tmp_path / "models" / "production" / "m4"
    d.mkdir(parents=True)
    # 故意不建 model.joblib
    (d / "config.yaml").write_text("dummy: true\n")
    cfg = _write_active(tmp_path, f"""primary:
  artifact_dir: {tmp_path}/models/production/m4
  role: risk_control
  strategy_variant: base
  status: live
""")
    with pytest.raises(FileNotFoundError, match="model.joblib"):
        load_active_models(path=cfg)


def test_unknown_variant_raises(tmp_path: Path) -> None:
    _make_model_dir(tmp_path, "m5", variant=None)
    cfg = _write_active(tmp_path, f"""primary:
  artifact_dir: {tmp_path}/models/production/m5
  role: risk_control
  strategy_variant: yolo_mode
  status: live
""")
    with pytest.raises(ValueError, match="未知 strategy_variant"):
        load_active_models(path=cfg)


def test_empty_active_yaml_raises(tmp_path: Path) -> None:
    cfg = _write_active(tmp_path, "# 啥也没有\n")
    with pytest.raises(ValueError, match="没有任何模型槽位"):
        load_active_models(path=cfg)


def test_validate_false_skips_checks(tmp_path: Path) -> None:
    """validate=False 时跳过所有校验 (用于纯读取场景)."""
    cfg = _write_active(tmp_path, f"""primary:
  artifact_dir: {tmp_path}/models/production/ghost
  role: risk_control
  strategy_variant: yolo_mode
  status: live
""")
    models = load_active_models(path=cfg, validate=False)
    assert models["primary"].strategy_variant == "yolo_mode"


# ----------------------------------------------------- cli flags


def test_cli_flags_mapping() -> None:
    assert VARIANT_FLAGS["base"] == []
    assert VARIANT_FLAGS["moderate"] == ["--take-profit"]
    assert VARIANT_FLAGS["conservative"] == ["--take-profit", "--regime-switch"]
