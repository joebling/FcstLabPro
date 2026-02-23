#!/usr/bin/env python3
"""生产预测 — 使用已训练模型对最新数据做预测.

Usage:
    python scripts/predict.py --experiment <experiment_id>
    python scripts/predict.py --model experiments/<id>/model.joblib --config experiments/<id>/config.yaml
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import joblib
import numpy as np
import pandas as pd

from src.utils.logging import setup_logging
from src.data.loader import load_csv
from src.data.downloader import download_binance_klines
from src.features.builder import build_features, get_feature_columns
from src.experiment.config import load_experiment_config
from src.experiment.tracker_old import EXPERIMENTS_DIR


def main():
    parser = argparse.ArgumentParser(description="FcstLabPro 生产预测")
    parser.add_argument("--experiment", help="实验 ID（从 experiments/ 目录加载模型和配置）")
    parser.add_argument("--model", help="模型文件路径")
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument("--latest-days", type=int, default=300,
                        help="下载最近 N 天数据用于特征计算")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    setup_logging(level=args.log_level)

    # 确定模型和配置路径
    if args.experiment:
        exp_dir = EXPERIMENTS_DIR / args.experiment
        model_path = exp_dir / "model.joblib"
        config_path = exp_dir / "config.yaml"
    elif args.model and args.config:
        model_path = Path(args.model)
        config_path = Path(args.config)
    else:
        parser.error("请指定 --experiment 或同时指定 --model 和 --config")
        return

    if not model_path.exists():
        print(f"❌ 模型文件不存在: {model_path}")
        return

    # 加载配置和模型
    import yaml
    with open(config_path) as f:
        config = yaml.safe_load(f)

    model = joblib.load(model_path)

    # 加载或下载最新数据
    data_cfg = config["data"]
    data_path = data_cfg.get("path")
    if data_path and Path(data_path).exists():
        df = load_csv(data_path)
    else:
        print("📥 下载最新数据...")
        df = download_binance_klines(
            symbol=data_cfg.get("symbol", "BTCUSDT"),
            interval=data_cfg.get("interval", "1d"),
            start="2024-01-01",
        )

    # 特征工程
    feat_cfg = config["features"]
    df = build_features(df, feature_sets=feat_cfg["sets"])

    # 取最后一行做预测
    feature_cols = get_feature_columns(df)
    X_latest = df[feature_cols].iloc[[-1]].values

    pred = model.predict(X_latest)
    proba = model.predict_proba(X_latest)

    label_map = {0: "顶部反转 ⚠️", 1: "正常 ➡️", 2: "底部反转 🟢"}
    pred_label = int(pred[0])

    print(f"\n{'='*50}")
    print(f"📅 预测日期: {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"💰 当前价格: ${df['close'].iloc[-1]:,.2f}")
    print(f"🔮 预测结果: {label_map.get(pred_label, pred_label)}")
    print(f"📊 概率分布:")
    print(f"   顶部反转: {proba[0][0]:.2%}")
    print(f"   正常:     {proba[0][1]:.2%}")
    print(f"   底部反转: {proba[0][2]:.2%}")
    print(f"{'='*50}")

    # 保存预测结果
    result = {
        "date": str(df.index[-1].date()),
        "price": float(df["close"].iloc[-1]),
        "prediction": pred_label,
        "prediction_label": label_map.get(pred_label, str(pred_label)),
        "probabilities": {
            "top_reversal": float(proba[0][0]),
            "normal": float(proba[0][1]),
            "bottom_reversal": float(proba[0][2]),
        },
        "experiment_id": args.experiment or "custom",
    }
    print(f"\n{json.dumps(result, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
