"""概率阈值优化 — 寻找最优分类阈值.

标准分类器使用 0.5 作为阈值，但在金融预测中，
最优阈值往往不在 0.5，因为:
  - 类别不平衡
  - 不同错误的代价不同 (假阳性 vs 假阴性)
  - 概率校准偏差

本模块支持:
  1. 基于 F1 的阈值优化
  2. 基于 Kappa 的阈值优化
  3. 基于 Precision@Recall 的阈值优化
  4. Youden's J 统计量
"""

import logging

import numpy as np
from sklearn.metrics import (
    f1_score,
    cohen_kappa_score,
    precision_score,
    recall_score,
)

logger = logging.getLogger(__name__)


def optimize_threshold(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    metric: str = "f1",
    thresholds: np.ndarray | None = None,
    min_precision: float = 0.0,
) -> tuple[float, float]:
    """寻找最优概率阈值.

    Parameters
    ----------
    y_true : np.ndarray
        真实标签 (0/1)
    y_proba : np.ndarray
        正类概率 (shape: (n,) 或 (n, 2))
    metric : str
        优化目标: "f1", "kappa", "youden", "precision_recall"
    thresholds : np.ndarray | None
        候选阈值列表, 默认 0.1~0.9
    min_precision : float
        最小精确率约束

    Returns
    -------
    tuple[float, float]
        (最优阈值, 最优指标值)
    """
    # 确保 y_proba 是一维正类概率
    if y_proba.ndim == 2:
        y_proba = y_proba[:, 1]

    if thresholds is None:
        thresholds = np.arange(0.20, 0.80, 0.01)

    best_threshold = 0.5
    best_score = -np.inf

    for t in thresholds:
        y_pred = (y_proba >= t).astype(int)

        # 跳过全 0 或全 1 预测
        if y_pred.sum() == 0 or y_pred.sum() == len(y_pred):
            continue

        # 检查精确率约束
        if min_precision > 0:
            prec = precision_score(y_true, y_pred, zero_division=0)
            if prec < min_precision:
                continue

        if metric == "f1":
            score = f1_score(y_true, y_pred, average="binary", zero_division=0)
        elif metric == "kappa":
            score = cohen_kappa_score(y_true, y_pred)
        elif metric == "youden":
            # Youden's J = Sensitivity + Specificity - 1
            tp = ((y_pred == 1) & (y_true == 1)).sum()
            tn = ((y_pred == 0) & (y_true == 0)).sum()
            fp = ((y_pred == 1) & (y_true == 0)).sum()
            fn = ((y_pred == 0) & (y_true == 1)).sum()
            sens = tp / (tp + fn) if (tp + fn) > 0 else 0
            spec = tn / (tn + fp) if (tn + fp) > 0 else 0
            score = sens + spec - 1
        elif metric == "precision_recall":
            # 最大化 F1 但要求 precision >= min_precision
            score = f1_score(y_true, y_pred, average="binary", zero_division=0)
        elif metric == "f1_macro":
            score = f1_score(y_true, y_pred, average="macro", zero_division=0)
        else:
            raise ValueError(f"未知优化指标: {metric}")

        if score > best_score:
            best_score = score
            best_threshold = t

    logger.info(f"阈值优化: metric={metric}, best_threshold={best_threshold:.3f}, "
                f"best_score={best_score:.4f}")

    return float(best_threshold), float(best_score)


def apply_threshold(
    y_proba: np.ndarray,
    threshold: float = 0.5,
) -> np.ndarray:
    """应用概率阈值生成预测.

    Parameters
    ----------
    y_proba : np.ndarray
        正类概率 (shape: (n,) 或 (n, 2))
    threshold : float
        分类阈值

    Returns
    -------
    np.ndarray
        预测标签
    """
    if y_proba.ndim == 2:
        y_proba = y_proba[:, 1]
    return (y_proba >= threshold).astype(int)
