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
}


@register_model("lightgbm")
class LightGBMModel(BaseModel):
    """LightGBM 分类器封装."""

    def __init__(self, params: dict[str, Any] | None = None):
        merged = {**DEFAULT_PARAMS, **(params or {})}
        # 移除旧的硬编码 objective/num_class，让 fit 时自动判断
        # 用户仍可通过 params 显式指定以覆盖
        super().__init__(merged)
        self.model = None
        self._auto_scale_pos_weight = merged.pop("auto_scale_pos_weight", True)
        self._early_stopping_rounds = merged.pop("early_stopping_rounds", None)

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sample_weight: np.ndarray | None = None,
    ) -> "LightGBMModel":
        """训练 LightGBM 模型.

        自动检测二分类/多分类，并对二分类自动设置 scale_pos_weight。
        支持 sample_weight 进行样本加权。
        """
        params = self.params.copy()
        n_classes = len(np.unique(y))

        # --- 自动设置 objective 和 num_class ---
        if "objective" not in params:
            if n_classes == 2:
                params["objective"] = "binary"
                # 移除 num_class（binary 不需要）
                params.pop("num_class", None)
            else:
                params["objective"] = "multiclass"
                params["num_class"] = n_classes
        elif params.get("objective") == "binary":
            params.pop("num_class", None)

        # --- 自动处理类别不平衡 (仅二分类) ---
        if n_classes == 2 and self._auto_scale_pos_weight and "scale_pos_weight" not in params:
            n_pos = (y == 1).sum()
            n_neg = (y == 0).sum()
            if n_pos > 0 and n_neg > 0:
                spw = n_neg / n_pos
                params["scale_pos_weight"] = spw
                logger.info(f"自动设置 scale_pos_weight={spw:.3f} (neg={n_neg}, pos={n_pos})")

        logger.info(f"LightGBM objective={params.get('objective')}, n_classes={n_classes}")

        # --- 早停机制 ---
        fit_kwargs = {}
        if self._early_stopping_rounds and X.shape[0] > 500:
            # 用训练集最后 10% 作为 validation
            val_size = max(int(X.shape[0] * 0.1), 50)
            X_train, X_val = X[:-val_size], X[-val_size:]
            y_train, y_val = y[:-val_size], y[-val_size:]

            callbacks = [
                lgb.early_stopping(self._early_stopping_rounds, verbose=False),
                lgb.log_evaluation(period=0),
            ]

            self.model = lgb.LGBMClassifier(**params)
            self.model.fit(
                X_train,
                y_train,
                eval_set=[(X_val, y_val)],
                callbacks=callbacks,
                sample_weight=sample_weight,
            )
            logger.info(f"LightGBM 早停训练完成, best_iteration={self.model.best_iteration_}")
        else:
            self.model = lgb.LGBMClassifier(**params)
            self.model.fit(X, y, sample_weight=sample_weight)

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
