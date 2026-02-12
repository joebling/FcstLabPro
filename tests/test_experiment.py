"""测试实验管理模块."""

import copy
import tempfile
from pathlib import Path

import pytest
import yaml

from src.experiment.config import _deep_merge, load_experiment_config, apply_overrides


class TestDeepMerge:
    def test_flat(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested(self):
        base = {"model": {"type": "lgbm", "params": {"lr": 0.1, "depth": 6}}}
        override = {"model": {"params": {"lr": 0.05}}}
        result = _deep_merge(base, override)
        assert result["model"]["type"] == "lgbm"
        assert result["model"]["params"]["lr"] == 0.05
        assert result["model"]["params"]["depth"] == 6

    def test_does_not_mutate(self):
        base = {"a": {"b": 1}}
        override = {"a": {"b": 2}}
        base_copy = copy.deepcopy(base)
        _deep_merge(base, override)
        assert base == base_copy


class TestApplyOverrides:
    def test_int_override(self):
        config = {"label": {"T": 14, "X": 0.08}}
        result = apply_overrides(config, ["label.T=21"])
        assert result["label"]["T"] == 21
        assert result["label"]["X"] == 0.08

    def test_float_override(self):
        config = {"label": {"T": 14, "X": 0.08}}
        result = apply_overrides(config, ["label.X=0.12"])
        assert result["label"]["X"] == 0.12

    def test_bool_override(self):
        config = {"debug": False}
        result = apply_overrides(config, ["debug=true"])
        assert result["debug"] is True

    def test_string_override(self):
        config = {"model": {"type": "lgbm"}}
        result = apply_overrides(config, ["model.type=xgboost"])
        assert result["model"]["type"] == "xgboost"

    def test_create_nested(self):
        config = {}
        result = apply_overrides(config, ["a.b.c=42"])
        assert result["a"]["b"]["c"] == 42
