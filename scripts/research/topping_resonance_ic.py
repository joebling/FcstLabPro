#!/usr/bin/env python3
"""逃顶指标"共振分"验证 (纯研究, 只读) — 多维共振 vs 单指标, 谁的 IC 更高?

回答: 用户"多维共振"的老炮直觉, 统计上到底值多少钱?

方法论 (诚实声明):
  - 【防未来函数·Layer 0】高位阈值用 expanding 扩展窗口历史百分位:
    每天只用 <= 当日数据判断"现在算不算历史高位", 而非全样本分位(那是作弊)。
  - 共振分 = 几个指标同时处于各自历史 >80 分位 (0~N 分)。
  - 【非重叠采样·§2.1】采样步长 = 预测窗口 h, 防 t-stat 虚高。
  - 检验共振分 vs future_return 的 Spearman IC, 与单指标基准对比。

入选指标 (上一步 IC 检验中方向正确的链上估值因子):
  Reserve Risk, MVRV-Z, LTH-NUPL, Puell, NUPL

用法:
    python scripts/research/topping_resonance_ic.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA = PROJECT_ROOT / "data"

COMPONENTS = {
    "Reserve Risk": "external/onchain/reserve_risk.csv",
    "MVRV-Z":       "external/onchain/mvrv_zscore_data.csv",
    "LTH-NUPL":     "external/onchain/lth_nupl.csv",
    "Puell":        "external/onchain/puell_multiple_data.csv",
    "NUPL":         "external/onchain/nupl_data.csv",
}

HORIZONS = [30, 90]
PCTL = 0.80          # 高位阈值: 历史 80 分位以上 = 亮红灯
MIN_HISTORY = 365    # 至少 1 年历史才开始判断分位 (避免冷启动噪音)


def load_price() -> pd.Series:
    df = pd.read_csv(DATA / "raw/btc_binance_BTCUSDT_1d.csv", parse_dates=["date"])
    return df.set_index("date").sort_index()["close"]


def load_series(rel: str) -> pd.Series:
    df = pd.read_csv(DATA / rel, parse_dates=["date"])
    s = df.set_index("date").sort_index()["value"]
    return s[~s.index.duplicated(keep="last")].dropna()


def expanding_pctl_flag(s: pd.Series, pctl: float, min_hist: int) -> pd.Series:
    """point-in-time 高位信号: 当前值 >= 截至当日的历史 pctl 分位 → 1, 否则 0。

    用 expanding rank, 严格只用 <= 当日数据 (无未来函数)。
    """
    # 每日的"当前值在历史中的百分位排名" (含当日, expanding)
    rank_pctl = s.expanding(min_periods=min_hist).apply(
        lambda w: (w <= w[-1]).mean(), raw=True
    )
    return (rank_pctl >= pctl).astype("float")


def ic_nonoverlap(sig: pd.Series, fwd: pd.Series, h: int):
    df = pd.concat([sig.rename("s"), fwd.rename("r")], axis=1).dropna()
    df = df.iloc[::h]
    n = len(df)
    if n < 8 or df["s"].nunique() < 2:
        return None
    ic, _ = spearmanr(df["s"], df["r"])
    if np.isnan(ic):
        return None
    t = ic * np.sqrt(n - 2) / np.sqrt(1 - ic**2) if abs(ic) < 1 else np.nan
    return {"ic": ic, "t": t, "n": n}


def main():
    price = load_price()

    # 构建各成分的 point-in-time 高位信号
    flags = {}
    for name, rel in COMPONENTS.items():
        s = load_series(rel)
        flags[name] = expanding_pctl_flag(s, PCTL, MIN_HISTORY)

    # 共振分 = 同日亮灯数 (对齐到所有成分都有数据的日期)
    flag_df = pd.DataFrame(flags).dropna()
    resonance = flag_df.sum(axis=1)  # 0~5 分

    print("=" * 90)
    print("逃顶'共振分'验证 — 多维共振 vs 单指标 (point-in-time, 无未来函数)")
    print(f"高位定义: expanding 历史 {PCTL:.0%} 分位以上 | 共振分范围 0~{len(COMPONENTS)}")
    print(f"覆盖区间: {flag_df.index[0].date()} ~ {flag_df.index[-1].date()} ({len(flag_df)}天)")
    print("=" * 90)
    # 共振分分布
    print("\n共振分分布(亮灯数:天数):", dict(resonance.astype(int).value_counts().sort_index()))

    print(f"\n{'信号':<16}{'窗口':>5}{'样本N':>6}{'RankIC':>9}{'t-stat':>8}{'判定':>14}")
    print("-" * 90)

    def verdict(ic, t):
        if abs(ic) < 0.02:
            return "❌噪音"
        if abs(t) < 1.0:
            return "⚠️不显著"
        if abs(t) >= 2.0:
            return "✅强(|t|≥2)"
        return "🟡弱有效"

    summary = {}
    for h in HORIZONS:
        fwd = price.shift(-h) / price - 1.0
        # 共振分
        res = ic_nonoverlap(resonance, fwd, h)
        if res:
            print(f"{'★共振分(0~5)':<16}{h:>4}d{res['n']:>6}{res['ic']:>+9.3f}"
                  f"{res['t']:>+8.2f}{verdict(res['ic'], res['t']):>14}")
            summary[(h, "共振分")] = res
        # 单指标基准
        for name in COMPONENTS:
            s = load_series(COMPONENTS[name]).reindex(flag_df.index).ffill()
            r = ic_nonoverlap(s, fwd, h)
            if r:
                print(f"{'  '+name:<16}{h:>4}d{r['n']:>6}{r['ic']:>+9.3f}"
                      f"{r['t']:>+8.2f}{verdict(r['ic'], r['t']):>14}")
                summary[(h, name)] = r
        print("-" * 90)

    # 关键对比: 共振分 vs 最强单指标
    print("\n【关键结论: 共振是否真的优于单指标?】")
    for h in HORIZONS:
        res_t = abs(summary.get((h, "共振分"), {}).get("t", 0))
        singles = {k[1]: abs(v["t"]) for k, v in summary.items()
                   if k[0] == h and k[1] != "共振分"}
        best_name = max(singles, key=singles.get)
        best_t = singles[best_name]
        winner = "共振分胜✅" if res_t >= best_t else f"单指标({best_name})胜"
        print(f"  {h}天: 共振分|t|={res_t:.2f}  vs  最强单指标({best_name})|t|={best_t:.2f}"
              f"  →  {winner}")

    print("\n【caveat】")
    print("  - expanding 分位已严格防未来函数; 但 90天非重叠样本 N≈30, 置信度仍有限。")
    print("  - 共振分用'同等权重投票', 未优化权重(避免过拟合, 手册§4.2)。")
    print("  - IC 衡量单调预测力; 共振分作为'分批撤退触发器'的实战价值需另做回测。")

    # 落盘
    out = PROJECT_ROOT / "experiments" / "research" / "topping_resonance.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.concat([flag_df, resonance.rename("共振分")], axis=1).to_csv(out)
    print(f"\n共振分时间序列已保存: {out.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
