"""组合模型实验运行器."""

import json
import logging
import time
from pathlib import Path

import pandas as pd

# 触发标签策略注册
import src.labels.reversal  # noqa: F401
import src.labels.directional  # noqa: F401

from src.data.loader import load_csv
from src.experiment.tracker import create_experiment_dir, generate_experiment_id, save_meta, update_registry
from src.evaluation.ensemble import run_ensemble_evaluation
from src.evaluation.metrics import compute_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run_ensemble_experiment(
    data_path: str,
    start: str = None,
    end: str = None,
    output_prefix: str = "ensemble",
):
    """运行组合模型实验."""

    # 加载数据
    logger.info(f"加载数据: {data_path}")
    df = load_csv(data_path)

    # 过滤日期
    if start:
        df = df[df.index >= start]
    if end:
        df = df[df.index <= end]

    logger.info(f"数据加载完成: {len(df)} 条记录")

    # Bull 模型配置 (v15)
    bull_config = {
        "feature_sets": ["technical", "volume", "flow", "market_structure", "external_fgi", "regime"],
        "label": {"strategy": "reversal", "T": 21, "X": 0.05, "map": {0: 0, 1: 0, 2: 1}},
        "model_type": "lightgbm",
        "model_params": {
            "n_estimators": 500,
            "max_depth": 6,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "random_state": 42,
            "verbose": -1,
        },
    }

    # Bear 模型配置 (v13)
    bear_config = {
        "feature_sets": ["technical", "volume", "flow", "market_structure", "external_fgi"],
        "label": {"strategy": "reversal", "T": 28, "X": 0.05, "map": {0: 1, 1: 0, 2: 0}},
        "model_type": "lightgbm",
        "model_params": {
            "n_estimators": 500,
            "max_depth": 6,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "random_state": 42,
            "verbose": -1,
        },
    }

    # 运行组合评估
    t_start = time.time()
    result = run_ensemble_evaluation(
        df=df,
        bull_config=bull_config,
        bear_config=bear_config,
        init_train=1500,
        oos_window=63,
        step=21,
        metric_names=["accuracy", "f1_binary", "precision_binary", "recall_binary", "f1_macro", "cohen_kappa"],
    )
    duration = time.time() - t_start

    # 打印结果
    logger.info("=" * 60)
    logger.info("组合模型实验完成!")
    logger.info(f"耗时: {duration:.1f}s")
    logger.info(f"Bull Kappa: {result.bull_result.aggregate_metrics.get('cohen_kappa', 0):.4f}")
    logger.info(f"Bear Kappa: {result.bear_result.aggregate_metrics.get('cohen_kappa', 0):.4f}")
    logger.info(f"组合 Kappa: {result.combined_metrics.get('cohen_kappa', 0):.4f}")
    logger.info("=" * 60)

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/raw/btc_binance_BTCUSDT_1d.csv")
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default="2025-12-31")
    args = parser.parse_args()

    run_ensemble_experiment(args.data, args.start, args.end)
