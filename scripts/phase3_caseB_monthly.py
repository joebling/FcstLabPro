#!/usr/bin/env python3
"""Phase 3 Case B: 月度配置回测 (降频, 非 21 天).

定位: 把 horizon 从"日频21天方向"改成"月度配置权重". 资产配置思路.
假设: 日频把链上慢信号切碎成噪音; 月频聚合后信噪比提升.

纪律 (样本仅 ~72 个月):
  - 严禁 ML / 过参数化, 只用纯规则 (MVRV-Z 相对分位 → 权重线性映射).
  - 防钝化: 用滚动分位 (本周期相对位置), 非绝对水位.
  - 防未来函数: 月初决策只用 <= 上月末 的数据 (shift).

对比基准: BuyHold (满仓) + 固定50%仓.
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

    # 月末价格 → 月度收益
    m_price = price.resample("ME").last()
    m_ret = m_price.pct_change().shift(-1)  # 本月持仓吃 本月末→下月末 收益

    # 指标月末值 (防未来: 用月末值决定下月仓位, 收益是下月的 → 对齐)
    mvrv = _load_series("mvrv_zscore_data", price.index).resample("ME").last()

    # MVRV-Z 本周期相对分位 (滚动24个月, 防钝化)
    rank = mvrv.rolling(24, min_periods=12).apply(
        lambda x: (x.iloc[-1] >= x).mean(), raw=False)

    # ── 策略: 逆向配置 — 估值分位越低, 权重越高 ──
    # weight = 1 - rank (分位0→满仓, 分位1→空仓), clip [0,1]
    w_contra = (1.0 - rank).clip(0, 1)

    # 基准
    w_bh = pd.Series(1.0, index=m_price.index)       # BuyHold
    w_half = pd.Series(0.5, index=m_price.index)     # 固定半仓

    def _strat_ret(w: pd.Series) -> pd.Series:
        w = w.reindex(m_ret.index).fillna(0.0)
        turnover = w.diff().abs().fillna(w.abs())
        return w * m_ret - turnover * args.cost

    strats = {
        "BuyHold": w_bh,
        "固定半仓": w_half,
        "逆向配置(1-rank)": w_contra,
    }
    res = {n: _monthly_stats(_strat_ret(w)) for n, w in strats.items()}

    n_months = int(m_ret.dropna().shape[0])
    print("\n" + "=" * 66)
    print("  Phase 3 Case B: 月度配置回测 (MVRV-Z 相对分位 → 权重)")
    print("=" * 66)
    print(f"  窗口: {m_price.index[0].date()}~{m_price.index[-1].date()} ({n_months}个月)")
    print(f"  再平衡成本: {args.cost:.1%}/边")
    print("-" * 66)
    print(f"  {'策略':<18}{'Sharpe':>9}{'MaxDD':>10}{'CAGR':>10}{'TotalRet':>12}")
    print("-" * 66)
    for n in strats:
        s = res[n]
        print(f"  {n:<18}{s['sharpe']:>9.2f}{s['max_dd']:>9.1%}"
              f"{s['cagr']:>10.1%}{s['total']:>11.0%}")
    print("-" * 66)

    bh, co = res["BuyHold"], res["逆向配置(1-rank)"]
    dd_imp = (abs(bh["max_dd"]) - abs(co["max_dd"])) / abs(bh["max_dd"]) if bh["max_dd"] else 0
    print(f"  ★ 逆向配置")
    print(f"     Sharpe: {bh['sharpe']:.2f}→{co['sharpe']:.2f} ({co['sharpe']-bh['sharpe']:+.2f})")
    print(f"     MaxDD: {bh['max_dd']:.1%}→{co['max_dd']:.1%} (改善 {dd_imp:+.1%})")
    verdict = "✅ 月度配置有价值" if (co["sharpe"] > bh["sharpe"] and dd_imp >= 0.10) else \
              "⚠️ 未显著优于 BuyHold"
    print(f"     判定: {verdict}")
    print("=" * 66 + "\n")


if __name__ == "__main__":
    main()
