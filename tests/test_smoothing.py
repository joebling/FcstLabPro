"""Smoothing 模块单元测试."""

import numpy as np
import pandas as pd
import pytest

from src.features.smoothing import _savgol_causal, apply_smoothing


def _make_noisy_ohlcv(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """生成带噪声的 OHLCV 测试数据."""
    rng = np.random.default_rng(seed)
    # 基础价格: 正弦波 + 噪声
    t = np.arange(n, dtype=float)
    base = 50000 + 5000 * np.sin(t / 30) + rng.normal(0, 500, n)
    close = base
    high = close + rng.uniform(100, 1000, n)
    low = close - rng.uniform(100, 1000, n)
    volume = rng.uniform(1e8, 5e8, n)
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


class TestSavgolCausal:
    """测试因果 SG 滤波器."""

    def test_output_shape_matches_input(self):
        x = np.random.randn(100)
        result = _savgol_causal(x, window=11, polyorder=3)
        assert result.shape == x.shape

    def test_short_series_returns_original(self):
        x = np.array([1.0, 2.0, 3.0])
        result = _savgol_causal(x, window=5, polyorder=2)
        np.testing.assert_array_equal(result, x)

    def test_smoothing_reduces_noise(self):
        rng = np.random.default_rng(123)
        signal = np.sin(np.linspace(0, 4 * np.pi, 200))
        noisy = signal + rng.normal(0, 0.3, 200)
        smoothed = _savgol_causal(noisy, window=11, polyorder=3)
        # 平滑后应该更接近原始信号
        error_raw = np.mean((noisy[20:] - signal[20:]) ** 2)
        error_smooth = np.mean((smoothed[20:] - signal[20:]) ** 2)
        assert error_smooth < error_raw, (
            f"SG 平滑后误差 ({error_smooth:.4f}) 应小于原始 ({error_raw:.4f})"
        )

    def test_no_lookahead_bias(self):
        """SG 滤波器不应使用未来数据."""
        rng = np.random.default_rng(42)
        x = rng.randn(100)
        smoothed_full = _savgol_causal(x, window=11, polyorder=3)

        # 只用前 50 个点平滑
        smoothed_partial = _savgol_causal(x[:50], window=11, polyorder=3)

        # 前 50 个点的结果应该完全一致 (因果性 = 不看未来)
        np.testing.assert_array_almost_equal(
            smoothed_full[:50], smoothed_partial,
            err_msg="因果 SG 滤波存在前瞻性泄漏!"
        )

    def test_window_gt_polyorder(self):
        with pytest.raises(ValueError, match="必须大于"):
            _savgol_causal(np.array([1, 2, 3]), window=2, polyorder=3)


class TestApplySmoothing:
    """测试 apply_smoothing 集成函数."""

    def test_none_method_returns_unchanged(self):
        df = _make_noisy_ohlcv(50)
        result = apply_smoothing(df, method="none")
        pd.testing.assert_frame_equal(result, df)

    def test_savgol_changes_values(self):
        df = _make_noisy_ohlcv(100)
        result = apply_smoothing(df, method="savgol", window=11)
        # close 列应该发生变化
        assert not np.allclose(df["close"].values, result["close"].values)

    def test_even_window_auto_corrected(self):
        df = _make_noisy_ohlcv(100)
        # 偶数窗口应自动修正为奇数
        result = apply_smoothing(df, method="savgol", window=10)
        assert result is not None  # 不应报错

    def test_preserves_nan_positions(self):
        df = _make_noisy_ohlcv(100)
        df.loc[df.index[5:8], "close"] = np.nan
        result = apply_smoothing(df, method="savgol", window=11)
        assert result["close"].isna().sum() == 3

    def test_custom_columns(self):
        df = _make_noisy_ohlcv(100)
        original_volume = df["volume"].copy()
        result = apply_smoothing(df, method="savgol", columns=["close"])
        # volume 不应被平滑
        np.testing.assert_array_equal(result["volume"].values, original_volume.values)
