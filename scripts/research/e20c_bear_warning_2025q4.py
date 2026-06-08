#!/usr/bin/env python3
"""回测 e20c regime 开关在 2025-10-06 牛市结束前后的反应 (纯研究, 只读).

复刻生产逻辑 scripts/live_signal.py::is_bear_market:
    规则: 63 天滚动收益率 <= -10% -> 熊市 (策略静默/强制平仓)

问题: e20c 在 2025-10-06 (上轮牛市宣告结束) 前一个月发出警告吗?

用法:
    python scripts/research/e20c_bear_warning_2025q4.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    csv = PROJECT_ROOT / "data/raw/btc_binance_BTCUSDT_1d.csv"
    df = pd.read_csv(csv, parse_dates=["date"]).set_index("date").sort_index()

    close = df["close"]
    window = 63
    threshold = -0.10

    roll_ret = close / close.shift(window) - 1.0
    is_bear = roll_ret <= threshold

    high_90 = close.rolling(90).max()
    dd_from_90 = close / high_90 - 1.0
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()

    start = pd.Timestamp("2025-09-06")
    end = pd.Timestamp("2025-10-20")
    win = df.loc[start:end]

    print("=" * 92)
    print("e20c regime 开关逆应回测 — 2025-10-06 牛市结束前后")
    print(f"规则: 63天滚动收益 <= {threshold:.0%} -> 熊市 (策略静默/平仓)")
    print("=" * 92)
    print(f"{'日期':<12}{'收盘':>10}{'63d收益':>10}{'距90d高':>9}"
          f"{'vsSMA50':>9}{'vsSMA200':>10}  {'regime':<7}信号")
    print("-" * 92)

    first_bear_date = None
    for d, row in win.iterrows():
        c = row["close"]
        rr = roll_ret.loc[d]
        dd = dd_from_90.loc[d]
        v50 = c / sma50.loc[d] - 1.0
        v200 = c / sma200.loc[d] - 1.0
        bear = bool(is_bear.loc[d])
        if bear and first_bear_date is None:
            first_bear_date = d
        regime = "熊市" if bear else "非熊市"
        sig = "警告/静默" if bear else "可交易"
        mark = "  <- 10-06" if d == pd.Timestamp("2025-10-06") else ""
        print(f"{str(d.date()):<12}{c:>10.0f}{rr:>+10.1%}{dd:>+9.1%}"
              f"{v50:>+9.1%}{v200:>+10.1%}  {regime:<7}{sig}{mark}")

    print("-" * 92)
    print("\n【结论】")
    target = pd.Timestamp("2025-10-06")
    one_month_before = target - pd.Timedelta(days=30)
    if first_bear_date is not None:
        lead = (target - first_bear_date).days
        when = "提前" if lead > 0 else "滞后"
        print(f"  窗口内首次转熊日期 : {first_bear_date.date()}")
        print(f"  相对 10-06        : {when} {abs(lead)} 天")
        if first_bear_date <= one_month_before:
            print("  结果: 在 10-06 前一个月 (<=09-06) 已发出熊市警告")
        elif first_bear_date < target:
            print("  结果: 在 10-06 前发出警告, 但不足一个月")
        else:
            print("  结果: 10-06 当日或之后才转熊, 未提前预警")
    else:
        print("  窗口期内 regime 开关始终未触发熊市 (从未发出警告)")

    # ---- 明确信号分析: 10-06 之后到数据末尾, 找连续>=5天的稳定熊市 ----
    print("\n【明确信号分析: 10-06 之后】")
    sub = df.loc[target:]
    br = is_bear.reindex(sub.index).fillna(False)
    runs = []
    cur = 0
    run_start = None
    for d in sub.index:
        if br.loc[d]:
            if cur == 0:
                run_start = d
            cur += 1
        else:
            if cur > 0:
                runs.append((run_start, cur))
                cur = 0
    if cur > 0:
        runs.append((run_start, cur))

    for s, n in runs:
        if n >= 5:
            tag = "<-- 明确信号(连续>=5天)"
        elif n >= 3:
            tag = "(>=3天)"
        else:
            tag = "抖动(噪音)"
        print(f"  {s.date()} 起 连续 {n:>2} 天  {tag}")

    stable = [(s, n) for s, n in runs if n >= 5]
    if stable:
        d0, n0 = stable[0]
        lead = (d0 - target).days
        peak = close.loc[target]
        dd = close.loc[d0] / peak - 1.0
        print(f"\n  首个明确信号 : {d0.date()} (10-06 后第 {lead} 天)")
        print(f"  当时价格     : {close.loc[d0]:.0f} (距 10-06 顶部 {peak:.0f} 已 {dd:+.1%})")
        print(f"  解读: regime 开关是滞后防御工具, 明确确认深熊时已距顶 {abs(dd):.0%}, 无法逃顶。")


if __name__ == "__main__":
    main()
