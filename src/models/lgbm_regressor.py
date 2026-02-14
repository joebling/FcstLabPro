"""LightGBM 回归模型 — 预测收益率 + 阈值转化为分类.

思路:
  - 用回归目标直接预测未来 T 日的收益率
  - 回归损失函数对收益率幅度敏感，不丢失信息
  - 在推理时通过概率阈值将连续值转化为分类标签
  - 避免分类标签化带来的信息损失
"""

import logging
from typing import Any

import numpy as np
import lightgbm as lgb

from src.models.base import BaseModel
from src.models.registry import register_model

logger = logging.getLogger(__name__)


@register_model("lightgbm_regressor")
class LightGBMRegressor(BaseModel):
    """LightGBM 回归器 — 预测连续值后转分类.

    在 fit 时训练回归器预测连续标签值。
    在 predict 时使用阈值转化为二分类（由外部或内部决定阈值）。

    使用方式:
      - 标签仍然用 0/1，但作为回归目标 (回归 0~1 之间)
      - predict 使用阈值 0.5 (或优化后的)
      - predict_proba 返回回归值 (伪概率)
    """

    def __init__(self, params: dict[str, Any] | None = None):
        merged = params.copy() if params else {}
        self._threshold = merged.pop("classification_threshold", 0.5)
        self._auto_threshold = merged.pop("auto_threshold", False)
        self._threshold_metric = merged.pop("threshold_metric", "f1")
        super().__init__(merged)
        self.model = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LightGBMRegressor":
        """训练 LightGBM 回归模型."""
        params = self.params.copy()

        # 强制使用回归目标
        params["objective"] = "regression"
        params.pop("num_class", None)
        params.pop("scale_pos_weight", None)
        params.pop("auto_scale_pos_weight", None)

        # 设置合理的默认值
        params.setdefault("n_estimators", 600)
        params.setdefault("max_depth", 5)
        params.setdefault("learning_rate", 0.05)
        params.setdefault("verbose", -1)

        self.model = lgb.LGBMRegressor(**params)
        self.model.fit(X, y.astype(float))

        # 如果启用自动阈值，在训练集上寻找最优阈值
        if self._auto_threshold:
            from src.evaluation.threshold_optimizer import optimize_threshold
            y_reg = self.model.predict(X)
            # clip 到 [0, 1] 范围
            y_reg = np.clip(y_reg, 0, 1)
            best_t, best_score = optimize_threshold(
                y_true=y.astype(int),
                y_proba=y_reg,
                metric=self._threshold_metric,
            )
            self._threshold = best_t
            logger.info(f"自动阈值优化: threshold={best_t:.3f}, "
                        f"{self._threshold_metric}={best_score:.4f}")

        self.is_fitted = True
        logger.info(f"LightGBM 回归训练完成, n_features={X.shape[1]}, "
                    f"n_samples={X.shape[0]}, threshold={self._threshold:.3f}")
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测类别 (基于阈值)."""
        if not self.is_fitted:
            raise RuntimeError("模型尚未训练")
        y_reg = self.model.predict(X)
        y_reg = np.clip(y_reg, 0, 1)
        return (y_reg >= self._threshold).astype(int)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """返回伪概率 (回归值 clipped 到 [0,1]).

        返回 shape (n, 2) 以兼容标准概率输出。
        """
        if not self.is_fitted:
            raise RuntimeError("模型尚未训练")
        y_reg = self.model.predict(X)
        y_reg = np.clip(y_reg, 0, 1)
        return np.column_stack([1 - y_reg, y_reg])

    def feature_importance(self) -> np.ndarray:
        """获取特征重要性 (gain)."""
        if not self.is_fitted:
            raise RuntimeError("模型尚未训练")
        return self.model.feature_importances_
