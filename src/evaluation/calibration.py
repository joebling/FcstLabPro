"""概率校准模块 — Platt Scaling + Isotonic Regression."""

import logging
from enum import Enum

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.base import BaseEstimator

logger = logging.getLogger(__name__)


class CalibrationMethod(Enum):
    """校准方法枚举."""
    PLATT = "platt"       # Platt Scaling (Sigmoid)
    ISOTONIC = "isotonic" # Isotonic Regression
    NONE = "none"


def calibrate_proba(
    model: BaseEstimator,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    method: str = "platt",
    cv: int = 3,
) -> tuple[BaseEstimator, dict]:
    """概率校准.

    Parameters
    ----------
    model : BaseEstimator
        原始模型
    X_train : np.ndarray
        训练特征
    y_train : np.ndarray
        训练标签
    X_val : np.ndarray
        验证特征
    y_val : np.ndarray
        验证标签
    method : str
        校准方法: "platt" | "isotonic"
    cv : int
        交叉验证折数

    Returns
    -------
    tuple[BaseEstimator, dict]
        校准后的模型, 校准信息
    """
    if method == "none":
        return model, {"method": "none"}

    method_map = {
        "platt": CalibrationMethod.PLATT,
        "isotonic": CalibrationMethod.ISOTONIC,
    }

    calib_method = method_map.get(method.lower(), CalibrationMethod.PLATT)

    try:
        # CalibratedClassifierCV 使用 cv='prefit' 需要先训练基础模型
        # 使用 internal cv 进行校准
        calibrated_model = CalibratedClassifierCV(
            estimator=model,
            method=calib_method.value,
            cv=cv,
        )

        # 训练校准模型
        calibrated_model.fit(X_train, y_train)

        # 评估校准效果
        from sklearn.metrics import brier_score_loss

        # 原始模型概率
        model.fit(X_train, y_train)
        orig_proba = model.predict_proba(X_val)[:, 1]
        orig_brier = brier_score_loss(y_val, orig_proba)

        # 校准后概率
        calib_proba = calibrated_model.predict_proba(X_val)[:, 1]
        calib_brier = brier_score_loss(y_val, calib_proba)

        info = {
            "method": method,
            "orig_brier": orig_brier,
            "calib_brier": calib_brier,
            "brier_improvement": (orig_brier - calib_brier) / (orig_brier + 1e-10),
        }

        logger.info(f"  概率校准 ({method}): Brier {orig_brier:.4f} -> {calib_brier:.4f}")

        return calibrated_model, info

    except Exception as e:
        logger.warning(f"  概率校准失败，回退原始模型: {e}")
        return model, {"method": "none", "error": str(e)}


def apply_calibration(
    model,
    X_train: np.ndarray,
    y_train: np.ndarray,
    method: str = "platt",
    cv: int = 3,
):
    """应用概率校准（使用内部交叉验证）.

    Parameters
    ----------
    model : BaseModel
        原始模型 (BaseModel 包装)
    X_train : np.ndarray
        训练特征
    y_train : np.ndarray
        训练标签
    method : str
        校准方法
    cv : int
        交叉验证折数

    Returns
    -------
    BaseEstimator
        校准后的模型
    """
    if method == "none":
        return model

    method_map = {
        "platt": "sigmoid",
        "isotonic": "isotonic",
    }

    try:
        # 获取底层的 LightGBM 模型
        lgbm_model = model.model

        calibrated_model = CalibratedClassifierCV(
            estimator=lgbm_model,
            method=method_map.get(method.lower(), "sigmoid"),
            cv=cv,
        )
        calibrated_model.fit(X_train, y_train)
        logger.info(f"  概率校准已应用: {method}")

        # 返回一个包装器，保持接口兼容
        class CalibratedWrapper:
            def __init__(self, calibrated):
                self.model = calibrated

            def predict(self, X):
                return self.model.predict(X)

            def predict_proba(self, X):
                return self.model.predict_proba(X)

            def feature_importance(self):
                return self.model.estimator.feature_importances_

        return CalibratedWrapper(calibrated_model)
    except Exception as e:
        logger.warning(f"  校准失败: {e}")
        return model
