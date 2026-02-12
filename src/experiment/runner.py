"""实验运行器 — 串联完整实验流程."""

import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns
from src.labels.registry import get_label_strategy
from src.evaluation.backtest import run_walk_forward
from src.evaluation.metrics import compute_classification_report, compute_confusion_matrix
from src.experiment.config import load_experiment_config, apply_overrides, save_config
from src.experiment.tracker import (
    generate_experiment_id, create_experiment_dir,
    build_meta, save_meta, update_registry,
)
from src.experiment.reporter import generate_experiment_report

# 触发标签策略注册
import src.labels.reversal  # noqa: F401

logger = logging.getLogger(__name__)


def run_experiment(
    config_path: str | Path,
    overrides: list[str] | None = None,
) -> str:
    """运行一次完整实验.

    Parameters
    ----------
    config_path : str | Path
        实验配置 YAML 文件路径
    overrides : list[str] | None
        命令行参数覆盖, 如 ["label.T=21", "label.X=0.10"]

    Returns
    -------
    str
        实验 ID
    """
    t_start = time.time()

    # ========== 1. 加载配置 ==========
    config = load_experiment_config(config_path)
    if overrides:
        config = apply_overrides(config, overrides)

    experiment_id = generate_experiment_id(config)
    category = config.get("experiment", {}).get("category", "default")
    exp_dir = create_experiment_dir(experiment_id, category=category)

    # 保存配置快照
    save_config(config, exp_dir / "config.yaml")

    # 元信息
    meta = build_meta(config, experiment_id)
    save_meta(meta, exp_dir)

    logger.info(f"{'='*60}")
    logger.info(f"实验开始: {experiment_id}")
    logger.info(f"{'='*60}")

    try:
        # ========== 2. 加载数据 ==========
        data_cfg = config["data"]
        data_path = data_cfg.get("path")
        if data_path is None:
            raise ValueError("请在配置中指定 data.path 或先下载数据")
        df = load_csv(data_path)

        # ========== 3. 特征工程 ==========
        feat_cfg = config["features"]
        df = build_features(
            df,
            feature_sets=feat_cfg["sets"],
            drop_na_method=feat_cfg.get("drop_na_method", "ffill_then_drop"),
        )

        # ========== 4. 标签生成 ==========
        label_cfg = config["label"]
        label_func = get_label_strategy(label_cfg["strategy"])
        labels = label_func(df, T=label_cfg["T"], X=label_cfg["X"])
        df["label"] = labels

        # 丢弃无标签的行
        df = df.dropna(subset=["label"])
        df["label"] = df["label"].astype(int)

        # 准备特征矩阵
        feature_cols = get_feature_columns(df)
        X = df[feature_cols].values
        y = df["label"].values

        logger.info(f"数据准备完成: X.shape={X.shape}, y.shape={y.shape}")
        logger.info(f"标签分布: {pd.Series(y).value_counts().sort_index().to_dict()}")

        # ========== 5. Walk-Forward 回测 ==========
        eval_cfg = config["evaluation"]
        model_cfg = config["model"]

        # 设置随机种子
        seed = config.get("seed", 42)
        np.random.seed(seed)

        bt_result = run_walk_forward(
            X=X, y=y,
            feature_names=feature_cols,
            model_type=model_cfg["type"],
            model_params=model_cfg.get("params", {}),
            init_train=eval_cfg.get("init_train", 1500),
            oos_window=eval_cfg.get("oos_window", 63),
            step=eval_cfg.get("step", 21),
            metric_names=eval_cfg.get("metrics"),
        )

        # ========== 6. 保存产物 ==========
        # 6a. 汇总指标
        with open(exp_dir / "metrics.json", "w") as f:
            json.dump(bt_result.aggregate_metrics, f, indent=2)

        # 6b. Fold 指标
        fold_rows = []
        for fr in bt_result.folds:
            row = {"fold_id": fr.fold_id, "train_size": fr.train_size, "test_size": fr.test_size}
            row.update(fr.metrics)
            fold_rows.append(row)
        fold_metrics_df = pd.DataFrame(fold_rows)
        fold_metrics_df.to_csv(exp_dir / "fold_metrics.csv", index=False)

        # 6c. 特征重要性 (使用最后一个 fold 的模型)
        fi = bt_result.last_model.feature_importance()
        fi_df = pd.DataFrame({"feature": feature_cols, "importance": fi})
        fi_df = fi_df.sort_values("importance", ascending=False).reset_index(drop=True)
        fi_df.to_csv(exp_dir / "feature_importance.csv", index=False)

        # 6d. 模型 (最后一个 fold)
        joblib.dump(bt_result.last_model.model, exp_dir / "model.joblib")

        # 6e. 预测结果
        pred_df = pd.DataFrame({
            "y_true": bt_result.all_y_true,
            "y_pred": bt_result.all_y_pred,
        })
        pred_df.to_csv(exp_dir / "predictions.csv", index=False)

        # ========== 7. 生成报告 ==========
        cls_report = compute_classification_report(bt_result.all_y_true, bt_result.all_y_pred)
        cm = compute_confusion_matrix(bt_result.all_y_true, bt_result.all_y_pred)

        generate_experiment_report(
            experiment_id=experiment_id,
            config=config,
            meta=meta,
            aggregate_metrics=bt_result.aggregate_metrics,
            fold_metrics_df=fold_metrics_df,
            feature_importance_df=fi_df,
            classification_report_text=cls_report,
            confusion_mat=cm,
            output_path=exp_dir / "report.md",
        )

        # ========== 8. 更新元信息和注册表 ==========
        duration = time.time() - t_start
        meta["status"] = "completed"
        meta["duration_seconds"] = round(duration, 2)
        meta["aggregate_metrics"] = bt_result.aggregate_metrics
        save_meta(meta, exp_dir)
        update_registry(experiment_id, meta)

        logger.info(f"{'='*60}")
        logger.info(f"实验完成: {experiment_id}")
        logger.info(f"耗时: {duration:.1f}s")
        logger.info(f"汇总指标: {bt_result.aggregate_metrics}")
        logger.info(f"产物目录: {exp_dir}")
        logger.info(f"{'='*60}")

    except Exception as e:
        duration = time.time() - t_start
        meta["status"] = "failed"
        meta["duration_seconds"] = round(duration, 2)
        meta["error"] = str(e)
        save_meta(meta, exp_dir)
        update_registry(experiment_id, meta)
        logger.error(f"实验失败: {experiment_id}, 错误: {e}")
        raise

    return experiment_id
