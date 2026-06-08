"""回测引擎 — Walk-Forward 训练 + 评估."""

from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    test_idx: np.ndarray | None = None  # 全局行索引 (用于去重)


@dataclass
class BacktestResult:
    """完整回测结果."""
    folds: list[FoldResult] = field(default_factory=list)
    aggregate_metrics: dict[str, float] = field(default_factory=dict)
    all_y_true: np.ndarray | None = None
    all_y_pred: np.ndarray | None = None
    all_test_idx: np.ndarray | None = None  # 每个预测的全局行索引 (可能重复)
    last_model: BaseModel | None = None


def _dedup_by_index(test_idx, y_true, y_pred):
    """按全局行索引去重, 每个索引保留首次 (最早 fold) 预测。

    walk-forward 重叠 (oos_window>step) 时同一天会被多个 fold 预测。
    聚合指标必须用非重叠样本 (手册 §2.1), 否则同一样本被计多次。
    返回 (uniq_idx, y_true_dedup, y_pred_dedup), 按索引升序。
    """
    test_idx = np.asarray(test_idx)
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    # 稳定排序: 索引升序, 同索引保留原顺序 (最早 fold 在前)
    order = np.argsort(test_idx, kind="stable")
    si, st, sp = test_idx[order], y_true[order], y_pred[order]
    keep = np.concatenate(([True], si[1:] != si[:-1]))
    return si[keep], st[keep], sp[keep]


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
    purge_gap: int = 0,
    threshold_optimize: bool = False,
    threshold_metric: str = "f1",
    threshold_val_ratio: float = 0.15,
    calibrate: str = "none",  # "none" | "platt" | "isotonic"
    regime_weights: dict | None = None,  # {"bull": 1.5, "sideways": 0.5, "bear": 1.2}
    regime_feature_idx: int | None = None,  # 哪个特征是 regime indicator
    parallel_workers: int = 1,  # 并行 fold 数，1 为串行
    exp_dir: Path | None = None,  # 实验目录，用于保存 fold 结果
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
    purge_gap : int
        训练集与测试集之间的间隔天数（防止标签泄漏）。
        当标签使用 T 日前瞻窗口时，应设置 purge_gap >= T。
    threshold_optimize : bool
        是否在每个 fold 中优化概率阈值
    threshold_metric : str
        阈值优化目标指标
    threshold_val_ratio : float
        用于阈值优化的验证集比例 (从训练集尾部切出)

    Returns
    -------
    BacktestResult
    """
    folds = walk_forward_split(len(X), init_train, oos_window, step)

    # 并行执行
    if parallel_workers > 1:
        return _run_parallel(
            X=X, y=y,
            folds=folds,
            model_type=model_type,
            model_params=model_params,
            metric_names=metric_names,
            purge_gap=purge_gap,
            threshold_optimize=threshold_optimize,
            threshold_metric=threshold_metric,
            threshold_val_ratio=threshold_val_ratio,
            calibrate=calibrate,
            regime_weights=regime_weights,
            regime_feature_idx=regime_feature_idx,
            parallel_workers=parallel_workers,
            exp_dir=exp_dir,
        )

    # 串行执行（原有逻辑）
    result = BacktestResult()

    all_y_true = []
    all_y_pred = []
    all_test_idx = []
    importance_sum = None

    for fold in folds:
        # 应用 purge gap: 截断训练集尾部，避免标签泄漏
        train_end = fold.train_end - purge_gap if purge_gap > 0 else fold.train_end
        if train_end <= fold.train_start:
            continue
            
        X_train = X[fold.train_start:train_end]
        y_train = y[fold.train_start:train_end]
        X_test = X[fold.test_start:fold.test_end]
        y_test = y[fold.test_start:fold.test_end]

        # ---- 样本加权 (Regime-Specific Weighting) ----
        sample_weight = None
        if regime_weights and regime_feature_idx is not None:
            try:
                regime_values = X_train[:, regime_feature_idx]
                sample_weight = np.ones(len(regime_values))
                # regime_bull=1, regime_bear=-1, regime_sideways=0
                sample_weight[regime_values > 0] = regime_weights.get("bull", 1.0)   # Bull
                sample_weight[regime_values < 0] = regime_weights.get("bear", 1.0)    # Bear
                sample_weight[regime_values == 0] = regime_weights.get("sideways", 1.0)  # Sideways
                logger.info(f"  Fold {fold.fold_id}: RSW applied, weights={regime_weights}")
            except Exception as e:
                logger.warning(f"  RSW 应用失败: {e}")

        # 训练
        model = create_model(model_type, model_params)
        model.fit(X_train, y_train, sample_weight=sample_weight)

        # ---- 概率校准 ----
        calibration_info = None
        if calibrate != "none" and calibrate != "None":
            from src.evaluation.calibration import apply_calibration
            try:
                # 使用内部CV进行校准
                model = apply_calibration(model, X_train, y_train, method=calibrate, cv=3)
                calibration_info = {"method": calibrate}
                logger.info(f"  Fold {fold.fold_id}: 概率校准已应用 ({calibrate})")
            except Exception as e:
                logger.warning(f"  校准失败: {e}")

        # ---- 概率阈值优化 ----
        if threshold_optimize:
            from src.evaluation.threshold_optimizer import optimize_threshold, apply_threshold
            # 用训练集尾部作为验证集来选阈值
            val_size = max(int(len(X_train) * threshold_val_ratio), 50)
            X_val = X_train[-val_size:]
            y_val = y_train[-val_size:]
            try:
                val_proba = model.predict_proba(X_val)
                best_t, _ = optimize_threshold(y_val, val_proba, metric=threshold_metric)
                # 用优化后的阈值预测测试集
                test_proba = model.predict_proba(X_test)
                y_pred = apply_threshold(test_proba, best_t)
                logger.info(f"  Fold {fold.fold_id}: 优化阈值={best_t:.3f}")
            except Exception as e:
                logger.warning(f"  阈值优化失败，回退默认预测: {e}")
                y_pred = model.predict(X_test)
        else:
            # 预测
            y_pred = model.predict(X_test)

        # 对齐 y_test：序列模型会减少样本数量
        if hasattr(model, 'sequence_length'):
            seq_len = model.sequence_length
            if len(y_test) > len(y_pred):
                y_test = y_test[seq_len - 1:]
                logger.debug(f"  Fold {fold.fold_id}: 序列模型对齐 y_test ({len(y_test)} -> {len(y_pred)})")

        try:
            y_proba = model.predict_proba(X_test)
        except Exception:
            y_proba = None

        # 评估
        metrics = compute_metrics(y_test, y_pred, metric_names)

        # 特征重要性累加
        fi = model.feature_importance()
        if fi is not None:
            if importance_sum is None:
                importance_sum = fi.copy()
            else:
                importance_sum += fi

        # 计算全局行索引 (用于下游去重/对齐日期)。
        # walk-forward 重叠 (oos_window>step) 时同一索引会出现多次。
        _test_idx = np.arange(fold.test_start, fold.test_end)
        if len(_test_idx) > len(y_test):  # 序列模型截断对齐
            _test_idx = _test_idx[len(_test_idx) - len(y_test):]

        fold_result = FoldResult(
            fold_id=fold.fold_id,
            train_size=fold.train_end - fold.train_start,
            test_size=fold.test_end - fold.test_start,
            metrics=metrics,
            y_true=y_test,
            y_pred=y_pred,
            y_proba=y_proba,
            feature_importance=fi,
            test_idx=_test_idx,
        )
        result.folds.append(fold_result)
        all_y_true.append(y_test)
        all_y_pred.append(y_pred)
        all_test_idx.append(_test_idx)

        logger.info(f"Fold {fold.fold_id}: "
                     f"train={fold_result.train_size}, test={fold_result.test_size}, "
                     f"acc={metrics.get('accuracy', 0):.4f}")

    # 汇总 (按手册 §2.1: 聚合指标用非重叠样本, 重叠预测去重)
    _idx_all = np.concatenate(all_test_idx)
    _yt_all = np.concatenate(all_y_true)
    _yp_all = np.concatenate(all_y_pred)
    uniq_idx, yt_dedup, yp_dedup = _dedup_by_index(_idx_all, _yt_all, _yp_all)
    result.all_y_true = yt_dedup
    result.all_y_pred = yp_dedup
    result.all_test_idx = uniq_idx
    result.aggregate_metrics = compute_metrics(result.all_y_true, result.all_y_pred, metric_names)
    result.last_model = model  # 最后一个 fold 的模型

    logger.info(f"Walk-Forward 完成: {len(folds)} folds, "
                f"去重样本={len(result.all_y_true)} (原始 {len(_yt_all)}), "
                f"总体 acc={result.aggregate_metrics.get('accuracy', 0):.4f}")

    return result


def _run_parallel(
    X: np.ndarray,
    y: np.ndarray,
    folds: list[FoldSplit],
    model_type: str,
    model_params: dict,
    metric_names: list[str] | None,
    purge_gap: int,
    threshold_optimize: bool,
    threshold_metric: str,
    threshold_val_ratio: float,
    calibrate: str,
    regime_weights: dict | None,
    regime_feature_idx: int | None,
    parallel_workers: int,
    exp_dir: Path | None,
) -> BacktestResult:
    """并行执行 Walk-Forward folds.

    每个 fold 的结果保存到 folds/fold_XX/ 目录，最后合并结果。
    """
    logger.info(f"并行执行: {parallel_workers} workers, {len(folds)} folds")

    # 创建 folds 目录
    if exp_dir:
        folds_dir = exp_dir / "folds"
        folds_dir.mkdir(exist_ok=True)
    else:
        folds_dir = None

    # 并行执行
    all_fold_results = []
    all_y_true = []
    all_y_pred = []
    importance_sum = None

    # 使用 ThreadPoolExecutor 避免 pickle 问题
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
        # 提交所有 fold 任务
        future_to_fold = {}
        for fold in folds:
            future = executor.submit(
                _execute_single_fold,
                fold=fold,
                X=X, y=y,
                model_type=model_type,
                model_params=model_params,
                metric_names=metric_names,
                purge_gap=purge_gap,
                threshold_optimize=threshold_optimize,
                threshold_metric=threshold_metric,
                threshold_val_ratio=threshold_val_ratio,
                calibrate=calibrate,
                regime_weights=regime_weights,
                regime_feature_idx=regime_feature_idx,
                folds_dir=folds_dir,
            )
            future_to_fold[future] = fold

        # 收集结果
        for future in as_completed(future_to_fold):
            fold = future_to_fold[future]
            try:
                fold_result = future.result()
                all_fold_results.append(fold_result)

                # 收集用于汇总的数据
                all_y_true.append(fold_result.y_true)
                all_y_pred.append(fold_result.y_pred)

                if fold_result.feature_importance is not None:
                    if importance_sum is None:
                        importance_sum = fold_result.feature_importance.copy()
                    else:
                        importance_sum += fold_result.feature_importance

                logger.info(f"Fold {fold_result.fold_id}: "
                            f"train={fold_result.train_size}, test={fold_result.test_size}, "
                            f"acc={fold_result.metrics.get('accuracy', 0):.4f}")
            except Exception as e:
                logger.error(f"Fold {fold.fold_id} 执行失败: {e}")

    # 按 fold_id 排序
    all_fold_results.sort(key=lambda x: x.fold_id)

    # 汇总 (手册 §2.1: 聚合用非重叠样本, 重叠预测去重)
    # 从排序后的 folds 重建 (不依赖完成顺序, 保证索引对齐)
    result = BacktestResult()
    result.folds = all_fold_results
    _idx_all = np.concatenate([f.test_idx for f in all_fold_results])
    _yt_all = np.concatenate([f.y_true for f in all_fold_results])
    _yp_all = np.concatenate([f.y_pred for f in all_fold_results])
    uniq_idx, yt_dedup, yp_dedup = _dedup_by_index(_idx_all, _yt_all, _yp_all)
    result.all_y_true = yt_dedup
    result.all_y_pred = yp_dedup
    result.all_test_idx = uniq_idx
    result.aggregate_metrics = compute_metrics(result.all_y_true, result.all_y_pred, metric_names)

    logger.info(f"并行 Walk-Forward 完成: {len(all_fold_results)} folds, "
                f"去重样本={len(result.all_y_true)} (原始 {len(_yt_all)}), "
                f"总体 acc={result.aggregate_metrics.get('accuracy', 0):.4f}")

    # 合并 fold 结果到 CSV
    if folds_dir:
        _merge_fold_results(all_fold_results, folds_dir)

    return result


def _execute_single_fold(
    fold: FoldSplit,
    X: np.ndarray,
    y: np.ndarray,
    model_type: str,
    model_params: dict,
    metric_names: list[str] | None,
    purge_gap: int,
    threshold_optimize: bool,
    threshold_metric: str,
    threshold_val_ratio: float,
    calibrate: str,
    regime_weights: dict | None,
    regime_feature_idx: int | None,
    folds_dir: Path | None,
) -> FoldResult:
    """执行单个 fold 的训练和预测。

    结果保存到 folds/fold_XX/ 目录。
    """
    # 应用 purge gap
    train_end = fold.train_end - purge_gap if purge_gap > 0 else fold.train_end
    if train_end <= fold.train_start:
        raise ValueError(f"Fold {fold.fold_id}: train_end <= train_start")

    X_train = X[fold.train_start:train_end]
    y_train = y[fold.train_start:train_end]
    X_test = X[fold.test_start:fold.test_end]
    y_test = y[fold.test_start:fold.test_end]

    # 样本加权
    sample_weight = None
    if regime_weights and regime_feature_idx is not None:
        try:
            regime_values = X_train[:, regime_feature_idx]
            sample_weight = np.ones(len(regime_values))
            sample_weight[regime_values > 0] = regime_weights.get("bull", 1.0)
            sample_weight[regime_values < 0] = regime_weights.get("bear", 1.0)
            sample_weight[regime_values == 0] = regime_weights.get("sideways", 1.0)
        except Exception:
            pass

    # 训练
    model = create_model(model_type, model_params)
    model.fit(X_train, y_train, sample_weight=sample_weight)

    # 概率校准
    if calibrate != "none" and calibrate != "None":
        try:
            from src.evaluation.calibration import apply_calibration
            model = apply_calibration(model, X_train, y_train, method=calibrate, cv=3)
        except Exception:
            pass

    # 阈值优化
    if threshold_optimize:
        from src.evaluation.threshold_optimizer import optimize_threshold, apply_threshold
        val_size = max(int(len(X_train) * threshold_val_ratio), 50)
        X_val = X_train[-val_size:]
        y_val = y_train[-val_size:]
        try:
            val_proba = model.predict_proba(X_val)
            best_t, _ = optimize_threshold(y_val, val_proba, metric=threshold_metric)
            test_proba = model.predict_proba(X_test)
            y_pred = apply_threshold(test_proba, best_t)
        except Exception:
            y_pred = model.predict(X_test)
    else:
        y_pred = model.predict(X_test)

    # 确保 y_pred 是 1D 数组
    if hasattr(y_pred, 'shape') and len(y_pred.shape) > 1:
        y_pred = np.argmax(y_pred, axis=1)

    # 对齐 y_test
    if hasattr(model, 'sequence_length'):
        seq_len = model.sequence_length
        if len(y_test) > len(y_pred):
            y_test = y_test[seq_len - 1:]

    # 获取概率
    try:
        y_proba = model.predict_proba(X_test)
        # 取正类概率
        if hasattr(y_proba, 'shape') and len(y_proba.shape) > 1 and y_proba.shape[1] == 2:
            y_proba = y_proba[:, 1]
    except Exception:
        y_proba = None

    # 计算指标
    metrics = compute_metrics(y_test, y_pred, metric_names)

    # 特征重要性
    fi = model.feature_importance()

    # 创建 fold 目录并保存结果
    if folds_dir:
        fold_dir = folds_dir / f"fold_{fold.fold_id:02d}"
        fold_dir.mkdir(exist_ok=True)

        # 保存 metrics.json
        with open(fold_dir / "metrics.json", "w") as f:
            json.dump(metrics, f, indent=2)

        # 保存 predictions.csv
        preds_df = pd.DataFrame({
            "y_true": y_test,
            "y_pred": y_pred,
        })
        if y_proba is not None:
            preds_df["y_proba"] = y_proba
        preds_df.to_csv(fold_dir / "predictions.csv", index=False)

    _test_idx = np.arange(fold.test_start, fold.test_end)
    if len(_test_idx) > len(y_test):  # 序列模型截断对齐
        _test_idx = _test_idx[len(_test_idx) - len(y_test):]

    return FoldResult(
        fold_id=fold.fold_id,
        train_size=fold.train_end - fold.train_start,
        test_size=fold.test_end - fold.test_start,
        metrics=metrics,
        y_true=y_test,
        y_pred=y_pred,
        y_proba=y_proba,
        feature_importance=fi,
        test_idx=_test_idx,
    )


def _merge_fold_results(folds: list[FoldResult], folds_dir: Path):
    """合并所有 fold 结果到 merged_metrics.csv."""
    rows = []
    for fold in folds:
        row = {
            "fold_id": fold.fold_id,
            "train_size": fold.train_size,
            "test_size": fold.test_size,
        }
        row.update(fold.metrics)
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(folds_dir.parent / "merged_metrics.csv", index=False)
    logger.info(f"已合并 {len(rows)} 个 fold 结果到 merged_metrics.csv")
