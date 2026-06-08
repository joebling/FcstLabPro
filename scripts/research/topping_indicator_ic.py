#!/usr/bin/env python3
"""逃顶指标单因子 IC 检验 (纯研究, 只读) — 用 t-stat 而非故事判断 alpha.

按 FcstLabPro 手册规范检验"五维逃顶框架"里能拿到干净数据的指标:
是否真有预测力, 还是事后叙事/幸存者偏差。

方法论 (诚实声明, 见手册 §2):
  - 单资产时间序列, 无横截面 → 用 signal[t] vs future_return[t→t+h] 的 Spearman。
  - 【防作弊·手册§2.1】非重叠采样: 采样步长 = 预测窗口 h, 避免重叠虚高 t-stat。
  - 【方向锁定·手册§2.2】逃顶指标理论方向 = 负 IC (指标越高→未来越跌),
    预先声明, 不事后反推符号 (否则就是 data snooping)。
  - t-stat = IC * sqrt(N-2) / sqrt(1-IC²), N = 非重叠样本数。

门槛 (手册 §3.3):
  - |Rank IC| > 0.02 才算有价值; |t-stat| > 1.0 才算显著。

用法:
    python scripts/research/topping_indicator_ic.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA = PROJECT_ROOT / "data"

# 指标清单: name -> (csv路径, 列名, 理论方向)
# 理论方向: -1 = 逃顶指标(越高越看跌, 预期负IC); +1 = 抄底指标(越高越看涨)
INDICATORS = {
    "MVRV-Z分数":        ("external/onchain/mvrv_zscore_data.csv", "value", -1),
    "NUPL(净未实现盈亏)":  ("external/onchain/nupl_data.csv",        "value", -1),
    "SOPR(花费产出利润)":  ("external/onchain/sopr_data.csv",        "value", -1),
    "Puell倍数(矿工营收)": ("external/onchain/puell_multiple_data.csv", "value", -1),
    "Reserve Risk":      ("external/onchain/reserve_risk.csv",     "value", -1),
    "LTH-NUPL(长持)":     ("external/onchain/lth_nupl.csv",         "value", -1),
    "资金费率(均值)":      ("external/funding_rate_BTCUSDT.csv", "funding_rate_mean", -1),
    "恐惧贪婪指数":        ("external/fear_greed_index.csv",         "fgi_value", -1),
    "DXY(美元指数)":      ("external/macro_factors.csv",            "dxy_close", -1),
    "美债10年(TNX)":      ("external/macro_factors.csv",            "tnx_close", -1),
    # === v1.1 扩充: 新增 8 个未检验链上因子 (均 2010~2013 起, 历史充足) ===
    "AVIV比率(估值)":     ("external/onchain/aviv.csv",             "value", -1),
    "CDD(币天销毁)":       ("external/onchain/cdd.csv",              "value", -1),
    "CDD调整(终端)":       ("external/onchain/cdd_terminal_ajusted.csv", "value", -1),
    "LTH-MVRV(长持估值)":  ("external/onchain/lth_mvrv.csv",         "value", -1),
    "LTH-SOPR(长持获利)":  ("external/onchain/lth_sopr.csv",         "value", -1),
    "STH-MVRV(短持估值)":  ("external/onchain/sth_mvrv.csv",         "value", -1),
    "STH-NUPL(短持)":      ("external/onchain/sth_nupl.csv",         "value", -1),
    "STH-SOPR(短持获利)":  ("external/onchain/sth_sopr.csv",         "value", -1),
    # === 注: 合约杠杆率 (open_interest / long_short_ratio) 本地数据仅自 2026-02 起,
    #     ~4个月 → 90d 非重叠采样后 N≈1, 无法做 IC 检验, 暂不纳入 (数据太短) ===
}

HORIZONS = [30, 90]  # 预测窗口(天) — 逃顶关心中期


def load_price() -> pd.Series:
    df = pd.read_csv(DATA / "raw/btc_binance_BTCUSDT_1d.csv", parse_dates=["date"])
    return df.set_index("date").sort_index()["close"]


def load_indicator(rel: str, col: str) -> pd.Series:
    df = pd.read_csv(DATA / rel, parse_dates=["date"])
    s = df.set_index("date").sort_index()[col]
    return s[~s.index.duplicated(keep="last")].dropna()


def ic_nonoverlap(sig: pd.Series, fwd_ret: pd.Series, h: int):
    """非重叠采样后的 Spearman rank IC + t-stat。"""
    # 对齐 (内连接, 只保留两者都有的日期)
    df = pd.concat([sig.rename("s"), fwd_ret.rename("r")], axis=1).dropna()
    if len(df) < 10:
        return None
    # 非重叠采样: 每 h 天取一个点 (手册 §2.1)
    df = df.iloc[::h]
    n = len(df)
    if n < 8:
        return None
    ic, _ = spearmanr(df["s"], df["r"])
    if np.isnan(ic):
        return None
    t = ic * np.sqrt(n - 2) / np.sqrt(1 - ic**2) if abs(ic) < 1 else np.nan
    return {"ic": ic, "t": t, "n": n}


def main():
    price = load_price()
    print("=" * 92)
    print("逃顶指标单因子 IC 检验 — 用 t-stat 而非故事 (手册 §2/§3)")
    print(f"价格数据: {price.index[0].date()} ~ {price.index[-1].date()} ({len(price)}天)")
    print("方向锁定: 全部按'逃顶指标'(预期负IC)预声明; 非重叠采样防 t-stat 虚高")
    print("=" * 92)

    rows = []
    for name, (rel, col, direction) in INDICATORS.items():
        try:
            sig = load_indicator(rel, col)
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  {name:<18} 加载失败: {e}")
            continue
        for h in HORIZONS:
            fwd = price.shift(-h) / price - 1.0  # future_return[t→t+h]
            res = ic_nonoverlap(sig, fwd, h)
            if res is None:
                continue
            # 方向是否符合理论预期 (逃顶指标应为负IC)
            ok_dir = (res["ic"] * direction) > 0
            rows.append({
                "指标": name, "h": h, "样本N": res["n"],
                "RankIC": res["ic"], "t-stat": res["t"],
                "符合理论方向": ok_dir,
            })

    rdf = pd.DataFrame(rows)
    # 排序: 按 |t-stat| (h=90) 降序, 找最强信号
    print(f"\n{'指标':<18}{'窗口':>5}{'样本N':>6}{'RankIC':>9}{'t-stat':>8}{'方向✓':>6}{'判定':>14}")
    print("-" * 92)
    for _, r in rdf.sort_values(["h", "t-stat"]).iterrows():
        ic, t, n = r["RankIC"], r["t-stat"], r["样本N"]
        # 判定 (手册 §3.3 门槛)
        if abs(ic) < 0.02:
            verdict = "❌噪音(IC<0.02)"
        elif abs(t) < 1.0:
            verdict = "⚠️不显著(|t|<1)"
        elif abs(t) >= 2.0:
            verdict = "✅强(|t|≥2)"
        else:
            verdict = "🟡弱有效"
        dirmark = "✓" if r["符合理论方向"] else "✗反向!"
        print(f"{r['指标']:<18}{r['h']:>4}d{n:>6}{ic:>+9.3f}{t:>+8.2f}{dirmark:>7}{verdict:>14}")

    print("-" * 92)
    print("\n【解读规则·手册§3.3】")
    print("  |IC|<0.02 = 噪音放弃 | |t|<1.0 = 不稳定(Regime依赖) | |t|≥2 = 显著")
    print("  方向✗ = 实际符号与'逃顶'理论相反, 该指标在此窗口不是看跌信号")
    print("\n【重要 caveat】")
    print("  - 单资产时序 IC, t-stat 用样本量法(非截面法); 非重叠采样已防虚高, 但 N 偏小时置信有限。")
    print("  - 链上数据可能被数据源回填修正 → 真实 live 表现或低于此回测 (Layer 0 风险)。")
    print("  - 本检验只看'线性单调预测力', 不含阈值/形态/共振逻辑 → 不能直接否定人工共振用法。")

    # 落盘 CSV 供复现
    out = PROJECT_ROOT / "experiments" / "research" / "topping_indicator_ic.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rdf.to_csv(out, index=False)
    print(f"\n结果已保存: {out.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
