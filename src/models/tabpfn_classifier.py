"""TabPFN 模型实现."""

import logging
from typing import Any

import numpy as np
from sklearn.preprocessing import StandardScaler

from src.models.base import BaseModel
from src.models.registry import register_model

logger = logging.getLogger(__name__)

DEFAULT_PARAMS = {
    "n_estimators": 8,
    "balance_probabilities": True,
    "random_state": 42,
}


@register_model("tabpfn")
class TabPFNModel(BaseModel):
    """TabPFN 分类器封装.

    TabPFN 是一个轻量级的表格数据预测模型，由 priorshop 提供。
    特点：
    - 小样本友好（<10k 样本最佳）
    - 无需复杂调参
    - 自动处理特征标准化
    """

    def __init__(self, params: dict[str, Any] | None = None):
        merged = {**DEFAULT_PARAMS, **(params or {})}
        super().__init__(merged)
        self.model = None
        self.scaler = StandardScaler()
        self._n_classes = None

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sample_weight: np.ndarray | None = None,
    ) -> "TabPFNModel":
        """训练 TabPFN 模型.

        注意：TabPFN 不直接支持 sample_weight，但可以通过复制数据来实现加权。
        """
        from tabpfn import TabPFNClassifier

        # 记录类别数
        self._n_classes = len(np.unique(y))

        # TabPFN 需要标准化
        X_scaled = self.scaler.fit_transform(X)

        # 只传递 TabPFN 有效的参数
        valid_params = {
            "n_estimators": self.params.get("n_estimators", 8),
            "balance_probabilities": self.params.get("balance_probabilities", True),
            "device": self.params.get("device", "cpu"),
            "random_state": self.params.get("random_state", 42),
            "ignore_pretraining_limits": True,  # 允许 CPU 大数据集
        }
        # 创建模型
        self.model = TabPFNClassifier(**valid_params)

        # TabPFN 不直接支持 sample_weight
        # 如果需要，可以复制少数类样本
        if sample_weight is not None and np.any(sample_weight > 1):
            # 简单处理：找出权重 > 1 的样本（通常是少数类）
            # 复制这些样本
            weighted_indices = np.where(sample_weight > 1)[0]
            if len(weighted_indices) > 0:
                X_aug = [X_scaled]
                y_aug = [y]
                for idx in weighted_indices:
                    n_repeat = int(sample_weight[idx]) - 1
                    if n_repeat > 0:
                        X_aug.append(np.tile(X_scaled[idx], (n_repeat, 1)))
                        y_aug.append(np.tile(y[idx], (n_repeat,)))
                X_scaled = np.vstack(X_aug)
                y = np.concatenate(y_aug)
                logger.info(f"TabPFN 样本加权后: {X.shape[0]} -> {X_scaled.shape[0]}")

        logger.info(
            f"TabPFN 训练中, n_features={X_scaled.shape[1]}, "
            f"n_samples={X_scaled.shape[0]}, n_classes={self._n_classes}"
        )

        self.model.fit(X_scaled, y)
        self.is_fitted = True
        logger.info("TabPFN 训练完成")
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测类别."""
        if not self.is_fitted:
            raise RuntimeError("模型尚未训练")
        X_scaled = self.scaler.transform(X)
        return self.model.predict(X_scaled)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """预测概率."""
        if not self.is_fitted:
            raise RuntimeError("模型尚未训练")
        X_scaled = self.scaler.transform(X)
        return self.model.predict_proba(X_scaled)

    def feature_importance(self) -> np.ndarray:
        """获取特征重要性.

        TabPFN 不直接提供特征重要性，返回 None。
        """
        logger.warning("TabPFN 不提供特征重要性，返回全零数组")
        # 返回零数组作为占位符
        if self.model is not None and hasattr(self.model, "n_features_in_"):
            return np.zeros(self.model.n_features_in_)
        return np.array([])
