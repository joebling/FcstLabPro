#!/usr/bin/env python3
"""E1 vs E8 Paper Trading 并行运行脚本.

同时运行 E1 (生产) 和 E8 (touch label) 模型的信号生成，
对比输出，方便 paper trading 验证。

Usage:
    python3.10 scripts/paper_trading_e1_vs_e8.py
    python3.10 scripts/paper_trading_e1_vs_e8.py --download  # 拉取最新数据
    python3.10 scripts/paper_trading_e1_vs_e8.py --save       # 保存信号到 JSON
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M",
)
logger = logging.getLogger("paper_trading")

# ---------------------------------------------------------------------------
# Model configs
# ---------------------------------------------------------------------------

MODELS = {
    "E1-conservative": {
        "model": PROJECT_ROOT / "models/production/e1-conservative/model.joblib",
        "config": PROJECT_ROOT / "models/production/e1-conservative/config.yaml",
        "state": PROJECT_ROOT / "data/live/paper_state_e1.json",
        "description": "生产模型 (directional_filtered, 止盈+regime)",
    },
    "E8-touch": {
        "model": PROJECT_ROOT / "models/production/e8-touch/model.joblib",
        "config": PROJECT_ROOT / "models/production/e8-touch/config.yaml",
        "state": PROJECT_ROOT / "data/live/paper_state_e8.json",
        "description": "Touch 标签候选 (touch_filtered, 止盈+regime)",
    },
}


# ---------------------------------------------------------------------------
# Regime detection
# ---------------------------------------------------------------------------

def is_bear_market(
    prices: pd.Series, window: int = 63, threshold: float = -0.10,
) -> tuple[bool, float]:
    """返回 (是否熊市, 滚动收益率)."""
    if len(prices) < window + 1:
        return False, 0.0
    rolling_ret = (prices.iloc[-1] / prices.iloc[-window - 1]) - 1
    return rolling_ret <= threshold, float(rolling_ret)


# ---------------------------------------------------------------------------
# Signal generation (simplified for paper trading)
# ---------------------------------------------------------------------------

def generate_model_signal(
    model_path: Path,
    config_path: Path,
    df: pd.DataFrame,
) -> dict:
    """对单个模型生成信号."""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # 导入对应的标签策略以确保注册
    import src.labels  # noqa: F401

    # 构建特征
    feat_cfg = config["features"]
    df_feat = build_features(
        df.copy(),
        feature_sets=feat_cfg["sets"],
        drop_na_method=feat_cfg.get("drop_na_method", "ffill_then_drop"),
        drop_features=feat_cfg.get("drop_features"),
    )
    feature_cols = get_feature_columns(df_feat)

    # 加载模型并预测
    model = joblib.load(model_path)
    X_latest = df_feat[feature_cols].iloc[[-1]].values
    pred = int(model.predict(X_latest)[0])

    # 尝试获取概率
    proba = None
    if hasattr(model, "predict_proba"):
        probas = model.predict_proba(X_latest)[0]
        proba = float(probas[1]) if len(probas) > 1 else float(probas[0])

    # Regime
    bear, rolling_ret = is_bear_market(df_feat["close"])

    # 生成信号
    label_cfg = config["label"]
    X = label_cfg.get("X", 0.04)

    if bear:
        signal = "SILENT"
        reason = f"Regime=熊市 (63d收益={rolling_ret:.2%})"
    elif pred == 1:
        signal = "BUY"
        reason = f"模型预测=1 (proba={proba:.3f}), TP={X:.0%}"
    else:
        signal = "HOLD"
        reason = f"模型预测=0 (proba={proba:.3f})"

    return {
        "signal": signal,
        "prediction": pred,
        "probability": proba,
        "regime": "熊市" if bear else "非熊市",
        "rolling_63d": rolling_ret,
        "tp_threshold": X,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="E1 vs E8 Paper Trading")
    parser.add_argument("--download", action="store_true", help="拉取最新数据")
    parser.add_argument("--save", action="store_true", help="保存信号到 JSON")
    args = parser.parse_args()

    # 加载数据
    data_path = PROJECT_ROOT / "data/raw/btc_binance_BTCUSDT_1d.csv"
    if args.download:
        try:
            from src.data.downloader import download_binance_klines
            df = download_binance_klines(symbol="BTCUSDT", interval="1d")
            df.to_csv(data_path)
            logger.info("✅ 数据已更新")
        except Exception as e:
            logger.warning(f"下载失败, 使用本地数据: {e}")

    df = load_csv(str(data_path))
    current_price = float(df["close"].iloc[-1])
    current_date = df.index[-1].strftime("%Y-%m-%d")

    print("\n" + "=" * 70)
    print(f"  📈 Paper Trading: E1 vs E8 | {current_date} | BTC=${current_price:,.2f}")
    print("=" * 70)

    results = {}
    for name, cfg in MODELS.items():
        logger.info(f"\n--- {name}: {cfg['description']} ---")
        try:
            sig = generate_model_signal(
                model_path=cfg["model"],
                config_path=cfg["config"],
                df=df,
            )
            results[name] = sig

            # 信号输出
            emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪", "SILENT": "⚫"}.get(
                sig["signal"], "❓"
            )
            print(f"\n  {emoji} {name}:")
            print(f"     信号: {sig['signal']}")
            print(f"     概率: {sig['probability']:.3f}")
            print(f"     Regime: {sig['regime']} (63d={sig['rolling_63d']:.2%})")
            print(f"     原因: {sig['reason']}")

        except Exception as e:
            logger.error(f"{name} 信号生成失败: {e}")
            results[name] = {"signal": "ERROR", "error": str(e)}

    # 对比分析
    print("\n" + "-" * 70)
    signals = [r.get("signal") for r in results.values()]
    if len(set(signals)) == 1:
        print(f"  ✅ 两个模型一致: {signals[0]}")
    else:
        print(f"  ⚠️  信号分歧: {dict(zip(results.keys(), signals))}")
    print("-" * 70 + "\n")

    # 保存
    if args.save:
        output = {
            "date": current_date,
            "price": current_price,
            "models": results,
            "consensus": len(set(signals)) == 1,
        }
        save_dir = PROJECT_ROOT / "data/live/paper_trading"
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / f"signal_{current_date}.json"
        with open(save_path, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"✅ 信号已保存: {save_path}")


if __name__ == "__main__":
    main()
