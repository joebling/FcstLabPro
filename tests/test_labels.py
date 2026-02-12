"""测试标签生成模块."""

import numpy as np
import pandas as pd
import pytest

from src.labels.reversal import generate_reversal_labels


def _make_sample_df(n=300):
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    close = 30000 + np.cumsum(np.random.randn(n) * 500)
    return pd.DataFrame({
        "open": close,
        "high": close + 200,
        "low": close - 200,
        "close": close,
        "volume": np.ones(n) * 5000,
    }, index=dates)


class TestReversalLabels:
    def test_output_shape(self):
        df = _make_sample_df()
        labels = generate_reversal_labels(df, T=14, X=0.08)
        assert len(labels) == len(df)

    def test_label_values(self):
        df = _make_sample_df()
        labels = generate_reversal_labels(df, T=14, X=0.08)
        valid = labels.dropna()
        assert set(valid.unique()).issubset({0, 1, 2})

    def test_last_T_are_nan(self):
        df = _make_sample_df()
        T = 14
        labels = generate_reversal_labels(df, T=T, X=0.08)
        assert labels.iloc[-T:].isna().all()

    def test_different_params(self):
        df = _make_sample_df()
        l1 = generate_reversal_labels(df, T=7, X=0.05)
        l2 = generate_reversal_labels(df, T=21, X=0.15)
        # 不同参数应该产生不同的标签分布
        assert not l1.dropna().equals(l2.dropna())
