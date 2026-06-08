#!/usr/bin/env python3
"""Regime overlay 回测对比 (纯研究, 不碰生产).

方法: 取 e20c 的「止盈无regime」原始仓位序列 (equity_strat止盈.csv 的 position),
作为基准信号; 然后分别套上不同 regime overlay (regime=避险时强制空仓),
对比 Sharpe / MaxDD / 收益, 隔离「regime 过滤」这单一变量的贡献。

⚠️ point-in-time: regime 用 regime_analysis.py 的 point-in-time 算法,
   只用 <=t 数据。回测严格用 e20c 的 OOS 期 (2022-09 ~ 2025-11)。

用法:
    python scripts/research/regime_backtest.py
输出:
    experiments/research/regime/backtest_compare.csv
    控制台对比表
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.research.regime_analysis import (  # noqa: E402
    load_prices,
    regime_legacy,
    regime_multidim,
)

EXP_DIR = PROJECT_ROOT / "experiments" / "weekly" / "v0601_E20c_prune_core_run1"
OUT_DIR = PROJECT_ROOT / "experiments" / "research" / "regime"


def perf_metrics(daily_ret, position):
    """从日收益序列算绩效指标 (年化 365, crypto 全年交易)."""
    eq = (1 + daily_ret).cumprod()
    total_ret = float(eq.iloc[-1] - 1)
    n = len(daily_ret)
    cagr = float(eq.iloc[-1] ** (365 / n) - 1) if n > 0 else 0.0
    vol = float(daily_ret.std() * np.sqrt(365))
    sharpe = float(daily_ret.mean() / daily_ret.std() * np.sqrt(365)) if daily_ret.std() > 0 else 0.0
    downside = daily_ret[daily_ret < 0].std()
    sortino = float(daily_ret.mean() / downside * np.sqrt(365)) if downside > 0 else 0.0
    roll_max = eq.cummax()
    max_dd = float((eq / roll_max - 1).min())
    calmar = float(cagr / abs(max_dd)) if max_dd != 0 else 0.0
    exposure = float((position > 0).mean())
    trades = int(((position > 0) & (position.shift(1).fillna(0) == 0)).sum())
    return {
        "total_return": total_ret,
        "cagr": cagr,
        "vol": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "calmar": calmar,
        "exposure": exposure,
        "num_trades": trades,
    }


def apply_overlay(base_pos, daily_mkt_ret, avoid_mask):
    """套 regime overlay: avoid_mask=True 的日子强制空仓.

    Returns (position_after_overlay, strategy_daily_return).
    仓位前移一天作用于当日收益 (避免未来函数: 用昨日定的仓位吃今日收益)。
    """
    pos = base_pos.copy()
    if avoid_mask is not None:
        pos = pos.where(~avoid_mask.reindex(pos.index).fillna(False), 0.0)
    strat_ret = pos.shift(1).fillna(0.0) * daily_mkt_ret
    return pos, strat_ret


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. 基准仓位: e20c「止盈无regime」的原始持仓序列 ──
    base = pd.read_csv(EXP_DIR / "equity_strat止盈.csv", parse_dates=["date"]).set_index("date")
    base_pos = base["position"].astype(float)
    oos_start, oos_end = base.index[0], base.index[-1]
    print(f"[oos] e20c OOS 期: {oos_start.date()} ~ {oos_end.date()} ({len(base)} 天)")

    # ── 2. 价格 → 市场日收益 (对齐 OOS) ──
    px = load_prices()["close"].astype(float)
    mkt_ret = px.pct_change()

    # ── 3. regime (在全历史上算, 再裁到 OOS, 保证 point-in-time) ──
    legacy_bear = regime_legacy(px) == 1                    # 老: 熊市=避险
    multi = regime_multidim(px)
    multi_off = multi["regime"] == 2                         # 新: risk_off=避险
    # 新方案变体: risk_off + neutral 都减仓 (更保守)
    multi_off_neu = multi["regime"] >= 1

    # 对齐到 OOS 区间
    idx = base_pos.index
    mkt_ret = mkt_ret.reindex(idx)

    # ── 4. 三种 overlay 回测 ──
    configs = {
        "无regime过滤 (纯止盈)": None,
        "老regime (63d≤-10%)": legacy_bear,
        "新regime (risk_off)": multi_off,
        "新regime (risk_off+neutral)": multi_off_neu,
    }

    rows = {}
    for name, mask in configs.items():
        pos, ret = apply_overlay(base_pos, mkt_ret, mask)
        rows[name] = perf_metrics(ret.dropna(), pos)

    # ── 5. 加 buy&hold 基准 ──
    bnh_ret = mkt_ret.dropna()
    rows["买入持有 (B&H)"] = perf_metrics(
        bnh_ret, pd.Series(1.0, index=bnh_ret.index)
    )

    df_out = pd.DataFrame(rows).T
    df_out.to_csv(OUT_DIR / "backtest_compare.csv")

    # ── 6. 控制台对比表 ──
    print("\n" + "=" * 92)
    print("Regime Overlay 回测对比  (e20c OOS, 止盈仓位为基准)")
    print("=" * 92)
    hdr = f"{'方案':<32}{'年化%':>8}{'Sharpe':>8}{'Sortino':>8}{'MaxDD%':>9}{'Calmar':>8}{'仓位%':>8}{'交易':>6}"
    print(hdr)
    print("-" * 92)
    for name, m in rows.items():
        print(f"{name:<30}{m['cagr']*100:>8.1f}{m['sharpe']:>8.2f}"
              f"{m['sortino']:>8.2f}{m['max_drawdown']*100:>9.1f}"
              f"{m['calmar']:>8.2f}{m['exposure']*100:>8.1f}{m['num_trades']:>6}")
    print("=" * 92)
    print(f"\n📄 已保存: {OUT_DIR / 'backtest_compare.csv'}")


if __name__ == "__main__":
    main()
