#!/usr/bin/env python3
"""BTC 四年周期 + 振幅衰减研究 (纯研究, 只读).

核心观点 (2026-06-05 研究):
  - 节奏重复: 顶到顶/底到底间隔稳定在 3.90-3.94 年
  - 幅度衰减: 底→顶涨幅 130x→21x→7.9x, 呈阻尼振荡
  - 减半→顶: 三轮均在减半后 17.5-18.2 个月见顶

用法:
    python scripts/research/btc_cycle_analysis.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── 公认关键节点 ──────────────────────────────────────────────
TOPS = {
    2017: (pd.Timestamp("2017-12-17"), 19_783),
    2021: (pd.Timestamp("2021-11-08"), 67_526),
    2025: (pd.Timestamp("2025-10-06"), 124_659),
}
BOTTOMS = {
    2015: (pd.Timestamp("2015-01-14"),    152),
    2018: (pd.Timestamp("2018-12-15"),  3_212),
    2022: (pd.Timestamp("2022-11-21"), 15_781),
}
HALVINGS = {
    2016: pd.Timestamp("2016-07-09"),
    2020: pd.Timestamp("2020-05-11"),
    2024: pd.Timestamp("2024-04-20"),
}
CYCLES = [
    dict(name="周期1(2015-2018)", bot=2015, top=2017, halving=2016),
    dict(name="周期2(2018-2022)", bot=2018, top=2021, halving=2020),
    dict(name="周期3(2022-2025)", bot=2022, top=2025, halving=2024),
]


def sep(char="-", n=72):
    print(char * n)


def main():
    df = pd.read_csv(
        PROJECT_ROOT / "data/raw/btc_binance_BTCUSDT_1d.csv",
        parse_dates=["date"],
    ).set_index("date").sort_index()
    c = df["close"]

    print("=" * 72)
    print("BTC 四年周期研究 — 节奏重复 & 振幅衰减验证")
    print("=" * 72)

    # ── 1. 顶到顶 / 底到底 间隔 ──────────────────────────────
    print("\n【1】顶到顶 / 底到底 间隔")
    sep()
    t17, _ = TOPS[2017]
    t21, _ = TOPS[2021]
    t25, _ = TOPS[2025]
    b18, _ = BOTTOMS[2018]
    b22, _ = BOTTOMS[2022]

    intervals = [
        ("顶→顶", "2017→2021", (t21 - t17).days),
        ("顶→顶", "2021→2025", (t25 - t21).days),
        ("底→底", "2018→2022", (b22 - b18).days),
    ]
    print(f"{'类型':<8}{'区间':<12}{'天数':>6}{'年':>7}")
    sep()
    for typ, rng, days in intervals:
        print(f"{typ:<8}{rng:<12}{days:>6}{days/365:>7.2f}")
    print(f"\n  >> 均落在 3.90-3.94 年, 误差 < 2 周 — 节奏极稳")

    # ── 2. 减半 → 顶部 ───────────────────────────────────────
    print("\n【2】减半 → 之后顶部 (周期论核心)")
    sep()
    halv_top = [
        ("2016减半→2017顶", HALVINGS[2016], t17),
        ("2020减半→2021顶", HALVINGS[2020], t21),
        ("2024减半→2025顶", HALVINGS[2024], t25),
    ]
    print(f"{'区间':<22}{'天数':>6}{'月数':>7}")
    sep()
    for name, hd, td in halv_top:
        days = (td - hd).days
        print(f"{name:<22}{days:>6}{days/30:>7.1f}")
    print(f"\n  >> 三轮均在减半后 17.5-18.2 个月见顶")

    # ── 3. 底→顶 涨幅 (振幅衰减) ─────────────────────────────
    print("\n【3】底→顶 涨幅倍数 (振幅衰减)")
    sep()
    print(f"{'周期':<16}{'底价':>10}{'顶价':>10}{'涨幅':>8}{'是上轮的':>10}")
    sep()
    prev_mult = None
    for cyc in CYCLES:
        bot_d, bot_p = BOTTOMS[cyc["bot"]]
        top_d, top_p = TOPS[cyc["top"]]
        mult = top_p / bot_p
        decay = f"{mult/prev_mult:.0%}" if prev_mult else "—"
        print(f"{cyc['name']:<16}{bot_p:>10,.0f}{top_p:>10,.0f}"
              f"{mult:>7.1f}x{decay:>10}")
        prev_mult = mult
    print(f"\n  >> 130x → 21x → 7.9x, 典型阻尼振荡")
    print(f"  >> 涨幅递减但非线性: 衰减率本身也在变(16%→38%)")

    # ── 4. 顶→底 回撤深度 (熊市也在变浅) ────────────────────
    print("\n【4】顶→底 回撤深度 (熊市变浅趋势)")
    sep()
    bear_draws = [
        ("周期1顶→底", TOPS[2017][1], BOTTOMS[2018][1]),
        ("周期2顶→底", TOPS[2021][1], BOTTOMS[2022][1]),
    ]
    for name, tp, bp in bear_draws:
        print(f"  {name}: {bp/tp-1:+.0%}")
    print(f"\n  >> -84% → -77%, 熊市深度也在收敛")
    print(f"  >> 周期3顶→底尚未完成, 持续观察")

    # ── 5. 数据内实测 (确认数据和业界公认一致) ──────────────
    print("\n【5】数据内验证 (2018-01 起)")
    sep()
    for cyc in CYCLES[1:]:  # 周期1顶在2017年底, 数据覆盖不全
        s, e = TOPS[cyc["top"]][0] - pd.Timedelta(days=180), \
               TOPS[cyc["top"]][0] + pd.Timedelta(days=30)
        sub = c.loc[s:e]
        actual_top = sub.idxmax()
        actual_price = sub.max()
        stated_price = TOPS[cyc["top"]][1]
        match = "✅" if abs(actual_price - stated_price) < 500 else "⚠️"
        print(f"  {cyc['name']}: 数据顶 {actual_top.date()} "
              f"${actual_price:,.0f} {match}")

    # ── 6. 结论 & 实用启示 ────────────────────────────────────
    print("\n【结论】")
    sep("=")
    print("  核心观点 (数据支持):")
    print("    ✅ 节奏重复: 顶到顶/底到底均约 3.90-3.94 年")
    print("    ✅ 幅度衰减: 底→顶涨幅 130x→21x→7.9x (阻尼振荡)")
    print("    ✅ 减半→顶: 三轮均在 17.5-18.2 个月, 极稳")
    print()
    print("  统计 caveat (保持清醒):")
    print("    ⚠️ N=3, 无法排除巧合; 第4轮可能范式转移")
    print("    ⚠️ 衰减率不稳定, 无法精确预测下轮涨幅")
    print("    ⚠️ ETF/国家储备等新变量可能打破节奏")
    print()
    print("  实用建议:")
    print("    → 把周期当'贝叶斯先验'(季节感), 不当精确时钟")
    print("    → 减半后12-18个月提高警戒, 结合实时波动率动态调仓")
    print("    → 每轮顶部能赚的倍数越来越小, 仓位管理比择时更重要")
    sep("=")


if __name__ == "__main__":
    main()
