"""Orion-BiX 模型封装.

Orion-BiX 是基于 Bi-Axial Attention + In-Context Learning 的
表格数据基础模型，适用于小样本分类任务。
"""

import logging
from typing import Any

import numpy as np

from src.models.base import BaseModel
from src.models.registry import register_model

logger = logging.getLogger(__name__)

DEFAULT_PARAMS = {
    "n_estimators": 16,
    "random_state": 42,
}


@register_model("orion_bix")
class OrionBixModel(BaseModel):
    """Orion-BiX 分类器封装."""

    def __init__(self, params: dict[str, Any] | None = None):
        merged = {**DEFAULT_PARAMS, **(params or {})}
        super().__init__(merged)
        self.model = None

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sample_weight: np.ndarray | None = None,
    ) -> "OrionBixModel":
        """Train Orion-BiX model."""
        from orion_bix import OrionBixClassifier

        # Filter params to only those accepted by OrionBixClassifier
        valid_keys = {
            "n_estimators", "norm_methods", "feat_shuffle_method",
            "class_shift", "outlier_threshold", "softmax_temperature",
            "average_logits", "use_hierarchical", "use_amp", "batch_size",
            "device", "n_jobs", "random_state",
        }
        model_params = {k: v for k, v in self.params.items() if k in valid_keys}

        self.model = OrionBixClassifier(**model_params)

        logger.info(
            f"Orion-BiX 训练中: n_features={X.shape[1]}, "
            f"n_samples={X.shape[0]}, n_estimators={model_params.get('n_estimators', 32)}"
        )
        self.model.fit(X, y)
        self.is_fitted = True
        logger.info("Orion-BiX 训练完成")
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("模型尚未训练")
        return self.model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("模型尚未训练")
        return self.model.predict_proba(X)

    def feature_importance(self) -> np.ndarray | None:
        """Orion-BiX 不提供特征重要性."""
        return None
