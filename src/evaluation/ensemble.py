"""组合模型评估器 — Bull/Bear 硬切策略."""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.evaluation.backtest import run_walk_forward, BacktestResult

logger = logging.getLogger(__name__)


@dataclass
class EnsembleResult:
    """组合模型结果."""
    bull_result: BacktestResult
    bear_result: BacktestResult
    combined_metrics: dict


def run_ensemble_evaluation(
    df: pd.DataFrame,
    bull_config: dict,
    bear_config: dict,
    init_train: int = 1500,
    oos_window: int = 63,
    step: int = 21,
    metric_names: list[str] | None = None,
) -> EnsembleResult:
    """运行组合模型评估.

    逻辑:
    - Price > 200MA → 使用 Bull 模型
    - Price < 200MA → 使用 Bear 模型

    Parameters
    ----------
    df : pd.DataFrame
        包含 close, high, low 等列的数据
    bull_config : dict
        Bull 模型配置 (特征集, 标签配置等)
    bear_config : dict
        Bear 模型配置
    init_train, oos_window, step : int
        Walk-Forward 参数

    Returns
    -------
    EnsembleResult
        组合模型结果
    """
    from src.features.builder import build_features
    from src.labels.registry import get_label_strategy

    # 计算 200MA
    sma_200 = df["close"].rolling(200).mean()
    df["regime_bull"] = (df["close"] > sma_200).astype(int)

    # 构建 Bull 特征和标签
    logger.info("构建 Bull 模型数据...")
    bull_df = df.copy()
    bull_feature_sets = bull_config.get("feature_sets", [
        "technical", "volume", "flow", "market_structure", "external_fgi", "regime"
    ])
    bull_df = build_features(bull_df, bull_feature_sets, drop_na_method="ffill_then_drop")

    # Bull 标签 (reversal, 预测底部反转)
    label_func = get_label_strategy("reversal")
    bull_label_cfg = bull_config.get("label", {})
    bull_df["label"] = label_func(
        bull_df,
        T=bull_label_cfg.get("T", 21),
        X=bull_label_cfg.get("X", 0.05),
    )

    # 应用标签映射: 2 (底部反转) -> 1, 其他 -> 0
    label_map = bull_label_cfg.get("map", {0: 0, 1: 0, 2: 1})
    bull_df["label"] = bull_df["label"].map(label_map).fillna(0).astype(int)

    # 构建 Bear 特征和标签
    logger.info("构建 Bear 模型数据...")
    bear_df = df.copy()
    bear_feature_sets = bear_config.get("feature_sets", [
        "technical", "volume", "flow", "market_structure", "external_fgi"
    ])
    bear_df = build_features(bear_df, bear_feature_sets, drop_na_method="ffill_then_drop")

    # Bear 标签 (reversal, 预测顶部反转)
    bear_label_cfg = bear_config.get("label", {})
    bear_df["label"] = label_func(
        bear_df,
        T=bear_label_cfg.get("T", 28),
        X=bear_label_cfg.get("X", 0.05),
    )

    # 应用标签映射: 0 (顶部反转) -> 1, 其他 -> 0
    label_map = bear_label_cfg.get("map", {0: 1, 1: 0, 2: 0})
    bear_df["label"] = bear_df["label"].map(label_map).fillna(0).astype(int)

    # 获取共同的有效索引
    valid_idx = bull_df.dropna(subset=["label"]).index.intersection(
        bear_df.dropna(subset=["label"]).index
    )

    bull_df = bull_df.loc[valid_idx]
    bear_df = bear_df.loc[valid_idx]
    regime = df.loc[valid_idx, "regime_bull"].values

    # 准备特征和标签
    feature_cols_bull = [c for c in bull_df.columns if c not in ["label", "open_time", "close_time"]]
    feature_cols_bear = [c for c in bear_df.columns if c not in ["label", "open_time", "close_time"]]

    # 找共同特征
    common_features = list(set(feature_cols_bull) & set(feature_cols_bear))
    logger.info(f"共同特征数: {len(common_features)}")

    X_bull = bull_df[common_features].values
    y_bull = bull_df["label"].values
    X_bear = bear_df[common_features].values
    y_bear = bear_df["label"].values

    # 运行 Bull Walk-Forward
    logger.info("运行 Bull 模型 Walk-Forward...")
    from src.models.registry import create_model

    bull_model_type = bull_config.get("model_type", "lightgbm")
    bull_model_params = bull_config.get("model_params", {})

    bull_result = run_walk_forward(
        X_bull, y_bull, common_features,
        bull_model_type, bull_model_params,
        init_train=init_train, oos_window=oos_window, step=step,
        metric_names=metric_names,
    )

    # 运行 Bear Walk-Forward
    logger.info("运行 Bear 模型 Walk-Forward...")
    bear_model_type = bear_config.get("model_type", "lightgbm")
    bear_model_params = bear_config.get("model_params", {})

    bear_result = run_walk_forward(
        X_bear, y_bear, common_features,
        bear_model_type, bear_model_params,
        init_train=init_train, oos_window=oos_window, step=step,
        metric_names=metric_names,
    )

    # 组合预测
    logger.info("组合 Bull/Bear 预测...")

    # 获取测试集索引
    from src.data.splitter import walk_forward_split
    folds = walk_forward_split(len(X_bull), init_train, oos_window, step)

    all_y_true = []
    all_y_pred = []
    all_regime = []

    for fold in folds:
        test_start = fold.test_start
        test_end = fold.test_end

        # Bull 预测
        bull_pred = bull_result.folds[fold.fold_id].y_pred if fold.fold_id < len(bull_result.folds) else None
        # Bear 预测
        bear_pred = bear_result.folds[fold.fold_id].y_pred if fold.fold_id < len(bear_result.folds) else None

        if bull_pred is None or bear_pred is None:
            continue

        # 硬切: Bull 市场用 Bull 预测, Bear 市场用 Bear 预测
        test_regime = regime[test_start:test_end]

        combined_pred = np.where(test_regime == 1, bull_pred, bear_pred)
        combined_true = y_bull[test_start:test_end]

        all_y_true.append(combined_true)
        all_y_pred.append(combined_pred)
        all_regime.append(test_regime)

    all_y_true = np.concatenate(all_y_true)
    all_y_pred = np.concatenate(all_y_pred)
    all_regime = np.concatenate(all_regime)

    # 计算组合指标
    from src.evaluation.metrics import compute_metrics
    combined_metrics = compute_metrics(all_y_true, all_y_pred, metric_names)

    # 统计
    bull_period = all_regime == 1
    bear_period = all_regime == 0

    logger.info(f"组合结果: 总样本={len(all_y_true)}, Bull区={bull_period.sum()}, Bear区={bear_period.sum()}")
    logger.info(f"组合 Kappa: {combined_metrics.get('cohen_kappa', 0):.4f}")

    return EnsembleResult(
        bull_result=bull_result,
        bear_result=bear_result,
        combined_metrics=combined_metrics,
    )
