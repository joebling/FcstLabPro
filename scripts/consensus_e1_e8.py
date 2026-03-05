#!/usr/bin/env python3
"""E1+E8 共识过滤实验.

用两个模型的 walk-forward 预测做逻辑 AND，
只有两个模型都看多才入场，然后跑 PnL 回测。

Usage:
    python3.10 scripts/consensus_e1_e8.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

E1_DIR = PROJECT_ROOT / "experiments/weekly/weekly_bear_v0305_E1_decontam"
E8_DIR = PROJECT_ROOT / "experiments/weekly/weekly_bear_v0305_E8_touch_label"
DATA_PATH = PROJECT_ROOT / "data/raw/btc_binance_BTCUSDT_1d.csv"
OUTPUT_DIR = PROJECT_ROOT / "experiments/weekly/consensus_E1_E8"


# ---------------------------------------------------------------------------
# PnL engine (simplified from pnl_backtest_v0305.py)
# ---------------------------------------------------------------------------

@dataclass
class PnLResult:
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
    exposure: float


def compute_pnl(
    daily_returns: pd.Series,
    positions: pd.Series,
    cost_per_trade: float = 0.001,
) -> PnLResult:
    """Compute PnL metrics from daily returns and position signals."""
    n_days = len(daily_returns)

    # Strategy returns (with transaction cost on position changes)
    pos_changes = positions.diff().abs().fillna(0)
    strat_rets = positions.shift(1).fillna(0) * daily_returns - pos_changes * cost_per_trade

    # Equity curve
    equity = (1 + strat_rets).cumprod()

    # Metrics
    total_return = float(equity.iloc[-1] - 1)
    n_years = n_days / 252
    cagr = float((1 + total_return) ** (1 / max(n_years, 0.01)) - 1)

    mean_ret = strat_rets.mean()
    std_ret = strat_rets.std()
    sharpe = float(mean_ret / (std_ret + 1e-10) * np.sqrt(252))

    downside = strat_rets[strat_rets < 0].std()
    sortino = float(mean_ret / (downside + 1e-10) * np.sqrt(252))

    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_dd = float(drawdown.min())
    calmar = float(cagr / abs(max_dd)) if max_dd != 0 else 0.0

    # Trade counting
    trade_starts = (positions.diff().fillna(0) == 1)
    num_trades = int(trade_starts.sum())
    days_held = int(positions.sum())

    # Win rate and profit factor
    active_rets = strat_rets[positions.shift(1).fillna(0) == 1]
    if len(active_rets) > 0:
        win_rate = float((active_rets > 0).mean())
        gross_profit = float(active_rets[active_rets > 0].sum())
        gross_loss = float(abs(active_rets[active_rets < 0].sum()))
        pf = gross_profit / (gross_loss + 1e-10)
    else:
        win_rate = 0.0
        pf = 0.0

    avg_trade_ret = float(active_rets.mean()) if len(active_rets) > 0 else 0.0
    exposure = days_held / max(n_days, 1)

    return PnLResult(
        total_return=total_return, cagr=cagr, sharpe=sharpe, sortino=sortino,
        max_drawdown=max_dd, calmar=calmar, win_rate=win_rate,
        profit_factor=pf, num_trades=num_trades, num_days_held=days_held,
        avg_trade_return=avg_trade_ret, exposure=exposure,
    )


def is_bear_market(
    prices: pd.Series, window: int = 63, threshold: float = -0.10,
) -> pd.Series:
    """Return boolean Series marking bear market days."""
    rolling_ret = prices / prices.shift(window) - 1
    return rolling_ret <= threshold


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Load price data
    from src.data.loader import load_csv
    df = load_csv(str(DATA_PATH))

    # Load E1 equity (to get date-aligned positions)
    e1_equity = pd.read_csv(E1_DIR / "equity_stratraw.csv", parse_dates=["date"], index_col="date")
    e8_equity = pd.read_csv(E8_DIR / "equity_stratraw.csv", parse_dates=["date"], index_col="date")

    # Align date ranges
    common_dates = e1_equity.index.intersection(e8_equity.index).intersection(df.index)
    common_dates = common_dates.sort_values()
    print(f"共同日期范围: {common_dates[0].date()} ~ {common_dates[-1].date()}, {len(common_dates)} 天")

    # Extract positions (1 = in market, 0 = cash)
    e1_pos = e1_equity.loc[common_dates, "position"]
    e8_pos = e8_equity.loc[common_dates, "position"]

    # Daily returns
    daily_ret = df.loc[common_dates, "close"].pct_change().fillna(0)

    # Regime
    bear = is_bear_market(df.loc[:common_dates[-1], "close"]).reindex(common_dates).fillna(False)

    # =====================================================================
    # Generate signal variants
    # =====================================================================

    signals = {
        "E1 (生产)": e1_pos,
        "E8 (touch)": e8_pos,
        "AND 共识 (无开关)": ((e1_pos == 1) & (e8_pos == 1)).astype(float),
        "OR 并集 (无开关)": ((e1_pos == 1) | (e8_pos == 1)).astype(float),
    }

    # Add regime-filtered versions
    for name, pos in list(signals.items()):
        regime_pos = pos.copy()
        regime_pos[bear] = 0.0
        signals[f"{name} +regime"] = regime_pos

    # Add take-profit versions for consensus
    # For take-profit we need to track positions more carefully
    # Use a simple approach: apply TP to the consensus signal
    tp_threshold = 0.04
    for base_name, base_pos in [("AND 共识", ((e1_pos == 1) & (e8_pos == 1)).astype(float))]:
        tp_pos = base_pos.copy()
        entry_price = None
        for i, date in enumerate(common_dates):
            price = df.loc[date, "close"]
            if tp_pos.iloc[i] == 1:
                if entry_price is None:
                    entry_price = price
                else:
                    pnl = (price - entry_price) / entry_price
                    if pnl >= tp_threshold:
                        tp_pos.iloc[i] = 0  # Take profit
                        entry_price = None
            else:
                entry_price = None

        signals[f"{base_name} (+止盈)"] = tp_pos

        # + regime
        tp_regime_pos = tp_pos.copy()
        tp_regime_pos[bear] = 0.0
        signals[f"{base_name} (止盈+regime)"] = tp_regime_pos

    # =====================================================================
    # Compute PnL for all variants
    # =====================================================================

    results = {}
    print("\n" + "=" * 80)
    print(f"  E1+E8 共识过滤实验 | {common_dates[0].date()} ~ {common_dates[-1].date()}")
    print("=" * 80)

    for name, pos in signals.items():
        pnl = compute_pnl(daily_ret, pos)
        results[name] = asdict(pnl)
        print(f"\n  {name}:")
        print(f"    Return={pnl.total_return:+.2%}, Sharpe={pnl.sharpe:.3f}, "
              f"MaxDD={pnl.max_drawdown:.2%}, Calmar={pnl.calmar:.3f}")
        print(f"    PF={pnl.profit_factor:.3f}, Trades={pnl.num_trades}, "
              f"Exposure={pnl.exposure:.1%}, AvgTrade={pnl.avg_trade_return:.4%}")

    # =====================================================================
    # Signal agreement analysis
    # =====================================================================

    both_buy = ((e1_pos == 1) & (e8_pos == 1)).sum()
    e1_only = ((e1_pos == 1) & (e8_pos == 0)).sum()
    e8_only = ((e1_pos == 0) & (e8_pos == 1)).sum()
    neither = ((e1_pos == 0) & (e8_pos == 0)).sum()
    total = len(common_dates)

    print("\n" + "-" * 80)
    print("  信号一致性分析:")
    print(f"    两者都买: {both_buy} 天 ({both_buy/total:.1%})")
    print(f"    E1独买:  {e1_only} 天 ({e1_only/total:.1%})")
    print(f"    E8独买:  {e8_only} 天 ({e8_only/total:.1%})")
    print(f"    两者都不买: {neither} 天 ({neither/total:.1%})")
    print("-" * 80)

    # =====================================================================
    # Save results
    # =====================================================================

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_DIR / "consensus_metrics.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Save equity curves for key variants
    for name, pos in [("AND共识_止盈regime", signals.get("AND 共识 (止盈+regime)"))]:
        if pos is not None:
            pos_changes = pos.diff().abs().fillna(0)
            strat_rets = pos.shift(1).fillna(0) * daily_ret - pos_changes * 0.001
            equity = (1 + strat_rets).cumprod()
            eq_df = pd.DataFrame({
                "date": common_dates,
                "strategy_equity": equity.values,
                "position": pos.values,
            })
            eq_df.to_csv(OUTPUT_DIR / f"equity_{name}.csv", index=False)

    print(f"\n✅ 结果已保存: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
