"""锁定 LightGBM sklearn wrapper 的关键行为 quirk.

为什么需要这些测试:
  - 我们的 P0 漏洞修复 (feature_cols.json 显式校验) 是建立在
    "LightGBM 不会自动按 feature_names_in_ 校验列名" 这一前提上。
  - 如果未来 LightGBM 升级修复了此行为, 这些测试会失败, 那时
    可以**考虑**放宽外层校验 (但不强求, 显式校验本身仍是好实践)。
  - 反过来, 如果这些测试通过 → 列序漏洞依然存在 → 外层校验是必需的。
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

lgb = pytest.importorskip("lightgbm")


@pytest.fixture(scope="module")
def trained_model_and_data():
    """训练一个小 LGBMClassifier (DataFrame fit), 返回 (model, X_df, y)."""
    rng = np.random.RandomState(42)
    n, d = 500, 20
    X = rng.randn(n, d).astype(np.float64)
    y = (X[:, 1] + 0.5 * X[:, 2] + rng.randn(n) * 0.3 > 0).astype(int)
    cols = [f"feat_{i}" for i in range(d)]
    X_df = pd.DataFrame(X, columns=cols)

    m = lgb.LGBMClassifier(
        n_estimators=50, max_depth=4, random_state=42, n_jobs=1, verbose=-1
    )
    m.fit(X_df, y)
    return m, X_df, y


def test_ndarray_fit_and_dataframe_fit_are_bit_exact():
    """改 runner.py 用 DataFrame fit 是否会改变模型? 不会 → 安全."""
    rng = np.random.RandomState(42)
    X = rng.randn(500, 20).astype(np.float64)
    y = (rng.randn(500) > 0).astype(int)
    cols = [f"feat_{i}" for i in range(20)]

    params = dict(n_estimators=50, max_depth=4, random_state=42, n_jobs=1, verbose=-1)
    m_nd = lgb.LGBMClassifier(**params).fit(X, y)
    m_df = lgb.LGBMClassifier(**params).fit(pd.DataFrame(X, columns=cols), y)

    np.testing.assert_array_equal(
        m_nd.predict_proba(X),
        m_df.predict_proba(pd.DataFrame(X, columns=cols)),
    )


def test_feature_names_in_is_preserved_with_dataframe_fit(trained_model_and_data):
    """DataFrame fit 后, sklearn 标准属性 feature_names_in_ 应该是真名."""
    m, X_df, _ = trained_model_and_data
    assert list(m.feature_names_in_) == list(X_df.columns)


def test_lightgbm_does_not_validate_shuffled_dataframe_columns(trained_model_and_data):
    """🚨 关键 quirk 锁定: 列名相同但顺序打乱 → LightGBM 不报错, 静默给出不同结果.

    这是 P0 漏洞的核心证据。如果这个测试有一天失败 (即 LightGBM 开始挡了),
    说明上游修复了此行为, 那时 validate_feature_cols 仍然有价值但不再唯一防线。
    """
    m, X_df, _ = trained_model_and_data
    sample = X_df.iloc[[0]]
    shuffled = sample.iloc[:, ::-1]  # 列名一样, 顺序反转

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        proba_normal = m.predict_proba(sample)
        proba_shuffled = m.predict_proba(shuffled)

    # 没有任何警告
    feature_warns = [wi for wi in w if "feature" in str(wi.message).lower()]
    assert not feature_warns, (
        f"LightGBM 现在会发警告了? 收到: {[str(x.message) for x in feature_warns]}. "
        "这是好事, 但要重新评估 validate_feature_cols 的必要性。"
    )

    # 结果不同, 证明确实是按位置错位计算的
    diff = np.abs(proba_normal - proba_shuffled).max()
    assert diff > 1e-6, (
        f"LightGBM 现在按列名重排了? max_diff={diff:.2e}. "
        "若如此, P0 quirk 已被上游修复, 可以放宽 validate_feature_cols。"
    )


def test_lightgbm_does_not_validate_wrong_column_names(trained_model_and_data):
    """🚨 更宽松场景: 列名完全不对 → LightGBM 依然不报错, 按位置硬塞."""
    m, X_df, _ = trained_model_and_data
    sample = X_df.iloc[[0]]
    wrong_names = sample.copy()
    wrong_names.columns = [f"BAD_{i}" for i in range(len(sample.columns))]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        proba_normal = m.predict_proba(sample)
        proba_wrong = m.predict_proba(wrong_names)

    feature_warns = [wi for wi in w if "feature" in str(wi.message).lower()]
    assert not feature_warns, (
        f"LightGBM 现在校验列名了? 收到: {[str(x.message) for x in feature_warns]}"
    )
    # 列名错但顺序对 → 结果应一致 (证明 LightGBM 只看位置)
    np.testing.assert_array_equal(proba_normal, proba_wrong)
