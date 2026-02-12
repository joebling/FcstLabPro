"""回测引擎 — Walk-Forward 训练 + 评估."""

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.data.splitter import walk_forward_split, FoldSplit
from src.models.base import BaseModel
from src.models.registry import create_model
from src.evaluation.metrics import compute_metrics

logger = logging.getLogger(__name__)


@dataclass
class FoldResult:
    """单个 fold 的结果."""
    fold_id: int
    train_size: int
    test_size: int
    metrics: dict[str, float]
    y_true: np.ndarray
    y_pred: np.ndarray
    y_proba: np.ndarray | None = None
    feature_importance: np.ndarray | None = None


@dataclass
class BacktestResult:
    """完整回测结果."""
    folds: list[FoldResult] = field(default_factory=list)
    aggregate_metrics: dict[str, float] = field(default_factory=dict)
    all_y_true: np.ndarray | None = None
    all_y_pred: np.ndarray | None = None
    last_model: BaseModel | None = None


def run_walk_forward(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: list[str],
    model_type: str,
    model_params: dict,
    init_train: int = 1500,
    oos_window: int = 63,
    step: int = 21,
    metric_names: list[str] | None = None,
) -> BacktestResult:
    """执行 Walk-Forward 回测.

    Parameters
    ----------
    X : np.ndarray
        特征矩阵
    y : np.ndarray
        标签
    feature_names : list[str]
        特征名列表
    model_type : str
        模型类型名称
    model_params : dict
        模型参数
    init_train, oos_window, step : int
        Walk-Forward 参数
    metric_names : list[str] | None
        要计算的评估指标

    Returns
    -------
    BacktestResult
    """
    folds = walk_forward_split(len(X), init_train, oos_window, step)
    result = BacktestResult()

    all_y_true = []
    all_y_pred = []
    importance_sum = None

    for fold in folds:
        X_train = X[fold.train_start:fold.train_end]
        y_train = y[fold.train_start:fold.train_end]
        X_test = X[fold.test_start:fold.test_end]
        y_test = y[fold.test_start:fold.test_end]

        # 训练
        model = create_model(model_type, model_params)
        model.fit(X_train, y_train)

        # 预测
        y_pred = model.predict(X_test)
        try:
            y_proba = model.predict_proba(X_test)
        except Exception:
            y_proba = None

        # 评估
        metrics = compute_metrics(y_test, y_pred, metric_names)

        # 特征重要性累加
        fi = model.feature_importance()
        if importance_sum is None:
            importance_sum = fi.copy()
        else:
            importance_sum += fi

        fold_result = FoldResult(
            fold_id=fold.fold_id,
            train_size=fold.train_end - fold.train_start,
            test_size=fold.test_end - fold.test_start,
            metrics=metrics,
            y_true=y_test,
            y_pred=y_pred,
            y_proba=y_proba,
            feature_importance=fi,
        )
        result.folds.append(fold_result)
        all_y_true.append(y_test)
        all_y_pred.append(y_pred)

        logger.info(f"Fold {fold.fold_id}: "
                     f"train={fold_result.train_size}, test={fold_result.test_size}, "
                     f"acc={metrics.get('accuracy', 0):.4f}")

    # 汇总
    result.all_y_true = np.concatenate(all_y_true)
    result.all_y_pred = np.concatenate(all_y_pred)
    result.aggregate_metrics = compute_metrics(result.all_y_true, result.all_y_pred, metric_names)
    result.last_model = model  # 最后一个 fold 的模型

    logger.info(f"Walk-Forward 完成: {len(folds)} folds, "
                f"总样本={len(result.all_y_true)}, "
                f"总体 acc={result.aggregate_metrics.get('accuracy', 0):.4f}")

    return result
