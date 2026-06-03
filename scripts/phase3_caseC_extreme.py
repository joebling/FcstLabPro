#!/usr/bin/env python3
"""Phase 3 Case C: 极值二元择时回测 (事件驱动覆盖层).

定位: 纯规则, 平时不动, 只在极端时刻出手. 验证"水位极值"能否择时.
两套阈值:
  1. 固定阈值 (业界经验值): Puell>4 逃顶 / SOPR<1 抄底 / MVRV-Z>7 / MVRV-Z<0
     → 测钝化 (新周期还触不触发).
  2. 滚动分位 (防钝化): SOPR<p10 抄底 / MVRV-Z<p10 / Puell>p90 逃顶 / MVRV-Z>p90.

评估: 信号触发后 +63/+126 日的前向收益分布 vs 基线 (全样本同窗口收益).
纪律: 阈值用经验值或先验分位, 严禁在自己数据上调优.

用法:
    .venv/bin/python scripts/phase3_caseC_extreme.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _load_series(name: str, idx: pd.DatetimeIndex) -> pd.Series:
    s = pd.read_csv(f"data/external/onchain/{name}.csv",
                    parse_dates=["date"]).set_index("date")["value"]
    return s.reindex(idx, method="ffill")


def _fwd_ret(price: pd.Series, horizon: int) -> pd.Series:
    return price.shift(-horizon) / price - 1.0


def _eval_signal(mask: pd.Series, fwd: pd.Series, direction: str) -> dict:
    """direction='up' 期望上涨(抄底), 'down' 期望下跌(逃顶)."""
    sig = fwd[mask].dropna()
    if len(sig) == 0:
        return dict(n=0, median=np.nan, hit=np.nan)
    median = sig.median()
    hit = (sig > 0).mean() if direction == "up" else (sig < 0).mean()
    return dict(n=len(sig), median=median, hit=hit)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2018-01-01")
    args = ap.parse_args()

    price = pd.read_csv("data/raw/btc_binance_BTCUSDT_1d.csv",
                        parse_dates=["date"]).set_index("date")["close"]
    full_price = price.copy()
    price = price[price.index >= args.start]

    mvrv = _load_series("mvrv_zscore_data", price.index)
    puell = _load_series("puell_multiple_data", price.index)
    sopr = _load_series("sopr_data", price.index)

    # shift(1) 防未来: 当日收盘后才知指标
    mvrv_s, puell_s, sopr_s = mvrv.shift(1), puell.shift(1), sopr.shift(1)

    fwd63 = _fwd_ret(price, 63)
    fwd126 = _fwd_ret(price, 126)

    print("\n" + "=" * 70)
    print("  Phase 3 Case C: 极值二元择时回测")
    print("=" * 70)
    print(f"  窗口: {price.index[0].date()}~{price.index[-1].date()}")

    # 基线: 全样本前向收益
    base63 = (fwd63.dropna() > 0).mean()
    base126 = (fwd126.dropna() > 0).mean()
    print(f"  基线上涨率: +63日 {base63:.0%} | +126日 {base126:.0%}")
    print("-" * 70)

    # ── 1. 固定阈值 (测钝化) ──
    print("  [1] 固定阈值 (业界经验值) — 测钝化:")
    fixed = [
        ("Puell>4 逃顶", puell_s > 4, "down"),
        ("MVRV-Z>7 逃顶", mvrv_s > 7, "down"),
        ("SOPR<1 抄底", sopr_s < 1.0, "up"),
        ("MVRV-Z<0 抄底", mvrv_s < 0, "up"),
    ]
    for name, mask, d in fixed:
        n_oos = int(mask.fillna(False).sum())
        print(f"     {name:<16} OOS触发 {n_oos:>4} 天"
              f" {'❌钝化(几乎不触发)' if n_oos < 20 else ''}")
    print("-" * 70)

    # ── 2. 滚动分位 (防钝化) ──
    print("  [2] 滚动分位 (rolling 365d p10/p90) — 防钝化:")
    print(f"     {'信号':<18}{'窗口':>6}{'N':>6}{'中位':>9}{'命中':>8}  判定")
    win = 365

    def _roll_q(s: pd.Series, q: float) -> pd.Series:
        return s.rolling(win, min_periods=180).quantile(q)

    sig_defs = [
        ("SOPR<p10 抄底", sopr_s < _roll_q(sopr_s, 0.10), "up"),
        ("MVRV-Z<p10 抄底", mvrv_s < _roll_q(mvrv_s, 0.10), "up"),
        ("Puell>p90 逃顶", puell_s > _roll_q(puell_s, 0.90), "down"),
        ("MVRV-Z>p90 逃顶", mvrv_s > _roll_q(mvrv_s, 0.90), "down"),
    ]
    for name, mask, d in sig_defs:
        for hz, fwd, base in [("+63", fwd63, base63), ("+126", fwd126, base126)]:
            r = _eval_signal(mask.fillna(False), fwd, d)
            if r["n"] == 0:
                continue
            base_hit = base if d == "up" else 1 - base
            edge = r["hit"] - base_hit
            verdict = ("✅" if edge > 0.10 else
                       "❌反向" if r["hit"] < 0.45 else "⚠️弱")
            print(f"     {name:<18}{hz:>6}{r['n']:>6}"
                  f"{r['median']:>8.1%}{r['hit']:>8.0%}  {verdict}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
