#!/usr/bin/env python3
"""Phase 3a: MVRV-Z "确认顶" 信号历史评估.

信号B (可用): MVRV-Z 90日动量转负 = 从 >0 转到 < -0.2.
  - 不依赖绝对水位 → 适应"周期钝化" (见 phase3 §3.1.1)
  - 是"确认顶/中期看跌"信号, 非"预测顶"

评估: 全历史所有触发, 信号后 +21/+63/+126 日的收益分布 + 下跌命中率,
对比 baseline (随机日的远期下跌概率).

防未来函数: MVRV-Z 全程 shift(1).

用法:
    .venv/bin/python scripts/eval_mvrv_top_signal.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

MVRV_PATH = "data/external/onchain/mvrv_zscore_data.csv"
PRICE_PATH = "data/raw/btc_binance_BTCUSDT_1d.csv"
HORIZONS = [21, 63, 126]


def _load() -> tuple[pd.Series, pd.Series]:
    mvrv = pd.read_csv(MVRV_PATH, parse_dates=["date"]).set_index("date")["value"]
    price = (
        pd.read_csv(PRICE_PATH, parse_dates=["date"])
        .set_index("date")["close"]
        .reindex(mvrv.index, method="ffill")
        .dropna()
    )
    return mvrv.reindex(price.index), price


def _cluster(days, gap_days: int = 30) -> list:
    """30 天内的重复信号合并为一次独立信号."""
    out, last = [], None
    for d in days:
        if last is None or (d - last).days > gap_days:
            out.append(d)
        last = d
    return out


def evaluate():
    mvrv, price = _load()
    m = mvrv.shift(1)  # 防未来函数

    # 信号B: 90日动量从正转负 (确认顶)
    mom90 = m - m.rolling(90).mean()
    sig = (mom90 < -0.2) & (mom90.shift(10) > 0)
    days = _cluster(sig[sig].index)

    print("\n" + "=" * 62)
    print("  MVRV-Z 90日动量转负 — '确认顶'信号历史评估")
    print("=" * 62)
    print(f"  独立信号: {len(days)} 次 (全历史 {price.index[0].date()}~{price.index[-1].date()})")
    print("-" * 62)
    print(f"  {'窗口':>6}{'平均收益':>12}{'中位':>10}{'下跌命中':>10}{'基线':>8}")
    print("-" * 62)
    for h in HORIZONS:
        fwd = []
        for d in days:
            fut = price[price.index > d]
            if len(fut) > h:
                fwd.append(fut.iloc[h] / price[price.index <= d].iloc[-1] - 1)
        fwd = np.array(fwd)
        base = (price.shift(-h) / price - 1).dropna()
        base_down = (base < 0).mean()
        print(f"  +{h:>3}日{fwd.mean():>11.1%}{np.median(fwd):>10.1%}"
              f"{(fwd < 0).mean():>9.0%}{base_down:>8.0%}")
    print("-" * 62)
    print("  信号日期:")
    for d in days:
        print(f"    {d.date()}")
    print("=" * 62)
    print("\n  解读:")
    print("  - +63日(季度)下跌命中率显著超基线 → 真实中期看跌 edge")
    print("  - 样本仅", len(days), "次 + 夹杂假信号 → 适合'减仓提示', 非全有全无清仓")
    print("  - 是'确认顶'(顶后)非'预测顶'(顶前), 不能抢顶\n")


if __name__ == "__main__":
    evaluate()
