#!/usr/bin/env python3
"""ahr999 vs RR 在 rolling-2y 分位口径下的决策重审 (Phase 2, audit §5.2/5.3).

背景:
  §10.1 (commit 5b200b0) 决定 ahr999 不接入 Layer A, 依据三条:
    (1) 单因子 IC h=90 |t|=1.83 (差强人意, 未达 |t|>=2)
    (2) vs RR Spearman ρ=0.910 (冗余级)
    (3) 6 事件 83% 命中 +14.8% 超额 vs RR 6/67%/+6.3% (强但同类信号)

  ALL THREE 都用 expanding 分位。Audit 报告 (2026-06-09) 揭示 expanding 在
  演化资产上被 2013-2018 极值锚死, 修复后切到 rolling-2y。
  → §10.1 的依据全部可疑, 必须重审。

本脚本三块输出 (对应原 3 条依据):

  Block A. 共线性矩阵
    raw value 的 Spearman (基线, 不受分位口径影响)
    expanding 分位 Spearman ρ (复现 0.910)
    rolling-2y 分位 Spearman ρ (关键: 是否解耦到 <0.7)

  Block B. 全样本 IC (h=30/90/180)
    原口径: raw value 作 signal (复现 -0.321/|t|=1.83)
    新口径: rolling-2y 分位作 signal (是否仍 |t|<2?)
    同步对比 RR

  Block C. 条件低估事件 (ahr999 分位 <= 15)
    expanding 触发 → 复现旧 6 事件
    rolling-2y 触发 → 重算 N / 命中率 / 超额
    同事件上 RR 的表现 (Jaccard, 互补性)

最终输出决策建议矩阵:
  | ρ_roll2y | IC_t_roll2y | 决策                        |
  |----------|-------------|-----------------------------|
  | <0.7     | |t|>=2      | 翻案: 接入 Layer A 辅助     |
  | <0.7     | |t|<2       | 维持不接 A, 升 Layer B 互验 |
  | >=0.7    | 任意        | 维持 §10.1 (仍冗余)         |
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, pearsonr

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.research.topping_indicator_ic import (  # noqa: E402
    DATA,
    load_indicator,
    load_price,
)

# ---- 口径常数 (与 audit 报告 V1.2 一致) ----
ROLL_WIN = 730       # rolling 2 年
MIN_PCT_WIN = 180    # rolling 最小窗 (NaN 截断, 与 cycle_core 一致)
EXP_MIN_WIN = 365    # expanding 最小窗 (与原 IC 脚本一致)
LOW_Q = 20.0         # ≤20% 为"极度低估" (与 bottoming_ic 一致)
HORIZONS = [30, 90, 180]
BASELINE_START = pd.Timestamp("2018-02-01")
BASELINE_END = pd.Timestamp("2025-12-28")


# ============================================================
# 分位函数 (与 cycle_core 同口径, 但研究层独立实现, 见手册架构约束)
# ============================================================
def pct_expanding(s: pd.Series, min_win: int = EXP_MIN_WIN) -> pd.Series:
    """expanding 分位 (复现 §10.1 旧口径). 矢量化版."""
    return s.expanding(min_periods=min_win).rank(pct=True) * 100


def pct_rolling(s: pd.Series, win: int = ROLL_WIN, min_win: int = MIN_PCT_WIN) -> pd.Series:
    """rolling-2y 分位 (新口径, audit 修复后)."""
    return s.rolling(window=win, min_periods=min_win).rank(pct=True) * 100


# ============================================================
# 工具: 非重叠采样后的 Spearman IC + t
# ============================================================
def ic_nonoverlap(sig: pd.Series, fwd: pd.Series, h: int) -> dict | None:
    df = pd.concat([sig.rename("s"), fwd.rename("r")], axis=1).dropna()
    if len(df) < 10:
        return None
    df = df.iloc[::h]  # 非重叠
    n = len(df)
    if n < 8:
        return None
    ic, _ = spearmanr(df["s"], df["r"])
    if np.isnan(ic) or abs(ic) >= 1:
        return None
    t = ic * np.sqrt(n - 2) / np.sqrt(1 - ic**2)
    return {"ic": float(ic), "t": float(t), "n": n}


def unified_baseline(price: pd.Series, h: int) -> float:
    fwd = price.shift(-h) / price - 1.0
    win = fwd[(fwd.index >= BASELINE_START) & (fwd.index <= BASELINE_END)].dropna()
    return float(win.mean()) if len(win) else float("nan")


def low_events(low_idx: pd.Index, h: int) -> pd.DatetimeIndex:
    """间隔 > h 天则视为新事件段, 取每段首日."""
    if len(low_idx) == 0:
        return pd.DatetimeIndex([])
    dates = pd.DatetimeIndex(sorted(low_idx))
    starts = [dates[0]]
    for prev, cur in zip(dates[:-1], dates[1:]):
        if (cur - prev).days > h:
            starts.append(cur)
    return pd.DatetimeIndex(starts)


# ============================================================
# Block A: 共线性重审
# ============================================================
def block_a_collinearity(ahr: pd.Series, rr: pd.Series) -> dict:
    print("\n" + "=" * 100)
    print("[Block A] ahr999 vs RR 共线性 (raw value + expanding + rolling-2y 三口径)")
    print("=" * 100)

    df = pd.concat([ahr.rename("ahr"), rr.rename("rr")], axis=1).dropna()
    print(f"对齐后样本: {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)} 天)")

    # raw value (sanity check, 不受分位口径影响)
    rho_raw, _ = spearmanr(df["ahr"], df["rr"])
    pear_raw, _ = pearsonr(df["ahr"], df["rr"])

    # expanding 分位 (复现 §10.1)
    pe_a = pct_expanding(df["ahr"]).dropna()
    pe_r = pct_expanding(df["rr"]).dropna()
    pe = pd.concat([pe_a.rename("a"), pe_r.rename("r")], axis=1).dropna()
    rho_exp, _ = spearmanr(pe["a"], pe["r"])
    pear_exp, _ = pearsonr(pe["a"], pe["r"])

    # rolling-2y 分位 (新口径)
    pr_a = pct_rolling(df["ahr"]).dropna()
    pr_r = pct_rolling(df["rr"]).dropna()
    pr = pd.concat([pr_a.rename("a"), pr_r.rename("r")], axis=1).dropna()
    rho_roll, _ = spearmanr(pr["a"], pr["r"])
    pear_roll, _ = pearsonr(pr["a"], pr["r"])

    print(f"\n{'口径':<25}{'Spearman ρ':>15}{'Pearson r':>15}{'样本N':>10}")
    print("-" * 65)
    print(f"{'raw value (基线)':<25}{rho_raw:>+15.3f}{pear_raw:>+15.3f}{len(df):>10}")
    print(f"{'expanding 分位 (旧)':<25}{rho_exp:>+15.3f}{pear_exp:>+15.3f}{len(pe):>10}")
    print(f"{'rolling-2y 分位 (新)':<25}{rho_roll:>+15.3f}{pear_roll:>+15.3f}{len(pr):>10}")

    # 判定
    print(f"\n判定门槛 (§10.1): ρ < 0.7 = 解耦, 可作独立 alpha; ρ >= 0.7 = 冗余")
    if abs(rho_roll) < 0.7:
        verdict_a = f" 解耦 (ρ={rho_roll:.3f} < 0.7) — 共线性证据被推翻"
    else:
        verdict_a = f" 仍冗余 (ρ={rho_roll:.3f} >= 0.7) — 共线性证据成立, 不应接 A"
    print(f"Block A 结论: {verdict_a}")

    return {
        "n_obs": int(len(df)),
        "rho_raw": float(rho_raw),
        "rho_expanding": float(rho_exp),
        "rho_rolling2y": float(rho_roll),
        "pear_raw": float(pear_raw),
        "pear_expanding": float(pear_exp),
        "pear_rolling2y": float(pear_roll),
        "verdict": verdict_a,
        "decoupled": bool(abs(rho_roll) < 0.7),
    }


# ============================================================
# Block B: 全样本单因子 IC (raw vs rolling-2y 分位作信号)
# ============================================================
def block_b_single_ic(ahr: pd.Series, rr: pd.Series, price: pd.Series) -> dict:
    print("\n" + "=" * 100)
    print("[Block B] 单因子 IC: raw value vs rolling-2y 分位 作 signal, h=30/90/180")
    print("=" * 100)
    print(f"\n{'指标':<10}{'口径':<22}{'h':>5}{'N':>6}{'RankIC':>9}{'t-stat':>9}{'判定':>14}")
    print("-" * 75)

    out = {}
    for name, sig in [("ahr999", ahr), ("RR", rr)]:
        out[name] = {}
        for label, transform in [
            ("raw value (旧基线)", lambda s: s),
            ("rolling-2y 分位 (新)", pct_rolling),
        ]:
            sig_t = transform(sig).dropna()
            for h in HORIZONS:
                fwd = price.shift(-h) / price - 1.0
                res = ic_nonoverlap(sig_t, fwd, h)
                if res is None:
                    continue
                if abs(res["ic"]) < 0.02:
                    v = "噪音"
                elif abs(res["t"]) < 1.0:
                    v = "不显著"
                elif abs(res["t"]) >= 2.0:
                    v = "强(|t|≥2)"
                else:
                    v = "弱有效"
                print(f"{name:<10}{label:<22}{h:>4}d{res['n']:>6}{res['ic']:>+9.3f}"
                      f"{res['t']:>+9.2f}{v:>14}")
                out[name].setdefault(label, {})[h] = res
        print()

    # 关键比较: ahr999 在两个口径下, h=90 的 |t|
    raw_h90 = out["ahr999"].get("raw value (旧基线)", {}).get(90)
    roll_h90 = out["ahr999"].get("rolling-2y 分位 (新)", {}).get(90)
    if raw_h90 and roll_h90:
        print(f"关键比较 ahr999 h=90:")
        print(f"  旧 (raw):     |t| = {abs(raw_h90['t']):.2f}  (§10.1 报告 1.83)")
        print(f"  新 (roll-2y): |t| = {abs(roll_h90['t']):.2f}")
        if abs(roll_h90["t"]) >= 2.0:
            verdict_b = f" 翻案: rolling-2y 下 |t|={abs(roll_h90['t']):.2f} >= 2, 达独立 alpha 门槛"
            passed = True
        else:
            verdict_b = f" 维持: rolling-2y 下 |t|={abs(roll_h90['t']):.2f} 仍 < 2, 不达门槛"
            passed = False
    else:
        verdict_b = "数据不足, 无法判定"
        passed = False
    print(f"\nBlock B 结论: {verdict_b}")

    return {"results": out, "verdict": verdict_b, "passed_ic_gate": passed}


# ============================================================
# Block C: 条件低估事件重审 (≤15% 触发)
# ============================================================
def block_c_events(ahr: pd.Series, rr: pd.Series, price: pd.Series) -> dict:
    print("\n" + "=" * 100)
    print(f"[Block C] 条件低估事件 (分位 <= {LOW_Q:.0f}%, expanding vs rolling-2y 对比)")
    print("=" * 100)

    base = {h: unified_baseline(price, h) for h in HORIZONS}
    print(f"统一基线 (全指标共用):")
    for h in HORIZONS:
        print(f"  h={h}d: {base[h]*100:+.1f}%")

    out = {}
    for name, sig in [("ahr999", ahr), ("RR", rr)]:
        out[name] = {}
        for label, pct_fn in [("expanding (旧)", pct_expanding), ("rolling-2y (新)", pct_rolling)]:
            pct = pct_fn(sig)
            df = pd.concat([sig.rename("s"), pct.rename("pct")], axis=1).dropna()
            out[name][label] = {}
            for h in HORIZONS:
                fwd = price.shift(-h) / price - 1.0
                dfh = pd.concat([df, fwd.rename("r")], axis=1).dropna()
                low = dfh[dfh["pct"] <= LOW_Q]
                n_low = len(low)
                if n_low == 0:
                    out[name][label][h] = {"n_ev": 0, "n_low": 0}
                    continue
                # 事件级 (非重叠)
                starts = low_events(low.index, h)
                ev_r = dfh.loc[starts, "r"]
                n_ev = len(ev_r)
                hit = float((ev_r > 0).mean()) if n_ev else None
                avg = float(ev_r.mean()) if n_ev else None
                excess = (avg - base[h]) if avg is not None else None
                out[name][label][h] = {
                    "n_low": int(n_low),
                    "n_ev": int(n_ev),
                    "hit": hit,
                    "avg": avg,
                    "excess": excess,
                    "event_dates": [d.strftime("%Y-%m-%d") for d in starts],
                }

    # 打印对比表 (h=30 = §6.2.1 旧报告口径)
    h_show = 30
    print(f"\n--- h={h_show}d ('§6.2.1 ahr999 6 事件' 重审) ---")
    print(f"{'指标':<10}{'口径':<22}{'低估天数':>10}{'事件N':>8}{'命中率':>10}{'均反弹':>10}{'超额':>10}")
    print("-" * 80)
    for name in ["ahr999", "RR"]:
        for label in ["expanding (旧)", "rolling-2y (新)"]:
            d = out[name][label][h_show]
            if d["n_ev"] == 0:
                print(f"{name:<10}{label:<22}{d['n_low']:>10}{'0':>8}{'n/a':>10}{'n/a':>10}{'n/a':>10}")
                continue
            print(f"{name:<10}{label:<22}{d['n_low']:>10}{d['n_ev']:>8}"
                  f"{d['hit']*100:>9.0f}%{d['avg']*100:>+9.1f}%{d['excess']*100:>+9.1f}%")

    # h=90/180 简表
    for h in [90, 180]:
        print(f"\n--- h={h}d (中长期反弹) ---")
        for name in ["ahr999", "RR"]:
            for label in ["expanding (旧)", "rolling-2y (新)"]:
                d = out[name][label][h]
                if d["n_ev"] == 0:
                    continue
                print(f"  {name} {label}: N={d['n_ev']:>3} 命中={d['hit']*100:>3.0f}% "
                      f"均={d['avg']*100:>+5.1f}% 超额={d['excess']*100:>+5.1f}%")

    # Jaccard: ahr999 vs RR 在 rolling-2y 下的低估日重叠
    print(f"\n--- Jaccard 重叠 (低估日集合, rolling-2y 口径) ---")
    for h in HORIZONS:
        a_low = set(out["ahr999"]["rolling-2y (新)"][h].get("event_dates", []))
        r_low = set(out["RR"]["rolling-2y (新)"][h].get("event_dates", []))
        if not a_low or not r_low:
            continue
        inter = a_low & r_low
        union = a_low | r_low
        jacc = len(inter) / len(union) if union else 0
        print(f"  h={h}d  ahr999 N={len(a_low):>2}  RR N={len(r_low):>2}  "
              f"交集={len(inter):>2}  并集={len(union):>2}  Jaccard={jacc:.2f}")

    # 关键: §6.2.1 重审 — h=30 ahr999 在 rolling-2y 下事件数 + 命中率
    ahr_new = out["ahr999"]["rolling-2y (新)"][30]
    ahr_old = out["ahr999"]["expanding (旧)"][30]
    rr_new = out["RR"]["rolling-2y (新)"][30]
    print(f"\n【§6.2.1 重审】")
    print(f"  旧 (expanding): ahr999 N={ahr_old['n_ev']}, 命中={ahr_old['hit']*100 if ahr_old['hit'] else 0:.0f}%, "
          f"超额={ahr_old['excess']*100 if ahr_old['excess'] else 0:+.1f}%  (§10.1 报告 6/83%/+14.8%)")
    print(f"  新 (rolling2y): ahr999 N={ahr_new['n_ev']}, 命中={ahr_new['hit']*100 if ahr_new['hit'] else 0:.0f}%, "
          f"超额={ahr_new['excess']*100 if ahr_new['excess'] else 0:+.1f}%")
    print(f"  新 (rolling2y): RR     N={rr_new['n_ev']}, 命中={rr_new['hit']*100 if rr_new['hit'] else 0:.0f}%, "
          f"超额={rr_new['excess']*100 if rr_new['excess'] else 0:+.1f}%")

    return out


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 100)
    print("ahr999 vs RR 决策重审 (rolling-2y 口径) — Audit Phase 2")
    print(f"对照: §10.1 (commit 5b200b0) 三条依据全部用 rolling-2y 重跑")
    print("=" * 100)

    price = load_price()
    ahr = load_indicator("external/onchain/ahr999.csv", "value")
    rr = load_indicator("external/onchain/reserve_risk.csv", "value")
    print(f"价格: {price.index[0].date()} ~ {price.index[-1].date()} ({len(price)}天)")
    print(f"ahr999: {ahr.index[0].date()} ~ {ahr.index[-1].date()} ({len(ahr)}天)")
    print(f"RR:     {rr.index[0].date()} ~ {rr.index[-1].date()} ({len(rr)}天)")

    a = block_a_collinearity(ahr, rr)
    b = block_b_single_ic(ahr, rr, price)
    c = block_c_events(ahr, rr, price)

    # ============== 决策矩阵 ==============
    print("\n" + "=" * 100)
    print("【最终决策建议】")
    print("=" * 100)
    print(f"Block A (ρ_rolling2y): {a['rho_rolling2y']:+.3f}  [{'解耦' if a['decoupled'] else '冗余'}]")
    print(f"Block B (IC h=90 |t|): {'>=2 ' if b['passed_ic_gate'] else '<2 '}  ({b['verdict']})")

    if a["decoupled"] and b["passed_ic_gate"]:
        decision = " **翻案 §10.1**: ahr999 接入 Layer A 作辅助 RR 的次要主信号"
        action = "Layer A 投票制 = RR (主) + ahr999 (辅), 任一 >=85 触发, 双触发加权"
    elif a["decoupled"] and not b["passed_ic_gate"]:
        decision = " **半翻案**: 不接 Layer A, 但升 Layer B 互验 (从纯备份升为正式 B)"
        action = "ahr999 加入 Layer B 共振计数, 阈值与其它 B 指标一致"
    else:
        decision = " **维持 §10.1**: ρ 仍 >=0.7, 共线性证据成立, ahr999 不接 A 也不升 B"
        action = "继续作 Layer 0 容灾备份, 不进入 regime gate"

    print(f"\n决策: {decision}")
    print(f"操作: {action}")

    # 落盘
    out = {
        "phase": "ahr999 recheck (rolling-2y)",
        "ref_decision": "§10.1, commit 5b200b0",
        "audit_ref": "docs/plans/rolling_vs_expanding_audit_20260609.md §5.2/5.3",
        "block_a_collinearity": a,
        "block_b_ic": b,
        "block_c_events": c,
        "final_decision": decision,
        "final_action": action,
    }
    out_path = PROJECT_ROOT / "experiments" / "research" / "ahr999_recheck_rolling2y.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n详细结果: {out_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
