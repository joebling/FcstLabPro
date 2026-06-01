"""实验运行器 — 串联完整实验流程."""

from __future__ import annotations

import inspect
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
from src.experiment.validation import validate_experiment_config
from src.experiment.tracker import (
    generate_experiment_id, create_experiment_dir,
    build_meta, save_meta, update_registry,
)
from src.experiment.reporter import generate_experiment_report

# 触发标签策略注册
import src.labels.reversal  # noqa: F401
import src.labels.directional  # noqa: F401
import src.labels.triple_barrier  # noqa: F401
import src.labels.return_rate  # noqa: F401
import src.labels.pump_dump  # noqa: F401
import src.labels.triple_barrier_simple  # noqa: F401
import src.labels.dip_recovery_v2  # noqa: F401
import src.labels.directional_filtered  # noqa: F401

# 触发新模型注册（可选模型缺依赖时静默跳过）
import importlib as _importlib
for _mod in [
    "src.models.stacking",
    "src.models.lgbm_regressor",
    "src.models.lstm_classifier",
    "src.models.gru_classifier",
    "src.models.transformer_classifier",
    "src.models.tft_classifier",
    "src.models.patchtst_classifier",
]:
    try:
        _importlib.import_module(_mod)
    except Exception:
        pass

logger = logging.getLogger(__name__)


def run_experiment(
    config_path: str | Path,
    overrides: list[str] | None = None,
    *,
    overwrite: bool = False,
) -> str:
    """运行一次完整实验.

    Parameters
    ----------
    config_path : str | Path
        实验配置 YAML 文件路径
    overrides : list[str] | None
        命令行参数覆盖, 如 ["label.T=21", "label.X=0.10"]
    overwrite : bool
        True 时使用实验名作为目录名并覆盖已有目录。

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

    # 硬校验: Non-overlapping / purge / walk-forward / seed (机构手册 §2)
    validate_experiment_config(config)

    experiment_id = generate_experiment_id(config, overwrite=overwrite)
    category = config.get("experiment", {}).get("category", "default")
    exp_dir = create_experiment_dir(experiment_id, category=category, overwrite=overwrite)

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
        df = load_csv(
            data_path,
            start=data_cfg.get("start"),
            end=data_cfg.get("end"),
            expected_sha256=data_cfg.get("expected_sha256"),
            expected_effective_rows=data_cfg.get("expected_effective_rows"),
        )

        # ========== 3. 特征工程 ==========
        feat_cfg = config["features"]
        df = build_features(
            df,
            feature_sets=feat_cfg["sets"],
            drop_na_method=feat_cfg.get("drop_na_method", "ffill_then_drop"),
            drop_features=feat_cfg.get("drop_features"),
            smoothing=feat_cfg.get("smoothing"),
        )

        # ========== 4. 标签生成 ==========
        label_cfg = config["label"]
        label_func = get_label_strategy(label_cfg["strategy"])
        
        # 构建标签函数的参数：只传递函数签名中接受的参数
        _label_meta_keys = {"strategy", "map"}
        _accepted = set(inspect.signature(label_func).parameters.keys()) - {"df"}
        label_kwargs = {
            k: v for k, v in label_cfg.items()
            if k not in _label_meta_keys and k in _accepted
        }
        _unknown = {k for k in label_cfg if k not in _label_meta_keys and k not in _accepted}
        if _unknown:
            logger.warning(f"⚠️ Label 配置中存在未识别的参数: {_unknown}，已被忽略。"
                           f"函数 '{label_cfg['strategy']}' 接受的参数: {_accepted}")
        
        labels = label_func(df, **label_kwargs)
        
        # 处理标签映射 (Label Mapping)
        # 例如: 将三分类 [0, 1, 2] 映射为二分类 [0, 0, 1] 用于多头预测
        if "map" in label_cfg and label_cfg["map"]:
            logger.info(f"应用标签映射: {label_cfg['map']}")
            # key in yaml might be int or str, ensure consistency
            mapping = {int(k): int(v) for k, v in label_cfg["map"].items()}
            labels = labels.map(mapping)
            
        df["label"] = labels

        # 丢弃无标签的行
        df = df.dropna(subset=["label"])
        df["label"] = df["label"].astype(int)

        # 准备特征矩阵
        feature_cols = get_feature_columns(df)
        
        # ========== 5. Walk-Forward 回测 ==========
        eval_cfg = config["evaluation"]
        model_cfg = config["model"]
        
        # ========== 4b. 特征选择（可选）==========
        feat_select_cfg = feat_cfg.get("selection", {})
        top_n = feat_select_cfg.get("top_n", 0)
        
        if top_n > 0 and top_n < len(feature_cols):
            logger.info(f"执行特征预筛选: 从 {len(feature_cols)} 个特征中选 Top-{top_n}")
            from src.models.registry import create_model as _create
            
            # 用前 init_train 个样本快速训练一个模型评估特征重要性
            _init = min(eval_cfg.get("init_train", 1500), len(df) - 100)
            _X_pre = df[feature_cols].values[:_init]
            _y_pre = df["label"].values[:_init]
            _m = _create(model_cfg["type"], model_cfg.get("params", {}))
            _m.fit(_X_pre, _y_pre)
            _fi = _m.feature_importance()
            _top_idx = np.argsort(_fi)[::-1][:top_n]
            feature_cols = [feature_cols[i] for i in sorted(_top_idx)]
            logger.info(f"特征筛选完成: 保留 {len(feature_cols)} 个特征")
        
        X = df[feature_cols].values
        y = df["label"].values

        logger.info(f"数据准备完成: X.shape={X.shape}, y.shape={y.shape}")
        logger.info(f"标签分布: {pd.Series(y).value_counts().sort_index().to_dict()}")

        # 设置随机种子
        seed = config.get("seed", 42)
        np.random.seed(seed)

        # 获取 regime feature 索引
        regime_feature_idx = None
        regime_weights = eval_cfg.get("regime_weight")
        if regime_weights:
            # 优先查找 regime_bull (1=Bull, 0=Bear)
            target_features = ["regime_bull", "regime_bear", "regime_sideways"]
            for target in target_features:
                for i, col in enumerate(feature_cols):
                    if col == target:
                        regime_feature_idx = i
                        logger.info(f"RSW: 使用特征 '{col}' (index={i}) 作为 regime indicator")
                        break
                if regime_feature_idx is not None:
                    break
            if regime_feature_idx is None:
                logger.warning("RSW: 未找到 regime 特征，跳过样本加权")

        bt_result = run_walk_forward(
            X=X, y=y,
            feature_names=feature_cols,
            model_type=model_cfg["type"],
            model_params=model_cfg.get("params", {}),
            init_train=eval_cfg.get("init_train", 1500),
            oos_window=eval_cfg.get("oos_window", 63),
            step=eval_cfg.get("step", 21),
            metric_names=eval_cfg.get("metrics"),
            purge_gap=eval_cfg.get("purge_gap", 0),
            threshold_optimize=eval_cfg.get("threshold_optimize", False),
            threshold_metric=eval_cfg.get("threshold_metric", "f1"),
            threshold_val_ratio=eval_cfg.get("threshold_val_ratio", 0.15),
            calibrate=eval_cfg.get("calibrate", "none"),
            regime_weights=regime_weights,
            regime_feature_idx=regime_feature_idx,
            parallel_workers=eval_cfg.get("parallel_workers", 1),
            exp_dir=exp_dir,
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
        fi_df = None
        if bt_result.last_model is not None:
            fi = bt_result.last_model.feature_importance()
            if fi is not None:
                fi_df = pd.DataFrame({"feature": feature_cols, "importance": fi})
                fi_df = fi_df.sort_values("importance", ascending=False).reset_index(drop=True)
                fi_df.to_csv(exp_dir / "feature_importance.csv", index=False)
        else:
            # 并行模式下 last_model 为 None
            logger.info("并行模式跳过特征重要性保存")

        # 6c-bis. 特征列名快照 (按训练时的真实列序保存)
        # 详见 docs/specs/data_pipeline.md §10 P0 技术债:
        # model.joblib 内部只记 Column_0..N, 需额外产物保护推理时的列对齐。
        import hashlib as _hashlib
        _cols_payload = ",".join(feature_cols)
        _feature_cols_doc = {
            "version": 1,
            "n_features": len(feature_cols),
            "feature_cols": list(feature_cols),
            "sha256": _hashlib.sha256(_cols_payload.encode("utf-8")).hexdigest(),
            "generated_by": "src.experiment.runner.run_experiment",
        }
        with open(exp_dir / "feature_cols.json", "w") as _f:
            json.dump(_feature_cols_doc, _f, indent=2, ensure_ascii=False)
        logger.info(f"特征列名快照已保存: feature_cols.json ({len(feature_cols)} 列)")

        # 6d. 模型 (最后一个 fold)
        if bt_result.last_model is not None:
            joblib.dump(bt_result.last_model.model, exp_dir / "model.joblib")
        else:
            logger.info("并行模式跳过模型保存")

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
            n_features=len(feature_cols),
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