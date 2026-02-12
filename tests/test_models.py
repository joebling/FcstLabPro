"""测试模型模块."""

import numpy as np
import pytest

from src.models.registry import create_model, list_models, get_model_class
from src.models.base import BaseModel


class TestModelRegistry:
    def test_lightgbm_registered(self):
        # 触发注册
        import src.models.lgbm  # noqa: F401
        assert "lightgbm" in list_models()

    def test_create_model(self):
        import src.models.lgbm  # noqa: F401
        model = create_model("lightgbm")
        assert isinstance(model, BaseModel)

    def test_unknown_raises(self):
        with pytest.raises(KeyError):
            get_model_class("nonexistent")


class TestLightGBMModel:
    def test_fit_predict(self):
        import src.models.lgbm  # noqa: F401
        np.random.seed(42)
        X = np.random.randn(200, 10)
        y = np.random.choice([0, 1, 2], size=200)

        model = create_model("lightgbm", {"n_estimators": 10, "verbose": -1})
        model.fit(X, y)

        assert model.is_fitted
        preds = model.predict(X)
        assert len(preds) == 200
        assert set(preds).issubset({0, 1, 2})

    def test_predict_proba(self):
        import src.models.lgbm  # noqa: F401
        np.random.seed(42)
        X = np.random.randn(100, 5)
        y = np.random.choice([0, 1, 2], size=100)

        model = create_model("lightgbm", {"n_estimators": 10, "verbose": -1})
        model.fit(X, y)
        proba = model.predict_proba(X)

        assert proba.shape == (100, 3)
        assert np.allclose(proba.sum(axis=1), 1.0, atol=1e-6)

    def test_feature_importance(self):
        import src.models.lgbm  # noqa: F401
        np.random.seed(42)
        X = np.random.randn(100, 8)
        y = np.random.choice([0, 1, 2], size=100)

        model = create_model("lightgbm", {"n_estimators": 10, "verbose": -1})
        model.fit(X, y)
        fi = model.feature_importance()

        assert len(fi) == 8
