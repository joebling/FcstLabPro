#!/usr/bin/env python3
"""Fold Regime 分析脚本.

对实验的每个 Walk-Forward fold 标注市场 regime（bull/bear/sideways），
分析模型在不同市场环境下的表现。

Usage:
    python scripts/analyze_fold_regimes.py \
        --experiments weekly/weekly_bear_v0305_E1_decontam \
                      weekly/weekly_bear_v0305_E3_tb_grid_a \
        --data data/raw/btc_binance_BTCUSDT_1d.csv
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Regime 分类
# ---------------------------------------------------------------------------

def classify_regime(
    prices: pd.Series,
    window: int = 63,
    bull_threshold: float = 0.10,
    bear_threshold: float = -0.10,
) -> pd.Series:
    """基于滚动收益率对每个日期标注 regime.

    Parameters
    ----------
    prices : pd.Series
        日线收盘价，index 为日期
    window : int
        滚动窗口（天），默认 63≈ 3 个月
    bull_threshold : float
        滚动收益 > 此阈值则为 bull
    bear_threshold : float
        滚动收益 < 此阈值则为 bear

    Returns
    -------
    pd.Series
        'bull' | 'bear' | 'sideways'
    """
    rolling_return = prices.pct_change(window)
    regime = pd.Series("sideways", index=prices.index, name="regime")
    regime[rolling_return > bull_threshold] = "bull"
    regime[rolling_return < bear_threshold] = "bear"
    return regime


# ---------------------------------------------------------------------------
# Fold 分析
# ---------------------------------------------------------------------------

def load_fold_metrics(exp_dir: Path) -> pd.DataFrame:
    """Load fold_metrics.csv from an experiment directory."""
    path = exp_dir / "fold_metrics.csv"
    if not path.exists():
        raise FileNotFoundError(f"\u627e\u4e0d\u5230 fold metrics: {path}")
    return pd.read_csv(path)


def compute_fold_date_ranges(
    n_samples: int,
    init_train: int,
    oos_window: int,
    step: int,
    dates: pd.DatetimeIndex,
) -> list[dict]:
    """Reconstruct test date ranges for each fold."""
    ranges = []
    train_end = init_train
    fold_id = 0
    while train_end + oos_window <= n_samples:
        test_start = train_end
        test_end = min(train_end + oos_window, n_samples)
        ranges.append({
            "fold_id": fold_id,
            "test_start_date": dates[test_start],
            "test_end_date": dates[test_end - 1],
        })
        train_end += step
        fold_id += 1
    return ranges


def assign_fold_regime(
    fold_ranges: list[dict],
    regime_series: pd.Series,
) -> list[dict]:
    """Assign dominant regime to each fold based on test window."""
    results = []
    for fr in fold_ranges:
        mask = (regime_series.index >= fr["test_start_date"]) & (
            regime_series.index <= fr["test_end_date"]
        )
        window_regimes = regime_series[mask]
        if len(window_regimes) == 0:
            dominant = "unknown"
        else:
            dominant = window_regimes.value_counts().idxmax()
        results.append({
            **fr,
            "regime": dominant,
        })
    return results


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------

def generate_regime_report(
    experiment_results: dict[str, pd.DataFrame],
    output_path: Path,
) -> None:
    """Generate a Markdown regime analysis report."""
    lines = [
        "# v0305 Fold Regime 分析报告\n",
        "## 概述\n",
        "对每个实验的 fold 按市场 regime（bull/bear/sideways）分组，",
        "分析模型在不同环境下的表现。\n",
    ]

    for exp_name, df in experiment_results.items():
        lines.append(f"---\n\n## {exp_name}\n")

        # 汇总表
        summary = (
            df.groupby("regime")
            .agg(
                fold_count=("fold_id", "count"),
                kappa_mean=("cohen_kappa", "mean"),
                kappa_std=("cohen_kappa", "std"),
                f1_mean=("f1_binary", "mean"),
                f1_gt0_ratio=("f1_binary", lambda x: (x > 0).mean()),
            )
            .round(3)
        )
        lines.append("### Regime 统计\n")
        lines.append(summary.to_markdown() + "\n")

        # F1=0 的 fold 时间分布
        dead_folds = df[df["f1_binary"] == 0]
        if len(dead_folds) > 0:
            regime_dist = dead_folds["regime"].value_counts()
            lines.append(f"### F1=0 的 fold 分布 ({len(dead_folds)}个)\n")
            lines.append(regime_dist.to_markdown() + "\n")
        else:
            lines.append("### ✅ 无 F1=0 的 fold\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\u2705 Regime 分析报告已保存: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fold Regime 分析")
    parser.add_argument(
        "--experiments", nargs="+", required=True,
        help="实验目录 (相对于 experiments/), 如 weekly/weekly_bear_v0305_E1",
    )
    parser.add_argument(
        "--data", required=True,
        help="价格数据文件路径",
    )
    parser.add_argument(
        "--regime-window", type=int, default=63,
        help="Regime 分类滚动窗口（天）",
    )
    parser.add_argument(
        "--output", default="experiments/weekly/v0305_fold_regime_analysis.md",
        help="输出报告路径",
    )
    args = parser.parse_args()

    # 加载价格数据
    price_df = pd.read_csv(args.data, parse_dates=["date"])
    price_df = price_df.set_index("date").sort_index()
    regime_series = classify_regime(price_df["close"], window=args.regime_window)

    experiment_results = {}

    for exp_rel in args.experiments:
        exp_dir = PROJECT_ROOT / "experiments" / exp_rel
        exp_name = exp_dir.name

        print(f"\u2192 分析: {exp_name}")

        # 读取 fold metrics
        fold_df = load_fold_metrics(exp_dir)

        # 读取 config 获取 walk-forward 参数
        import yaml
        config_path = exp_dir / "config.yaml"
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        eval_cfg = config["evaluation"]
        init_train = eval_cfg.get("init_train", 800)
        oos_window = eval_cfg.get("oos_window", 63)
        step = eval_cfg.get("step", 21)

        # 重建 fold 时间窗口
        # 需要知道处理后的数据长度和日期索引
        # 简化方法：从价格数据中截取对应的日期
        dates = price_df.index
        n_folds = len(fold_df)
        fold_ranges = compute_fold_date_ranges(
            n_samples=len(dates),
            init_train=init_train,
            oos_window=oos_window,
            step=step,
            dates=dates,
        )

        # 取前 n_folds 个
        fold_ranges = fold_ranges[:n_folds]

        # 标注 regime
        regime_info = assign_fold_regime(fold_ranges, regime_series)
        regime_df = pd.DataFrame(regime_info)

        # 合并
        merged = fold_df.merge(
            regime_df[["fold_id", "test_start_date", "test_end_date", "regime"]],
            on="fold_id",
            how="left",
        )
        experiment_results[exp_name] = merged

    # 生成报告
    generate_regime_report(experiment_results, Path(args.output))


if __name__ == "__main__":
    main()
