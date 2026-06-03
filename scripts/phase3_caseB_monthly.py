#!/usr/bin/env python3
"""Phase 3 Case B: 月度配置回测 (降频, 非 21 天).

定位: 把 horizon 从"日频21天方向"改成"月度配置权重". 资产配置思路.
假设: 日频把链上慢信号切碎成噪音; 月频聚合后信噪比提升.

纪律 (样本仅 ~100 个月):
  - 严禁 ML / 过参数化, 只用纯规则 (动量符号 / 相对分位 → 权重).
  - 防钝化: 用动量(方向) 或滚动分位, 非绝对水位.
  - 防未来函数: 月末值决定下月仓位, 收益是下月的 (shift -1 对齐).

对比基准: BuyHold (满仓) + 固定50%仓 + 逆向水位 (反例).
评估: 月度收益序列的 Sharpe / MaxDD / CAGR.

用法:
    .venv/bin/python scripts/phase3_caseB_monthly.py
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


def _monthly_stats(monthly_ret: pd.Series) -> dict:
    r = monthly_ret.dropna().values
    if len(r) == 0:
        return dict(sharpe=0, max_dd=0, cagr=0, total=0)
    cum = np.cumprod(1 + r)
    total = cum[-1] - 1
    yrs = len(r) / 12.0
    cagr = (1 + total) ** (1 / yrs) - 1 if yrs > 0 else 0
    sh = np.mean(r) / np.std(r) * np.sqrt(12) if np.std(r) > 0 else 0
    dd = ((cum - np.maximum.accumulate(cum)) / np.maximum.accumulate(cum)).min()
    return dict(sharpe=sh, max_dd=dd, cagr=cagr, total=total)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cost", type=float, default=0.002, help="月度再平衡单边成本")
    ap.add_argument("--start", default="2018-01-01")
    args = ap.parse_args()

    price = pd.read_csv("data/raw/btc_binance_BTCUSDT_1d.csv",
                        parse_dates=["date"]).set_index("date")["close"]
    price = price[price.index >= args.start]

    # 月末价格 → 月度收益. 本月持仓(月末决定)吃 本月末→下月末 收益
    m_price = price.resample("ME").last()
    m_ret = m_price.pct_change().shift(-1)

    # 指标月末值. diff(N)>0 = 近 N 月上升趋势 (动量).
    #   用 diff 而非 pct_change: MVRV-Z 可为负, pct_change 有符号陷阱.
    mvrv = _load_series("mvrv_zscore_data", price.index).resample("ME").last()
    puell = _load_series("puell_multiple_data", price.index).resample("ME").last()
    sopr = _load_series("sopr_data", price.index).resample("ME").last()

    def _mom_w(series: pd.Series, n: int) -> pd.Series:
        """动量符号 → 满仓/空仓. 月末值决定, 不偷看未来."""
        return (series.diff(n) > 0).astype(float)

    def _price_mom_w(n: int) -> pd.Series:
        return (m_price.pct_change(n) > 0).astype(float)

    # 逆向水位 (反例): 滚动24月相对分位, 分位越低权重越高
    rank = mvrv.rolling(24, min_periods=12).apply(
        lambda x: (x.iloc[-1] >= x).mean(), raw=False)
    w_contra = (1.0 - rank).clip(0, 1)

    def _strat_ret(w: pd.Series) -> pd.Series:
        w = w.reindex(m_ret.index).fillna(0.0)
        turnover = w.diff().abs().fillna(w.abs())
        return w * m_ret - turnover * args.cost

    n_months = int(m_ret.dropna().shape[0])
    print("\n" + "=" * 70)
    print("  Phase 3 Case B: 月度配置回测 (动量 vs 水位)")
    print("=" * 70)
    print(f"  窗口: {m_price.index[0].date()}~{m_price.index[-1].date()} "
          f"({n_months}个月) | 再平衡成本: {args.cost:.1%}/边")

    # ── 主对比表 ──
    bh = pd.Series(1.0, index=m_price.index)
    half = pd.Series(0.5, index=m_price.index)
    main_strats = {
        "BuyHold": bh,
        "固定半仓": half,
        "逆向水位(1-rank)": w_contra,
        "MVRV-Z动量(3M>0)": _mom_w(mvrv, 3),
        "价格趋势(3M>0)": _price_mom_w(3),
    }
    print("-" * 70)
    print(f"  {'策略':<20}{'Sharpe':>9}{'MaxDD':>10}{'CAGR':>10}{'TotalRet':>12}")
    print("-" * 70)
    res = {}
    for n, w in main_strats.items():
        s = _monthly_stats(_strat_ret(w))
        res[n] = s
        print(f"  {n:<20}{s['sharpe']:>9.2f}{s['max_dd']:>9.1%}"
              f"{s['cagr']:>10.1%}{s['total']:>11.0%}")
    print("-" * 70)

    # ── 稳健性: MVRV-Z 动量窗口扫描 ──
    print("  稳健性扫描 — MVRV-Z 动量窗口 (防单点甜蜜点):")
    win_sh = []
    for nw in (2, 3, 4, 6):
        sh = _monthly_stats(_strat_ret(_mom_w(mvrv, nw)))["sharpe"]
        win_sh.append((nw, sh))
        print(f"     {nw}月窗口: Sharpe {sh:.2f}")

    # ── 指标横向 (同 3M 动量逻辑) ──
    print("  指标横向 — 同 3M 动量逻辑:")
    cross = {"MVRV-Z": mvrv, "Puell": puell, "SOPR": sopr}
    cross_sh = {}
    for n, ser in cross.items():
        sh = _monthly_stats(_strat_ret(_mom_w(ser, 3)))["sharpe"]
        cross_sh[n] = sh
        print(f"     {n}: Sharpe {sh:.2f}")
    print("-" * 70)

    # ── 判定 ──
    bh_sh = res["BuyHold"]["sharpe"]
    mv_sh = res["MVRV-Z动量(3M>0)"]["sharpe"]
    pr_sh = res["价格趋势(3M>0)"]["sharpe"]
    co_sh = res["逆向水位(1-rank)"]["sharpe"]
    print(f"  ★ 判定:")
    print(f"     动量 vs 水位: MVRV动量 {mv_sh:.2f} vs 逆向水位 {co_sh:.2f}"
          f" → {'动量胜✅' if mv_sh > co_sh else '存疑'}")
    print(f"     胜过BuyHold: {mv_sh:.2f} vs {bh_sh:.2f}"
          f" → {'✅' if mv_sh > bh_sh else '❌未胜出'}")
    print(f"     链上 vs 纯价格: MVRV动量 {mv_sh:.2f} vs 价格趋势 {pr_sh:.2f}"
          f" → {'链上有增量✅' if mv_sh > pr_sh else '无增量(纯价格已够)'}")
    sh_only = [s for _, s in win_sh]
    plateau = max(sh_only) - min(sh_only[1:]) if len(sh_only) > 1 else 0
    print(f"     窗口稳健: 3/4/6月 Sharpe 跨度 {plateau:.2f}"
          f" {'(plateau✅)' if plateau < 0.10 else '(单点敏感⚠️)'}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
