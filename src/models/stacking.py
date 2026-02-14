"""Stacking 集成模型 — 多模型融合.

实现两层 Stacking:
  Layer 1: 多个基学习器 (LightGBM 不同超参 + 可选 XGBoost/CatBoost)
  Layer 2: 逻辑回归/LightGBM 作为元学习器

Walk-Forward 中每个 fold 独立做 Stacking 内部 CV，
避免任何形式的信息泄漏。
"""

import logging
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit

from src.models.base import BaseModel
from src.models.registry import register_model

logger = logging.getLogger(__name__)

# 默认基学习器配置
DEFAULT_BASE_MODELS = [
    {
        "name": "lgbm_deep",
        "type": "lightgbm_raw",
        "params": {
            "n_estimators": 600,
            "max_depth": 6,
            "num_leaves": 31,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.7,
            "min_child_samples": 20,
            "reg_alpha": 0.1,
            "reg_lambda": 0.1,
            "verbose": -1,
            "random_state": 42,
        },
    },
    {
        "name": "lgbm_shallow",
        "type": "lightgbm_raw",
        "params": {
            "n_estimators": 800,
            "max_depth": 3,
            "num_leaves": 8,
            "learning_rate": 0.03,
            "subsample": 0.7,
            "colsample_bytree": 0.5,
            "min_child_samples": 40,
            "reg_alpha": 0.5,
            "reg_lambda": 0.5,
            "verbose": -1,
            "random_state": 123,
        },
    },
    {
        "name": "lgbm_wide",
        "type": "lightgbm_raw",
        "params": {
            "n_estimators": 500,
            "max_depth": 5,
            "num_leaves": 24,
            "learning_rate": 0.08,
            "subsample": 0.9,
            "colsample_bytree": 0.8,
            "min_child_samples": 15,
            "reg_alpha": 0.05,
            "reg_lambda": 0.2,
            "min_split_gain": 0.01,
            "verbose": -1,
            "random_state": 456,
        },
    },
    {
        "name": "lgbm_conservative",
        "type": "lightgbm_raw",
        "params": {
            "n_estimators": 400,
            "max_depth": 4,
            "num_leaves": 12,
            "learning_rate": 0.02,
            "subsample": 0.6,
            "colsample_bytree": 0.4,
            "min_child_samples": 50,
            "reg_alpha": 1.0,
            "reg_lambda": 1.0,
            "min_split_gain": 0.05,
            "verbose": -1,
            "random_state": 789,
        },
    },
]


def _create_lgbm_classifier(params: dict) -> Any:
    """创建 LightGBM 分类器实例."""
    import lightgbm as lgb
    p = params.copy()
    return lgb.LGBMClassifier(**p)


@register_model("stacking")
class StackingModel(BaseModel):
    """Stacking 集成模型.

    Parameters (在 params dict 中传递)
    ----------
    base_models : list[dict]
        基学习器配置列表, 每个元素 {"name", "type", "params"}
    meta_model : str
        元学习器类型: "logistic" 或 "lightgbm"
    n_cv_folds : int
        生成 meta features 的内部 CV 折数
    use_proba : bool
        是否使用概率特征 (True) 还是硬预测 (False)
    passthrough : bool
        是否将原始特征也传给元学习器
    auto_scale_pos_weight : bool
        基学习器是否自动处理类别不平衡
    """

    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__(params or {})
        self._base_configs = self.params.get("base_models", DEFAULT_BASE_MODELS)
        self._meta_type = self.params.get("meta_model", "logistic")
        self._n_cv_folds = self.params.get("n_cv_folds", 3)
        self._use_proba = self.params.get("use_proba", True)
        self._passthrough = self.params.get("passthrough", False)
        self._auto_scale = self.params.get("auto_scale_pos_weight", True)

        self._base_models = []   # 训练好的基学习器
        self._meta_model = None  # 训练好的元学习器
        self._n_meta_features = 0
        self.model = None  # 用于兼容基类

    def fit(self, X: np.ndarray, y: np.ndarray) -> "StackingModel":
        """训练 Stacking 模型.

        使用 TimeSeriesSplit 生成 out-of-fold 预测作为 meta features.
        """
        n_classes = len(np.unique(y))
        n_models = len(self._base_configs)

        logger.info(f"Stacking 训练开始: {n_models} 基学习器, "
                    f"内部 {self._n_cv_folds}-fold CV")

        # ========== Step 1: 生成 out-of-fold meta features ==========
        if self._use_proba:
            # 每个模型一个概率列 (二分类用正类概率)
            meta_features = np.zeros((len(X), n_models))
        else:
            meta_features = np.zeros((len(X), n_models))

        tscv = TimeSeriesSplit(n_splits=self._n_cv_folds)

        for i, cfg in enumerate(self._base_configs):
            model_name = cfg["name"]
            params = cfg["params"].copy()

            # 自动处理类别不平衡
            if n_classes == 2 and self._auto_scale and "scale_pos_weight" not in params:
                n_pos = (y == 1).sum()
                n_neg = (y == 0).sum()
                if n_pos > 0 and n_neg > 0:
                    params["scale_pos_weight"] = n_neg / n_pos

            if n_classes == 2:
                params.setdefault("objective", "binary")
                params.pop("num_class", None)
            else:
                params.setdefault("objective", "multiclass")
                params.setdefault("num_class", n_classes)

            # Out-of-fold predictions
            for fold_idx, (train_idx, val_idx) in enumerate(tscv.split(X)):
                m = _create_lgbm_classifier(params)
                m.fit(X[train_idx], y[train_idx])

                if self._use_proba:
                    proba = m.predict_proba(X[val_idx])
                    if proba.ndim == 2:
                        meta_features[val_idx, i] = proba[:, 1]
                    else:
                        meta_features[val_idx, i] = proba
                else:
                    meta_features[val_idx, i] = m.predict(X[val_idx])

            logger.info(f"  基学习器 '{model_name}' OOF 完成")

        # ========== Step 2: 在全部训练集上重新训练所有基学习器 ==========
        self._base_models = []
        for cfg in self._base_configs:
            params = cfg["params"].copy()
            if n_classes == 2 and self._auto_scale and "scale_pos_weight" not in params:
                n_pos = (y == 1).sum()
                n_neg = (y == 0).sum()
                if n_pos > 0 and n_neg > 0:
                    params["scale_pos_weight"] = n_neg / n_pos
            if n_classes == 2:
                params.setdefault("objective", "binary")
                params.pop("num_class", None)
            else:
                params.setdefault("objective", "multiclass")
                params.setdefault("num_class", n_classes)

            m = _create_lgbm_classifier(params)
            m.fit(X, y)
            self._base_models.append(m)

        # ========== Step 3: 训练元学习器 ==========
        # 只用有 OOF 预测的部分 (第一个 fold 的训练集没有 OOF)
        first_val_start = list(tscv.split(X))[0][1][0]
        meta_X = meta_features[first_val_start:]
        meta_y = y[first_val_start:]

        if self._passthrough:
            meta_X = np.hstack([meta_X, X[first_val_start:]])

        if self._meta_type == "logistic":
            self._meta_model = LogisticRegression(
                C=1.0, max_iter=1000, random_state=42,
                class_weight="balanced" if self._auto_scale else None,
            )
            self._meta_model.fit(meta_X, meta_y)
        elif self._meta_type == "lightgbm":
            import lightgbm as lgb
            meta_params = {
                "n_estimators": 100,
                "max_depth": 2,
                "num_leaves": 4,
                "learning_rate": 0.1,
                "verbose": -1,
                "random_state": 42,
            }
            if n_classes == 2:
                meta_params["objective"] = "binary"
            self._meta_model = lgb.LGBMClassifier(**meta_params)
            self._meta_model.fit(meta_X, meta_y)
        else:
            raise ValueError(f"未知元学习器: {self._meta_type}")

        self._n_meta_features = meta_X.shape[1]
        self.is_fitted = True
        self.model = self  # 用于兼容

        logger.info(f"Stacking 训练完成: meta_features={self._n_meta_features}, "
                    f"meta_model={self._meta_type}")
        return self

    def _build_meta_features(self, X: np.ndarray) -> np.ndarray:
        """从基学习器生成 meta features."""
        n_models = len(self._base_models)
        meta = np.zeros((len(X), n_models))

        for i, m in enumerate(self._base_models):
            if self._use_proba:
                proba = m.predict_proba(X)
                if proba.ndim == 2:
                    meta[:, i] = proba[:, 1]
                else:
                    meta[:, i] = proba
            else:
                meta[:, i] = m.predict(X)

        if self._passthrough:
            meta = np.hstack([meta, X])

        return meta

    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测类别."""
        if not self.is_fitted:
            raise RuntimeError("模型尚未训练")
        meta_X = self._build_meta_features(X)
        return self._meta_model.predict(meta_X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """预测概率."""
        if not self.is_fitted:
            raise RuntimeError("模型尚未训练")
        meta_X = self._build_meta_features(X)
        return self._meta_model.predict_proba(meta_X)

    def feature_importance(self) -> np.ndarray:
        """获取特征重要性.

        返回各基学习器特征重要性的加权平均。
        """
        if not self.is_fitted:
            raise RuntimeError("模型尚未训练")

        importances = []
        for m in self._base_models:
            fi = m.feature_importances_
            # 归一化
            fi_sum = fi.sum()
            if fi_sum > 0:
                fi = fi / fi_sum
            importances.append(fi)

        # 取平均
        avg_importance = np.mean(importances, axis=0)
        return avg_importance
