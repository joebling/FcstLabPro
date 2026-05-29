#!/usr/bin/env python3
"""v0305 PnL 回测脚本.

对实验的 walk-forward 预测结果做交易回测，支持 regime 开关。

Usage:
    python scripts/pnl_backtest_v0305.py \
        --experiment experiments/weekly/weekly_bear_v0305_E5_low_threshold \
        --data data/raw/btc_binance_BTCUSDT_1d.csv \
        --regime-switch
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PnLResult:
    """PnL 回测结果."""
    total_return: float
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    win_rate: float
    profit_factor: float
    num_trades: int
    num_days_held: int
    avg_trade_return: float
    exposure: float  # 持仓时间比例


# ---------------------------------------------------------------------------
# Date-prediction alignment
# ---------------------------------------------------------------------------

def reconstruct_daily_predictions(
    predictions_csv: Path,
    fold_metrics_csv: Path,
    n_total: int,
    init_train: int,
    oos_window: int,
    step: int,
) -> pd.DataFrame:
    """将 walk-forward 的重叠预测去重，每个日期取最新 fold 的预测.

    Returns DataFrame with columns: [idx, y_true, y_pred, fold_id]
    """
    preds = pd.read_csv(predictions_csv)
    folds = pd.read_csv(fold_metrics_csv)
    n_folds = len(folds)

    # 给每条预测分配 fold_id 和原始数据索引
    records = []
    offset = 0
    for fold_id in range(n_folds):
        test_start = init_train + fold_id * step
        test_end = min(test_start + oos_window, n_total)
        fold_size = test_end - test_start
        for j in range(fold_size):
            records.append({
                "idx": test_start + j,
                "y_true": int(preds.iloc[offset + j]["y_true"]),
                "y_pred": int(preds.iloc[offset + j]["y_pred"]),
                "fold_id": fold_id,
            })
        offset += fold_size

    df = pd.DataFrame(records)
    # 重叠时取最新 fold 的预测（最后一个 fold_id 最大）
    df = df.sort_values(["idx", "fold_id"]).drop_duplicates(subset="idx", keep="last")
    df = df.sort_values("idx").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Regime detection
# ---------------------------------------------------------------------------

def compute_regime(
    prices: pd.Series, window: int = 63, bear_threshold: float = -0.10,
) -> pd.Series:
    """返回 bool Series: True = 非熊市 (可交易), False = 熊市 (静默)."""
    rolling_ret = prices.pct_change(window)
    return rolling_ret > bear_threshold


# ---------------------------------------------------------------------------
# Core PnL engine
# ---------------------------------------------------------------------------

def run_pnl(
    daily_preds: pd.DataFrame,
    prices: np.ndarray,
    dates: pd.DatetimeIndex,
    transaction_cost: float = 0.001,
    regime_mask: np.ndarray | None = None,
    holding_period: int = 21,
    take_profit: float | None = None,
) -> tuple[PnLResult, pd.DataFrame]:
    """运行 PnL 回测.

    Parameters
    ----------
    daily_preds : DataFrame
        必须包含 idx, y_pred
    prices : ndarray
        与原始数据对齐的价格序列
    dates : DatetimeIndex
        与原始数据对齐的日期序列
    transaction_cost : float
        单边交易成本
    regime_mask : ndarray, optional
        True = 可交易, False = 强制空仓
    holding_period : int
        每次信号的持仓天数 (与标签 T 一致)
    take_profit : float or None
        止盈阈值，到达后自动平仓 (例如 0.03 = 3%)

    Returns
    -------
    (PnLResult, equity_df)
    """
    idx_arr = daily_preds["idx"].values
    pred_arr = daily_preds["y_pred"].values

    # 构建每日仓位: y_pred=1 意味着 "买入并持有 T 天"
    n = len(prices)
    position = np.zeros(n)
    for i, idx in enumerate(idx_arr):
        if pred_arr[i] == 1:
            # 从信号日开始持仓 holding_period 天
            end = min(idx + holding_period, n)
            if take_profit is not None:
                # 止盈: 价格涨到 take_profit 即平仓
                entry_price = prices[idx]
                for d in range(idx, end):
                    if (prices[d] - entry_price) / entry_price >= take_profit:
                        end = d + 1  # 包含止盈日
                        break
            position[idx:end] = 1.0

    # 应用 regime 开关
    if regime_mask is not None:
        position = position * regime_mask.astype(float)

    # 计算每日收益率
    daily_returns = np.zeros(n)
    daily_returns[1:] = (prices[1:] - prices[:-1]) / prices[:-1]

    # 策略收益 = 昨日仓位 * 今日收益 - 交易成本
    trade_signal = np.diff(np.concatenate([[0], position]))
    costs = np.abs(trade_signal) * transaction_cost
    strategy_returns = np.zeros(n)
    strategy_returns[1:] = position[:-1] * daily_returns[1:] - costs[1:]

    # 只看 OOS 窗口内的回测
    oos_start = idx_arr[0]
    oos_end = idx_arr[-1] + 1
    strat_ret = strategy_returns[oos_start:oos_end]
    bnh_ret = daily_returns[oos_start:oos_end]
    pos_slice = position[oos_start:oos_end]

    # 累计收益曲线
    equity = np.cumprod(1 + strat_ret)
    bnh_equity = np.cumprod(1 + bnh_ret)

    total_return = equity[-1] - 1 if len(equity) > 0 else 0
    n_days = len(strat_ret)
    years = n_days / 365.0
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

    # Sharpe (annualised daily)
    std_ret = np.std(strat_ret)
    sharpe = np.mean(strat_ret) / std_ret * np.sqrt(365) if std_ret > 0 else 0

    # Sortino
    neg = strat_ret[strat_ret < 0]
    ds = np.std(neg) if len(neg) > 0 else 0
    sortino = np.mean(strat_ret) / ds * np.sqrt(365) if ds > 0 else 0

    # Max drawdown
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    max_dd = float(np.min(dd)) if len(dd) > 0 else 0

    calmar = cagr / abs(max_dd) if max_dd != 0 else 0

    # Trade stats
    trades = np.where(np.diff(np.concatenate([[0], pos_slice])) != 0)[0]
    num_trades = len(trades) // 2  # 买入+卖出算一笔

    # 按“持仓期”统计胜率 (今日收益对应昨日仓位)
    holding_returns = strat_ret[1:][pos_slice[:-1] > 0] if len(pos_slice) > 1 else np.array([])
    wins = holding_returns[holding_returns > 0]
    losses = holding_returns[holding_returns < 0]
    win_rate = len(wins) / len(holding_returns) if len(holding_returns) > 0 else 0
    pf = abs(wins.sum() / losses.sum()) if len(losses) > 0 and losses.sum() != 0 else 0
    avg_trade_ret = float(holding_returns.mean()) if len(holding_returns) > 0 else 0

    exposure = float(pos_slice.mean())
    num_days_held = int(pos_slice.sum())

    result = PnLResult(
        total_return=total_return, cagr=cagr, sharpe=sharpe, sortino=sortino,
        max_drawdown=max_dd, calmar=calmar, win_rate=win_rate,
        profit_factor=pf, num_trades=num_trades, num_days_held=num_days_held,
        avg_trade_return=avg_trade_ret, exposure=exposure,
    )

    equity_df = pd.DataFrame({
        "date": dates[oos_start:oos_end],
        "strategy_equity": equity,
        "bnh_equity": bnh_equity,
        "position": pos_slice,
        "strategy_return": strat_ret,
    })

    return result, equity_df


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_pnl_report(
    exp_name: str,
    results: dict[str, PnLResult],
    equity_dfs: dict[str, pd.DataFrame],
    output_path: Path,
) -> None:
    """Generate markdown PnL report."""
    lines = [
        f"# {exp_name} PnL 回测报告\n",
        f"**生成时间**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n",
    ]

    # Summary table
    lines.append("## 概览\n")
    header = "| 指标 | " + " | ".join(results.keys()) + " |"
    sep = "|------|" + "|".join(["------"] * len(results)) + "|"
    lines.append(header)
    lines.append(sep)

    metrics_display = [
        ("Total Return", "total_return", "{:.2%}"),
        ("CAGR", "cagr", "{:.2%}"),
        ("Sharpe", "sharpe", "{:.2f}"),
        ("Sortino", "sortino", "{:.2f}"),
        ("Max Drawdown", "max_drawdown", "{:.2%}"),
        ("Calmar", "calmar", "{:.2f}"),
        ("Win Rate", "win_rate", "{:.1%}"),
        ("Profit Factor", "profit_factor", "{:.2f}"),
        ("Trades", "num_trades", "{}"),
        ("Days Held", "num_days_held", "{}"),
        ("Exposure", "exposure", "{:.1%}"),
        ("Avg Trade Return", "avg_trade_return", "{:.4%}"),
    ]

    for label, key, fmt in metrics_display:
        vals = []
        for r in results.values():
            v = getattr(r, key)
            vals.append(fmt.format(v))
        lines.append(f"| {label} | " + " | ".join(vals) + " |")

    lines.append("")

    # Equity curve stats by year
    for name, eq_df in equity_dfs.items():
        if eq_df is None or len(eq_df) == 0:
            continue
        lines.append(f"## {name} 年度明细\n")
        eq_df = eq_df.copy()
        eq_df["year"] = eq_df["date"].dt.year
        yearly = []
        for year, grp in eq_df.groupby("year"):
            yr_ret = (1 + grp["strategy_return"]).prod() - 1
            yr_exp = grp["position"].mean()
            yearly.append({"Year": year, "Return": f"{yr_ret:.2%}", "Exposure": f"{yr_exp:.1%}"})
        lines.append(pd.DataFrame(yearly).to_markdown(index=False))
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ PnL 报告已保存: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="v0305 PnL 回测")
    parser.add_argument("--experiment", required=True, help="实验目录")
    parser.add_argument("--data", required=True, help="价格数据文件")
    parser.add_argument("--cost", type=float, default=0.001, help="单边交易成本")
    parser.add_argument("--regime-switch", action="store_true", help="启用 regime 开关")
    parser.add_argument("--regime-window", type=int, default=63, help="Regime 判断窗口")
    parser.add_argument("--output", default=None, help="输出报告路径")
    args = parser.parse_args()

    exp_dir = Path(args.experiment)
    with open(exp_dir / "config.yaml") as f:
        config = yaml.safe_load(f)

    eval_cfg = config["evaluation"]
    init_train = eval_cfg["init_train"]
    oos_window = eval_cfg["oos_window"]
    step = eval_cfg["step"]

    # Load & preprocess data (same pipeline as experiment)
    from src.data.loader import load_csv
    from src.features.builder import build_features
    from src.labels.registry import get_label_strategy
    import src.labels.directional_filtered  # noqa
    import src.labels.directional  # noqa
    import src.labels.triple_barrier_simple  # noqa
    import src.labels.dip_recovery_v2  # noqa
    import src.labels.dip_recovery_v1  # noqa
    import inspect

    df = load_csv(args.data, start=config["data"].get("start"), end=config["data"].get("end"))
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
    label_kwargs = {k: v for k, v in label_cfg.items() if k not in _meta_keys and k in _accepted}
    labels = label_func(df, **label_kwargs)
    df["label"] = labels
    df = df.dropna(subset=["label"])

    prices = df["close"].values
    dates = df.index
    n_total = len(df)

    print(f"数据: {n_total} 行, {dates[0].date()} ~ {dates[-1].date()}")

    # Reconstruct predictions
    daily_preds = reconstruct_daily_predictions(
        predictions_csv=exp_dir / "predictions.csv",
        fold_metrics_csv=exp_dir / "fold_metrics.csv",
        n_total=n_total,
        init_train=init_train,
        oos_window=oos_window,
        step=step,
    )
    print(f"预测: {len(daily_preds)} 个唯一日期, 做多信号={daily_preds['y_pred'].sum()}")

    # Regime mask
    regime_mask = None
    if args.regime_switch:
        regime_bool = compute_regime(pd.Series(prices, index=dates), window=args.regime_window)
        regime_mask = regime_bool.values
        bear_days = (~regime_bool).sum()
        print(f"Regime 开关: 熊市天数={bear_days} ({bear_days/n_total:.1%})")

    # Run backtests
    results = {}
    equity_dfs = {}
    T = config["label"].get("T", 21)

    # Strategy: no regime switch
    r_base, eq_base = run_pnl(daily_preds, prices, dates, args.cost, holding_period=T)
    results["策略(无开关)"] = r_base
    equity_dfs["策略(无开关)"] = eq_base

    if args.regime_switch:
        r_regime, eq_regime = run_pnl(daily_preds, prices, dates, args.cost, regime_mask, holding_period=T)
        results["策略(+regime开关)"] = r_regime
        equity_dfs["策略(+regime开关)"] = eq_regime

    # Strategy with take-profit
    X = config["label"].get("X", 0.03)
    r_tp, eq_tp = run_pnl(daily_preds, prices, dates, args.cost, holding_period=T, take_profit=X)
    results["策略(+止盈)"] = r_tp
    equity_dfs["策略(+止盈)"] = eq_tp

    if args.regime_switch:
        r_tp_regime, eq_tp_regime = run_pnl(daily_preds, prices, dates, args.cost, regime_mask, holding_period=T, take_profit=X)
        results["策略(止盈+regime)"] = r_tp_regime
        equity_dfs["策略(止盈+regime)"] = eq_tp_regime

    # Buy and hold (same OOS period)
    oos_start = daily_preds["idx"].values[0]
    oos_end = daily_preds["idx"].values[-1] + 1
    bnh_preds = daily_preds.copy()
    bnh_preds["y_pred"] = 1  # always long
    r_bnh, eq_bnh = run_pnl(bnh_preds, prices, dates, 0.0, holding_period=n_total)  # infinite hold
    results["买入持有"] = r_bnh
    equity_dfs["买入持有"] = eq_bnh

    # Fair random baseline: match EXPOSURE, not signal count
    # Calculate actual strategy exposure
    actual_exposure = r_base.exposure
    n_oos_days = len(daily_preds)
    actual_position_days = int(actual_exposure * n_oos_days)
    print(f"\n策略暴露: {actual_exposure:.1%} ({actual_position_days}/{n_oos_days} 天)")

    rng = np.random.default_rng(42)
    random_returns = []
    for _ in range(200):
        rand_preds = daily_preds.copy()
        rand_preds["y_pred"] = 0
        # 随机选相同数量的天数持仓 (不用 holding_period, 直接按天)
        if actual_position_days > 0 and actual_position_days < n_oos_days:
            rand_idx = rng.choice(n_oos_days, size=actual_position_days, replace=False)
            rand_preds.iloc[rand_idx, rand_preds.columns.get_loc("y_pred")] = 1
        else:
            rand_preds["y_pred"] = 1
        r_rand, _ = run_pnl(rand_preds, prices, dates, args.cost, holding_period=1)
        random_returns.append(r_rand.total_return)

    rand_mean = np.mean(random_returns)
    rand_std = np.std(random_returns)
    alpha = r_base.total_return - rand_mean
    alpha_z = alpha / (rand_std + 1e-10)

    print(f"随机基线 (同暴露, 200次): Return={rand_mean:+.2%} ± {rand_std:.2%}")
    print(f"策略 vs 随机: {alpha:+.2%} (超额)")
    print(f"Alpha Z-score: {alpha_z:.2f} {'(显著)' if abs(alpha_z) > 1.96 else '(不显著)'}")

    # Print summary
    print("\n" + "=" * 60)
    print(f"{'':>25s} | {'':>12s} | {'':>8s} | {'':>8s} | {'':>8s}")
    print(f"{'Strategy':>25s} | {'Return':>12s} | {'Sharpe':>8s} | {'MaxDD':>8s} | {'WinRate':>8s}")
    print("-" * 75)
    for name, r in results.items():
        print(f"{name:>25s} | {r.total_return:>+12.2%} | {r.sharpe:>8.2f} | {r.max_drawdown:>8.2%} | {r.win_rate:>8.1%}")
    print("=" * 60)

    # Save report
    output = Path(args.output) if args.output else exp_dir / "pnl_report.md"
    generate_pnl_report(exp_dir.name, results, equity_dfs, output)

    # Save equity curves
    for name, eq_df in equity_dfs.items():
        safe_name = name.replace("(", "").replace(")", "").replace("+", "").replace("无开关", "raw").replace("regime开关", "regime").replace("买入持有", "bnh").replace("策略", "strat")
        eq_df.to_csv(exp_dir / f"equity_{safe_name}.csv", index=False)

    # Save metrics JSON
    metrics_out = {name: asdict(r) for name, r in results.items()}
    with open(exp_dir / "pnl_metrics.json", "w") as f:
        json.dump(metrics_out, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 产物已保存到: {exp_dir}")


if __name__ == "__main__":
    main()
