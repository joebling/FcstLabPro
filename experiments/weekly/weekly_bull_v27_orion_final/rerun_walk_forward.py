import sys
import os

sys.path.insert(0, os.path.abspath('.'))

import json
import logging
import numpy as np
import pandas as pd
import joblib
import yaml
from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns
from src.labels.registry import get_label_strategy
from src.evaluation.backtest import run_walk_forward
from src.experiment.config import load_experiment_config

import src.labels.reversal

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    print("="*80)
    print("重新运行 Orion-BiX v27 Walk-Forward 回测")
    print("="*80)
    
    config_path = "experiments/weekly/weekly_bull_v27_orion_final/config.yaml"
    exp_dir = "experiments/weekly/weekly_bull_v27_orion_final"
    
    logger.info(f"加载配置: {config_path}")
    config = load_experiment_config(config_path)
    
    # ========== 1. 加载数据 ==========
    data_cfg = config["data"]
    data_path = data_cfg.get("path")
    logger.info(f"加载数据: {data_path}")
    df = load_csv(data_path)
    
    # ========== 2. 特征工程 ==========
    feat_cfg = config["features"]
    logger.info(f"构建特征: {feat_cfg['sets']}")
    df = build_features(
        df,
        feature_sets=feat_cfg["sets"],
        drop_na_method=feat_cfg.get("drop_na_method", "ffill_then_drop"),
    )
    
    # ========== 3. 标签生成 ==========
    label_cfg = config["label"]
    label_func = get_label_strategy(label_cfg["strategy"])
    logger.info(f"生成标签: {label_cfg['strategy']} T={label_cfg['T']} X={label_cfg['X']}")
    
    label_kwargs = {"T": label_cfg["T"], "X": label_cfg["X"]}
    labels = label_func(df, **label_kwargs)
    
    if "map" in label_cfg and label_cfg["map"]:
        logger.info(f"应用标签映射: {label_cfg['map']}")
        mapping = {int(k): int(v) for k, v in label_cfg["map"].items()}
        labels = labels.map(mapping)
    
    df["label"] = labels
    df = df.dropna(subset=["label"])
    df["label"] = df["label"].astype(int)
    
    feature_cols = get_feature_columns(df)
    X = df[feature_cols].values
    y = df["label"].values
    
    logger.info(f"数据准备完成: X.shape={X.shape}, y.shape={y.shape}")
    logger.info(f"标签分布: {pd.Series(y).value_counts().sort_index().to_dict()}")
    
    # ========== 4. Walk-Forward 回测 ==========
    eval_cfg = config["evaluation"]
    model_cfg = config["model"]
    seed = config.get("seed", 42)
    np.random.seed(seed)
    
    logger.info(f"运行 Walk-Forward 回测...")
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
    )
    
    # ========== 5. 保存产物 ==========
    logger.info(f"保存回测结果到: {exp_dir}")
    
    with open(os.path.join(exp_dir, "metrics.json"), "w") as f:
        json.dump(bt_result.aggregate_metrics, f, indent=2)
    
    fold_rows = []
    for fr in bt_result.folds:
        row = {"fold_id": fr.fold_id, "train_size": fr.train_size, "test_size": fr.test_size}
        row.update(fr.metrics)
        fold_rows.append(row)
    fold_metrics_df = pd.DataFrame(fold_rows)
    fold_metrics_df.to_csv(os.path.join(exp_dir, "fold_metrics.csv"), index=False)
    
    pred_df = pd.DataFrame({
        "y_true": bt_result.all_y_true,
        "y_pred": bt_result.all_y_pred,
    })
    pred_df.to_csv(os.path.join(exp_dir, "predictions.csv"), index=False)
    
    logger.info(f"预测结果已保存: {os.path.join(exp_dir, 'predictions.csv')}")
    
    print("\n" + "="*80)
    print("回测完成！")
    print("="*80)
    print(f"\n汇总指标:")
    for k, v in bt_result.aggregate_metrics.items():
        print(f"  {k}: {v:.4f}")
    
    print(f"\nFold 数: {len(bt_result.folds)}")
    print(f"预测样本数: {len(bt_result.all_y_true)}")

if __name__ == '__main__':
    main()
