"""评估指标计算模块."""

import logging

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    cohen_kappa_score,
    classification_report,
    confusion_matrix,
)

logger = logging.getLogger(__name__)


def compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    metric_names: list[str] | None = None,
) -> dict[str, float]:
    """计算分类评估指标.

    Parameters
    ----------
    y_true : np.ndarray
        真实标签
    y_pred : np.ndarray
        预测标签
    metric_names : list[str] | None
        要计算的指标列表, None 则计算全部

    Returns
    -------
    dict[str, float]
        指标名 -> 值
    """
    all_metrics = {
        "accuracy": lambda: accuracy_score(y_true, y_pred),
        "f1_macro": lambda: f1_score(y_true, y_pred, average="macro", zero_division=0),
        "f1_weighted": lambda: f1_score(y_true, y_pred, average="weighted", zero_division=0),
        "f1_binary": lambda: f1_score(y_true, y_pred, average="binary", zero_division=0),
        "precision_macro": lambda: precision_score(y_true, y_pred, average="macro", zero_division=0),
        "precision_binary": lambda: precision_score(y_true, y_pred, average="binary", zero_division=0),
        "recall_macro": lambda: recall_score(y_true, y_pred, average="macro", zero_division=0),
        "recall_binary": lambda: recall_score(y_true, y_pred, average="binary", zero_division=0),
        "cohen_kappa": lambda: cohen_kappa_score(y_true, y_pred),
    }

    if metric_names is None:
        metric_names = list(all_metrics.keys())

    results = {}
    for name in metric_names:
        if name in all_metrics:
            results[name] = float(all_metrics[name]())
        else:
            logger.warning(f"未知指标: {name}, 跳过")

    return results


def compute_classification_report(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    target_names: list[str] | None = None,
) -> str:
    """生成分类报告文本."""
    if target_names is None:
        n_classes = len(set(y_true) | set(y_pred))
        if n_classes <= 2:
            target_names = ["负例(0)", "正例(1)"]
        else:
            target_names = ["顶部反转", "正常", "底部反转"]
    return classification_report(y_true, y_pred, target_names=target_names, zero_division=0)


def compute_confusion_matrix(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> np.ndarray:
    """计算混淆矩阵."""
    return confusion_matrix(y_true, y_pred)
