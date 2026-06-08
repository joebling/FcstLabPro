#!/usr/bin/env python3
"""逃顶工具大比拼 — 谁能在 2025-10-06 BTC 顶部 ($124,659) 附近最快退出 (纯研究, 只读).

对比常见退出/择时工具在真实顶部的反应速度。所有指标均为 point-in-time 因果计算,
仅用 <= 当日数据, 无未来函数。

工具清单:
  1. regime开关(基线)  : 63天滚动收益 <= -10%
  2. 跌破SMA50          : 收盘 < 50日均线
  3. 跌破SMA20          : 收盘 < 20日均线
  4. 吊灯止损ATR(3x)    : 收盘 < (滚动最高 - 3*ATR22)
  5. 动量背离(MACD)     : MACD柱状图 由正转负
  6. 回撤止损(-10%)     : 距滚动最高点回撤 <= -10%
  7. RSI高位回落        : RSI 从 >70 跌破 70

用法:
    python scripts/research/exit_tools_2025top.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def rsi(close, n=14):
    delta = close.diff()
    up = delta.clip(lower=0).rolling(n).mean()
    dn = (-delta.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def atr(df, n=22):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def first_trigger_after(signal, start, idx):
    """返回 signal 在 start(含)之后首个 True 的日期, 无则 None."""
    s = signal.reindex(idx).fillna(False)
    after = s.loc[start:]
    hits = after[after]
    return hits.index[0] if len(hits) else None


def main():
    csv = PROJECT_ROOT / "data/raw/btc_binance_BTCUSDT_1d.csv"
    df = pd.read_csv(csv, parse_dates=["date"]).set_index("date").sort_index()
    c = df["close"]

    top = pd.Timestamp("2025-10-06")
    top_price = c.loc[top]

    # --- 各工具的'退出信号'布尔序列 ---
    sigs = {}

    # 1. regime 基线
    sigs["1.regime开关(63d≤-10%)"] = (c / c.shift(63) - 1.0) <= -0.10

    # 2. 跌破 SMA50
    sma50 = c.rolling(50).mean()
    sigs["2.跌破SMA50"] = c < sma50

    # 3. 跌破 SMA20
    sma20 = c.rolling(20).mean()
    sigs["3.跌破SMA20"] = c < sma20

    # 4. 吊灯止损 (滚动22日最高 - 3*ATR22)
    a = atr(df, 22)
    chand = c.rolling(22).max() - 3 * a
    sigs["4.吊灯止损ATR(3x)"] = c < chand

    # 5. MACD 柱状图由正转负
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal_line = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal_line
    sigs["5.MACD柱转负"] = (hist < 0) & (hist.shift(1) >= 0)

    # 6. 回撤止损 (距滚动最高 -10%)
    roll_max = c.cummax()
    sigs["6.回撤止损(-10%)"] = (c / roll_max - 1.0) <= -0.10

    # 7. RSI 从 >70 跌破 70
    r = rsi(c, 14)
    sigs["7.RSI高位回落(破70)"] = (r < 70) & (r.shift(1) >= 70)

    # --- 评估: 每个工具在 top 之后首次触发 ---
    print("=" * 88)
    print(f"逃顶工具大比拼 — 真实顶部 2025-10-06 (${top_price:,.0f})")
    print("评判: top 之后越早触发 + 触发时距顶跌幅越小 = 越好")
    print("=" * 88)
    print(f"{'工具':<24}{'首次触发':>12}{'滞后天':>7}{'触发价':>10}{'距顶':>8}")
    print("-" * 88)

    rows = []
    for name, sig in sigs.items():
        d = first_trigger_after(sig, top, df.index)
        if d is None:
            print(f"{name:<24}{'未触发':>12}{'-':>7}{'-':>10}{'-':>8}")
            continue
        lead = (d - top).days
        price = c.loc[d]
        dd = price / top_price - 1.0
        rows.append((name, d, lead, dd))
        print(f"{name:<24}{str(d.date()):>12}{lead:>7}{price:>10.0f}{dd:>+8.1%}")

    print("-" * 88)
    # 排名: 距顶跌幅最小(越接近0越好)
    rows.sort(key=lambda x: x[3], reverse=True)
    print("\n【排名: 距顶跌幅最小(逃得最高) = 最优】")
    for i, (name, d, lead, dd) in enumerate(rows, 1):
        medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f" {i}."
        print(f"  {medal} {name:<24} {d.date()} 滞后{lead}天 距顶{dd:+.1%}")

    print("\n【解读】")
    print("  - regime开关(基线)是所有工具里最慢的之一, 印证它'深熊静音'而非'逃顶'的定位。")
    print("  - 短周期工具(SMA20/MACD/RSI)反应快但易假信号; 长周期(SMA50/regime)稳但滞后。")
    print("  - 注: 本表只看'首次触发速度', 未含假信号率/胜率, 不能直接当策略。")


if __name__ == "__main__":
    main()
