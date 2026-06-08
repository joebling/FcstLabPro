#!/usr/bin/env python3
"""分析 e20c 在单边上涨中的行为 (纯研究, 不碰生产).

核心问题: e20c 标签 = "价格<SMA50 且 RSI<45 时, 赌未来21天反弹4%"。
单边上涨时价格一直在 SMA50 上方、RSI 高 → 入场条件不满足 → 模型踏空。

本脚本量化这个"踏空"现象, 用 2022-2025 及更早的上涨周期数据说明。

用法:
    python scripts/research/e20c_uptrend_behavior.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def rsi(close, window=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window).mean()
    return 100 - 100 / (1 + gain / loss)


def main():
    raw = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"
    df = pd.read_csv(raw, index_col=0).sort_index()
    df.index = pd.to_datetime(df.index)
    close = df["close"].astype(float)

    sma50 = close.rolling(50).mean()
    r = rsi(close, 14)

    # e20c 入场门槛: 价格 < SMA50 且 RSI < 45
    entry_ok = (close < sma50) & (r < 45)
    # 上涨标记: 价格在 SMA50 上方
    above_ma = close > sma50

    periods = {
        "2020-2021 大牛市": ("2020-10-01", "2021-04-15"),
        "2023 复苏年": ("2023-01-01", "2023-12-31"),
        "2024 新高年": ("2024-01-01", "2024-12-31"),
        "2025 全年": ("2025-01-01", "2025-12-31"),
        "全样本": (str(close.index[0].date()), str(close.index[-1].date())),
    }

    print("=" * 90)
    print("e20c 入场门槛 (价格<SMA50 且 RSI<45) 在各周期的满足率")
    print("=" * 90)
    print(f"{'周期':<22}{'天数':>7}{'可入场天':>10}{'占比':>8}{'区间涨幅':>11}{'在MA上方':>11}")
    print("-" * 90)

    rows = []
    for name, (s, e) in periods.items():
        seg = close.loc[s:e]
        if len(seg) < 2:
            continue
        n = len(seg)
        n_entry = int(entry_ok.loc[s:e].sum())
        ret = seg.iloc[-1] / seg.iloc[0] - 1
        pct_above = float(above_ma.loc[s:e].mean())
        entry_pct = n_entry / n * 100
        print(f"{name:<22}{n:>7}{n_entry:>10}{entry_pct:>7.1f}%"
              f"{ret*100:>10.0f}%{pct_above*100:>10.0f}%")
        rows.append({
            "period": name, "days": n, "entry_days": n_entry,
            "entry_pct": round(entry_pct, 1), "return_pct": round(ret * 100, 1),
            "pct_above_ma": round(pct_above * 100, 1),
        })

    print("=" * 90)

    # ── 深入: 上涨主升段, 模型能出手的日子有多少 ──
    print("\n" + "=" * 90)
    print("关键洞察: 上涨周期里, 模型「能出手的日子」少得可怜 (结构性踏空)")
    print("=" * 90)

    bull_s, bull_e = "2023-01-01", "2025-11-23"
    seg = close.loc[bull_s:bull_e]
    n_entry = int(entry_ok.loc[bull_s:bull_e].sum())
    bnh = (seg.iloc[-1] / seg.iloc[0] - 1) * 100
    miss_pct = 100 - n_entry / len(seg) * 100

    print(f"  区间: {bull_s} ~ {bull_e}")
    print(f"  买入持有涨幅: {bnh:+.0f}%")
    print(f"  总天数: {len(seg)}")
    print(f"  可入场天数: {n_entry}")
    print(f"  踏空天数占比: {miss_pct:.0f}% (这些天模型根本不出手)")
    print("=" * 90)

    out = pd.DataFrame(rows)
    out_dir = PROJECT_ROOT / "experiments" / "research" / "regime"
    out_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_dir / "e20c_uptrend_entry_rate.csv", index=False)
    print(f"\n📄 已保存: {out_dir / 'e20c_uptrend_entry_rate.csv'}")


if __name__ == "__main__":
    main()
