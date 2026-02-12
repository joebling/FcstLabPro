"""测试特征工程模块."""

import numpy as np
import pandas as pd
import pytest

from src.features.registry import list_feature_sets, get_feature_set
from src.features.builder import build_features, get_feature_columns


def _make_sample_df(n=300):
    """生成测试用 OHLCV 数据."""
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    close = 30000 + np.cumsum(np.random.randn(n) * 500)
    return pd.DataFrame({
        "open": close + np.random.randn(n) * 100,
        "high": close + abs(np.random.randn(n) * 300),
        "low": close - abs(np.random.randn(n) * 300),
        "close": close,
        "volume": np.random.randint(1000, 10000, n).astype(float),
    }, index=dates)


class TestFeatureRegistry:
    def test_technical_registered(self):
        assert "technical" in list_feature_sets()

    def test_volume_registered(self):
        assert "volume" in list_feature_sets()

    def test_flow_registered(self):
        assert "flow" in list_feature_sets()

    def test_unknown_raises(self):
        with pytest.raises(KeyError):
            get_feature_set("nonexistent")


class TestBuildFeatures:
    def test_builds_technical(self):
        df = _make_sample_df()
        result = build_features(df, ["technical"])
        assert len(result.columns) > len(df.columns)
        assert len(result) > 0

    def test_builds_multiple(self):
        df = _make_sample_df()
        result = build_features(df, ["technical", "volume"])
        assert len(result.columns) > len(df.columns)

    def test_no_nan(self):
        df = _make_sample_df()
        result = build_features(df, ["technical", "volume"])
        assert result.isna().sum().sum() == 0

    def test_get_feature_columns(self):
        df = _make_sample_df()
        result = build_features(df, ["technical"])
        cols = get_feature_columns(result)
        assert "close" not in cols
        assert "open" not in cols
        assert len(cols) > 0
