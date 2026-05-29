"""测试 src/experiment/validation.py —— 实验配置硬校验门.

覆盖机构手册 §2 的核心规则:
  1. Non-overlapping (step == T)
  2. Purge gap (purge_gap >= T)
  3. Walk-forward only
  4. Seed 必填
  5. label.strategy 已注册
  6. model.type / data.path / features.sets
"""
from __future__ import annotations

import pytest

from src.experiment.validation import (
    ConfigValidationError,
    validate_experiment_config,
)


def _valid_config() -> dict:
    """一份合规的最小配置 (对标 E1)."""
    return {
        "seed": 42,
        "data": {"path": "data/raw/btc_binance_BTCUSDT_1d.csv"},
        "features": {"sets": ["technical", "external_fgi"]},
        "label": {"strategy": "directional_filtered", "T": 21},
        "model": {"type": "lightgbm"},
        "evaluation": {"method": "walk_forward", "step": 21, "purge_gap": 21},
    }


def test_valid_config_passes() -> None:
    validate_experiment_config(_valid_config())


def test_step_must_equal_T() -> None:
    cfg = _valid_config()
    cfg["evaluation"]["step"] = 1  # 重叠采样!
    with pytest.raises(ConfigValidationError, match="Non-overlapping"):
        validate_experiment_config(cfg)


def test_purge_gap_must_cover_T() -> None:
    cfg = _valid_config()
    cfg["evaluation"]["purge_gap"] = 5  # < T=21
    with pytest.raises(ConfigValidationError, match="Purge gap"):
        validate_experiment_config(cfg)


def test_method_must_be_walk_forward() -> None:
    cfg = _valid_config()
    cfg["evaluation"]["method"] = "train_test_split"
    with pytest.raises(ConfigValidationError, match="walk_forward"):
        validate_experiment_config(cfg)


def test_seed_required() -> None:
    cfg = _valid_config()
    del cfg["seed"]
    with pytest.raises(ConfigValidationError, match="seed"):
        validate_experiment_config(cfg)


def test_unregistered_label_strategy_rejected() -> None:
    cfg = _valid_config()
    cfg["label"]["strategy"] = "magic_crystal_ball"
    with pytest.raises(ConfigValidationError, match="未注册"):
        validate_experiment_config(cfg)


def test_missing_data_path_rejected() -> None:
    cfg = _valid_config()
    del cfg["data"]["path"]
    with pytest.raises(ConfigValidationError, match="data.path"):
        validate_experiment_config(cfg)


def test_nonexistent_data_path_rejected() -> None:
    cfg = _valid_config()
    cfg["data"]["path"] = "data/raw/does_not_exist.csv"
    with pytest.raises(ConfigValidationError, match="不存在"):
        validate_experiment_config(cfg)


def test_strict_data_false_skips_path_check() -> None:
    cfg = _valid_config()
    cfg["data"]["path"] = "data/raw/does_not_exist.csv"
    # strict_data=False 时不校验文件存在
    validate_experiment_config(cfg, strict_data=False)


def test_empty_feature_sets_rejected() -> None:
    cfg = _valid_config()
    cfg["features"]["sets"] = []
    with pytest.raises(ConfigValidationError, match="features.sets"):
        validate_experiment_config(cfg)


def test_missing_model_type_rejected() -> None:
    cfg = _valid_config()
    del cfg["model"]["type"]
    with pytest.raises(ConfigValidationError, match="model.type"):
        validate_experiment_config(cfg)


def test_errors_aggregate() -> None:
    """多个问题应一次性汇总报告 (不是 fail-fast 单条)."""
    cfg = {"label": {}, "evaluation": {}, "data": {}, "features": {}, "model": {}}
    with pytest.raises(ConfigValidationError) as exc:
        validate_experiment_config(cfg)
    # 至少报告多条
    assert str(exc.value).count("- ") >= 4


def test_real_e1_config_passes() -> None:
    """真实 E1 生产配置必须通过校验 (回归保护)."""
    import yaml
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    cfg = yaml.safe_load(
        (root / "models/production/e1-conservative/config.yaml").read_text()
    )
    validate_experiment_config(cfg)


def test_real_e8_config_passes() -> None:
    import yaml
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    cfg = yaml.safe_load(
        (root / "models/production/e8-touch/config.yaml").read_text()
    )
    validate_experiment_config(cfg)
