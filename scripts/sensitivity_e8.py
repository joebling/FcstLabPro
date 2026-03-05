#!/usr/bin/env python3
"""E8 touch_filtered 敏感性分析脚本.

网格扫描: regime_threshold × cost × tp_threshold
生成综合报告。

Usage:
    python3.10 scripts/sensitivity_e8.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.pnl_backtest_v0305 import (
    PnLResult,
    compute_regime,
    reconstruct_daily_predictions,
    run_pnl,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EXP_DIR = PROJECT_ROOT / "experiments/weekly/weekly_bear_v0305_E8_touch_label"
DATA_PATH = PROJECT_ROOT / "data/raw/btc_binance_BTCUSDT_1d.csv"
OUTPUT_DIR = EXPERIMENT_DIR = EXP_DIR

# 网格参数
REGIME_THRESHOLDS = [-0.08, -0.10, -0.12]  # 熊市判定阈值
COSTS = [0.001, 0.002, 0.003]               # 单边交易成本
TP_THRESHOLDS = [0.03, 0.04, 0.05]          # 止盈阈值
REGIME_WINDOW = 63


def load_experiment_data():
    """加载实验数据和预测结果."""
    import inspect

    from src.data.loader import load_csv
    from src.features.builder import build_features
    from src.labels.registry import get_label_strategy
    import src.labels.touch_filtered  # noqa: F401

    with open(EXP_DIR / "config.yaml") as f:
        config = yaml.safe_load(f)

    df = load_csv(str(DATA_PATH))
    df = build_features(
        df,
        feature_sets=config["features"]["sets"],
        drop_na_method=config["features"].get("drop_na_method", "ffill_then_drop"),
        drop_features=config["features"].get("drop_features"),
    )

    label_cfg = config["label"]
    label_func = get_label_strategy(label_cfg["strategy"])
    _meta_keys = {"strategy", "map"}
    _accepted = set(inspect.signature(label_func).parameters.keys()) - {"df"}
    label_kwargs = {
        k: v for k, v in label_cfg.items() if k not in _meta_keys and k in _accepted
    }
    labels = label_func(df, **label_kwargs)
    df["label"] = labels
    df = df.dropna(subset=["label"])

    eval_cfg = config["evaluation"]
    daily_preds = reconstruct_daily_predictions(
        predictions_csv=EXP_DIR / "predictions.csv",
        fold_metrics_csv=EXP_DIR / "fold_metrics.csv",
        n_total=len(df),
        init_train=eval_cfg["init_train"],
        oos_window=eval_cfg["oos_window"],
        step=eval_cfg["step"],
    )

    return df, daily_preds, config


def run_sensitivity_grid(
    df: pd.DataFrame,
    daily_preds: pd.DataFrame,
    config: dict,
) -> list[dict]:
    """遍历所有参数组合，返回结果列表."""
    prices = df["close"].values
    dates = df.index
    T = config["label"].get("T", 21)
    results = []

    # 预计算所有 regime mask
    regime_masks = {}
    for bear_th in REGIME_THRESHOLDS:
        regime_bool = compute_regime(
            pd.Series(prices, index=dates),
            window=REGIME_WINDOW,
            bear_threshold=bear_th,
        )
        regime_masks[bear_th] = regime_bool.values
        bear_days = (~regime_bool).sum()
        print(f"  Regime {bear_th:.0%}: 熊市天数={bear_days} ({bear_days/len(prices):.1%})")

    total = len(REGIME_THRESHOLDS) * len(COSTS) * len(TP_THRESHOLDS)
    idx = 0

    for bear_th, cost, tp in product(REGIME_THRESHOLDS, COSTS, TP_THRESHOLDS):
        idx += 1
        regime_mask = regime_masks[bear_th]

        r, _ = run_pnl(
            daily_preds, prices, dates,
            transaction_cost=cost,
            regime_mask=regime_mask,
            holding_period=T,
            take_profit=tp,
        )

        row = {
            "regime_threshold": f"{bear_th:.0%}",
            "cost_bps": f"{cost*100:.1f}%",
            "tp_threshold": f"{tp:.0%}",
            "total_return": r.total_return,
            "cagr": r.cagr,
            "sharpe": r.sharpe,
            "sortino": r.sortino,
            "max_drawdown": r.max_drawdown,
            "calmar": r.calmar,
            "profit_factor": r.profit_factor,
            "num_trades": r.num_trades,
            "exposure": r.exposure,
            "win_rate": r.win_rate,
        }
        results.append(row)

        if idx % 9 == 0 or idx == total:
            print(f"  进度: {idx}/{total}")

    return results


def generate_sensitivity_report(
    results: list[dict],
    output_path: Path,
) -> None:
    """生成 Markdown 敏感性分析报告."""
    rdf = pd.DataFrame(results)

    # 找到最优组合（按不同目标）
    best_sharpe_idx = rdf["sharpe"].idxmax()
    best_calmar_idx = rdf["calmar"].idxmax()
    best_return_idx = rdf["total_return"].idxmax()
    lowest_dd_idx = rdf["max_drawdown"].idxmax()  # max_drawdown 是负数，最大=最小回撤

    lines = [
        "# E8 Touch Label 敏感性分析报告\n",
        f"**生成时间**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n",
        "**扫描参数**:",
        f"- Regime 阈值: {REGIME_THRESHOLDS}",
        f"- 交易成本: {COSTS} (单边)",
        f"- 止盈阈值: {TP_THRESHOLDS}",
        f"- 总组合数: {len(results)}\n",
        "---\n",
    ]

    # 最优组合总结
    lines.append("## 一、最优组合\n")

    for label, idx_val in [
        ("最高 Sharpe", best_sharpe_idx),
        ("最高 Calmar", best_calmar_idx),
        ("最高收益", best_return_idx),
        ("最小回撤", lowest_dd_idx),
    ]:
        r = rdf.iloc[idx_val]
        lines.append(
            f"**{label}**: Regime={r['regime_threshold']}, "
            f"Cost={r['cost_bps']}, TP={r['tp_threshold']} → "
            f"Return={r['total_return']:+.2%}, Sharpe={r['sharpe']:.2f}, "
            f"MaxDD={r['max_drawdown']:.2%}, Calmar={r['calmar']:.2f}"
        )
    lines.append("")

    # 成本敏感性（固定 regime=-10%, tp=4%）
    lines.append("---\n")
    lines.append("## 二、成本敏感性 (Regime=-10%, TP=4%)\n")
    cost_df = rdf[(rdf["regime_threshold"] == "-10%") & (rdf["tp_threshold"] == "4%")]
    if len(cost_df) > 0:
        lines.append("| 成本 | Return | CAGR | Sharpe | MaxDD | PF | Trades |")
        lines.append("|------|--------|------|--------|-------|-----|--------|")
        for _, r in cost_df.iterrows():
            lines.append(
                f"| {r['cost_bps']} | {r['total_return']:+.2%} | "
                f"{r['cagr']:.2%} | {r['sharpe']:.2f} | "
                f"{r['max_drawdown']:.2%} | {r['profit_factor']:.2f} | "
                f"{r['num_trades']} |"
            )
    lines.append("")

    # Regime 敏感性（固定 cost=0.1%, tp=4%）
    lines.append("## 三、Regime 阈值敏感性 (Cost=0.1%, TP=4%)\n")
    regime_df = rdf[(rdf["cost_bps"] == "0.1%") & (rdf["tp_threshold"] == "4%")]
    if len(regime_df) > 0:
        lines.append("| Regime | Return | CAGR | Sharpe | MaxDD | Calmar | Exposure |")
        lines.append("|--------|--------|------|--------|-------|--------|----------|")
        for _, r in regime_df.iterrows():
            lines.append(
                f"| {r['regime_threshold']} | {r['total_return']:+.2%} | "
                f"{r['cagr']:.2%} | {r['sharpe']:.2f} | "
                f"{r['max_drawdown']:.2%} | {r['calmar']:.2f} | "
                f"{r['exposure']:.1%} |"
            )
    lines.append("")

    # 止盈敏感性（固定 regime=-10%, cost=0.1%）
    lines.append("## 四、止盈阈值敏感性 (Regime=-10%, Cost=0.1%)\n")
    tp_df = rdf[(rdf["regime_threshold"] == "-10%") & (rdf["cost_bps"] == "0.1%")]
    if len(tp_df) > 0:
        lines.append("| TP | Return | CAGR | Sharpe | MaxDD | Calmar | PF |")
        lines.append("|----|--------|------|--------|-------|--------|----|")
        for _, r in tp_df.iterrows():
            lines.append(
                f"| {r['tp_threshold']} | {r['total_return']:+.2%} | "
                f"{r['cagr']:.2%} | {r['sharpe']:.2f} | "
                f"{r['max_drawdown']:.2%} | {r['calmar']:.2f} | "
                f"{r['profit_factor']:.2f} |"
            )
    lines.append("")

    # 全量结果表
    lines.append("## 五、全量结果\n")
    lines.append(
        "| Regime | Cost | TP | Return | Sharpe | MaxDD | Calmar | PF | Trades |"
    )
    lines.append(
        "|--------|------|----|--------|--------|-------|--------|-----|--------|"
    )
    for _, r in rdf.iterrows():
        lines.append(
            f"| {r['regime_threshold']} | {r['cost_bps']} | {r['tp_threshold']} | "
            f"{r['total_return']:+.2%} | {r['sharpe']:.2f} | "
            f"{r['max_drawdown']:.2%} | {r['calmar']:.2f} | "
            f"{r['profit_factor']:.2f} | {r['num_trades']} |"
        )
    lines.append("")

    # 与 E1 生产对比
    lines.append("---\n")
    lines.append("## 六、与 E1 生产模型对比 (止盈+Regime)\n")
    lines.append("| 指标 | E1 (生产) | E8 默认 | E8 最优 Calmar |")
    lines.append("|------|---------|---------|-----------------|")

    e1 = {
        "total_return": 0.3667, "cagr": 0.0981, "sharpe": 0.633,
        "max_drawdown": -0.1266, "calmar": 0.775, "profit_factor": 1.318,
    }
    e8_default = rdf[(rdf["regime_threshold"] == "-10%") & (rdf["cost_bps"] == "0.1%") & (rdf["tp_threshold"] == "4%")]
    e8_best_calmar = rdf.iloc[best_calmar_idx]

    if len(e8_default) > 0:
        e8d = e8_default.iloc[0]
        for label, key, fmt in [
            ("Total Return", "total_return", "{:+.2%}"),
            ("CAGR", "cagr", "{:.2%}"),
            ("Sharpe", "sharpe", "{:.2f}"),
            ("MaxDD", "max_drawdown", "{:.2%}"),
            ("Calmar", "calmar", "{:.2f}"),
            ("Profit Factor", "profit_factor", "{:.2f}"),
        ]:
            lines.append(
                f"| {label} | {fmt.format(e1[key])} | "
                f"{fmt.format(e8d[key])} | "
                f"{fmt.format(e8_best_calmar[key])} |"
            )
    lines.append("")

    lines.append(f"\n*报告生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}*\n")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✅ 敏感性报告已保存: {output_path}")


def main():
    print("=" * 60)
    print("E8 Touch Label 敏感性分析")
    print("=" * 60)

    print("\n⭐ 加载实验数据...")
    df, daily_preds, config = load_experiment_data()
    print(f"   数据: {len(df)} 行, 预测: {len(daily_preds)} 天\n")

    print("⭐ 运行网格扫描...")
    results = run_sensitivity_grid(df, daily_preds, config)

    # 保存原始结果 JSON
    output_json = EXP_DIR / "sensitivity_results.json"
    with open(output_json, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n✅ 原始结果已保存: {output_json}")

    # 生成报告
    report_path = EXP_DIR / "sensitivity_report.md"
    generate_sensitivity_report(results, report_path)

    print("\n" + "=" * 60)
    print("完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
