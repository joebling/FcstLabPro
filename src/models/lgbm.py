"""LightGBM 模型实现."""

import logging
from typing import Any

import numpy as np
import lightgbm as lgb

from src.models.base import BaseModel
from src.models.registry import register_model

logger = logging.getLogger(__name__)

DEFAULT_PARAMS = {
    "n_estimators": 500,
    "max_depth": 6,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_samples": 20,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "random_state": 42,
    "verbose": -1,
    "objective": "multiclass",
    "num_class": 3,
}


@register_model("lightgbm")
class LightGBMModel(BaseModel):
    """LightGBM 分类器封装."""

    def __init__(self, params: dict[str, Any] | None = None):
        merged = {**DEFAULT_PARAMS, **(params or {})}
        super().__init__(merged)
        self.model = lgb.LGBMClassifier(**self.params)

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LightGBMModel":
        """训练 LightGBM 模型."""
        self.model.fit(X, y)
        self.is_fitted = True
        logger.info(f"LightGBM 训练完成, n_features={X.shape[1]}, n_samples={X.shape[0]}")
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测类别."""
        if not self.is_fitted:
            raise RuntimeError("模型尚未训练")
        return self.model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """预测概率."""
        if not self.is_fitted:
            raise RuntimeError("模型尚未训练")
        return self.model.predict_proba(X)

    def feature_importance(self) -> np.ndarray:
        """获取特征重要性 (gain)."""
        if not self.is_fitted:
            raise RuntimeError("模型尚未训练")
        return self.model.feature_importances_
