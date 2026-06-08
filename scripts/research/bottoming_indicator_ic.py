#!/usr/bin/env python3
"""抄底指标单因子 IC 检验 (纯研究, 只读) — 底部框架的 alpha 验证.

对标 topping_indicator_ic.py, 但【底部 != 顶部反操作】, 方法论有关键不对称:

  ===== 陷阱: 全样本 IC 镜像 =====
  单资产全样本 Spearman rank IC 是对称的:
    corr(rank(signal), rank(fwd_ret)) 数值与逃顶检验完全相同,
    只是方向解释相反 (高->跌 vs 低->涨)。
    -> 单纯把 direction 翻成 +1 跑全样本 IC = 顶部结果的镜像, 没有新信息。
    -> Part A 仅作方向基线确认; 真正的底部 alpha 在 Part B。

  ===== 底部特异: 条件分位 IC =====
  底部研判的真问题是:
    "当指标处于历史极低分位 (极度低估) 时, 未来是否真的反弹?"
    -> 只在 expanding 历史低分位子样本上检验未来收益
       (命中率 / 超额反弹 / 子样本 IC)。
    这才是与全样本线性 IC 不同的、底部区域专属的预测力。

方法论 (诚实声明, 见手册 §2):
  - point-in-time expanding 分位 (只用 <=当日数据, 防未来函数)
  - 非重叠采样 (手册 §2.1) 用于 IC/子样本 IC 的 t-stat
  - 方向锁定: 抄底指标预期 低分位->未来正收益 (预声明, 不事后反推)
  - 底部样本天然稀少 (BTC 史上 3-4 个大底) -> t-stat 弱是诚实发现, 不是 bug

门槛 (手册 §3.3): |Rank IC|>0.02 有价值; |t|>1.0 显著; |t|>=2 强。

用法:
    python scripts/research/bottoming_indicator_ic.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# 复用逃顶脚本的数据加载 + IC 内核 (DRY, 保证两端方法论严格可比)
from scripts.research.topping_indicator_ic import (
    INDICATORS,
    ic_nonoverlap,
    load_indicator,
    load_price,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

HORIZONS = [30, 90, 180]  # 底部反弹关心中-长期 (比顶部多看 180d)
LOW_Q = 20.0              # "极度低估" 阈值: expanding 历史分位 <= 20%
MIN_PCT_WIN = 365        # 分位最少需要 1 年历史才稳 (早期不算)


def expanding_pct(s: pd.Series) -> pd.Series:
    """每点的 expanding 历史分位 (0~100), 只用 <=当日数据 (防未来函数).

    与 src/dashboard/data/topping._expanding_pct 同口径 (那是展示层, 此处研究层,
    刻意不跨层 import; 逻辑微小重复但保持层间解耦, 见手册架构约束)。
    """
    return s.expanding(min_periods=MIN_PCT_WIN).apply(
        lambda w: float((w <= w.iloc[-1]).sum()) / len(w) * 100.0, raw=False
    )


def conditional_bottom(sig: pd.Series, price: pd.Series, h: int) -> dict | None:
    """底部条件分析: 仅在 expanding 历史低分位 (<=LOW_Q) 子样本上看未来反弹.

    Returns dict: 低分位天数 / 命中率 / 平均反弹 / 全样本基线 / 超额 / 子样本IC+t。
    """
    pct = expanding_pct(sig)
    fwd = price.shift(-h) / price - 1.0  # future_return[t -> t+h]
    df = pd.concat(
        [sig.rename("s"), pct.rename("pct"), fwd.rename("r")], axis=1
    ).dropna()
    if len(df) < MIN_PCT_WIN:
        return None

    base_mean = float(df["r"].mean())  # 全样本未来收益基线
    low = df[df["pct"] <= LOW_Q]
    if len(low) < 5:
        return {"n_low": len(low), "insufficient": True, "base_mean": base_mean}

    hit = float((low["r"] > 0).mean())
    avg = float(low["r"].mean())
    excess = avg - base_mean

    # 子样本 IC (非重叠): 低估区内 指标 vs 未来收益, 抄底预期为负 (越低越涨)
    low_no = low.iloc[::h]
    sub = None
    if len(low_no) >= 8:
        ic, _ = spearmanr(low_no["s"], low_no["r"])
        if not np.isnan(ic) and abs(ic) < 1:
            t = ic * np.sqrt(len(low_no) - 2) / np.sqrt(1 - ic**2)
            sub = {"ic": float(ic), "t": float(t), "n": int(len(low_no))}

    return {
        "n_low": int(len(low)), "insufficient": False,
        "hit": hit, "avg": avg, "base_mean": base_mean, "excess": excess,
        "sub_ic": sub,
    }


def main() -> None:
    price = load_price()
    print("=" * 100)
    print("抄底指标单因子 IC 检验 — 底部框架 alpha 验证 (手册 §2/§3)")
    print(f"价格数据: {price.index[0].date()} ~ {price.index[-1].date()} ({len(price)}天)")
    print(f"低估阈值: expanding 历史分位 <= {LOW_Q:.0f}% | 分位最少历史 {MIN_PCT_WIN}天")
    print("=" * 100)

    # ---------- Part A: 全样本对称 IC (方向基线, = 顶部镜像) ----------
    print("\n" + "-" * 100)
    print("[Part A] 全样本对称 IC — 仅确认方向基线 (|IC|/|t| 必然 = 逃顶检验, 无新信息)")
    print("-" * 100)
    print(f"{'指标':<20}{'窗口':>6}{'样本N':>7}{'RankIC':>9}{'t-stat':>8}{'抄底方向':>10}")
    for name, (rel, col, _) in INDICATORS.items():
        try:
            sig = load_indicator(rel, col)
        except Exception:  # noqa: BLE001
            continue
        for h in [30, 90]:
            fwd = price.shift(-h) / price - 1.0
            res = ic_nonoverlap(sig, fwd, h)
            if res is None:
                continue
            # 抄底方向: 指标低->未来涨 => 指标与未来收益负相关 (IC<0)
            ok = res["ic"] < 0
            print(f"{name:<20}{h:>5}d{res['n']:>7}{res['ic']:>+9.3f}"
                  f"{res['t']:>+8.2f}{('' if ok else ''):>9}")

    # ---------- Part B: 条件分位 IC (底部灵魂) ----------
    print("\n" + "=" * 100)
    print("[Part B] 条件分位分析 — 极度低估区 (分位<=20%) 的未来反弹 (底部专属预测力)")
    print("=" * 100)
    print(f"{'指标':<20}{'窗口':>6}{'低估天数':>8}{'命中率':>8}{'均反弹':>9}"
          f"{'基线':>9}{'超额':>9}{'子样本IC':>10}{'子t':>7}")
    print("-" * 100)

    rows = []
    for name, (rel, col, _) in INDICATORS.items():
        try:
            sig = load_indicator(rel, col)
        except Exception:  # noqa: BLE001
            continue
        for h in HORIZONS:
            res = conditional_bottom(sig, price, h)
            if res is None:
                continue
            if res.get("insufficient"):
                print(f"{name:<20}{h:>5}d{res['n_low']:>8}  (低估样本<5, 跳过)")
                continue
            sub = res["sub_ic"]
            sic = f"{sub['ic']:+.3f}" if sub else "  n/a"
            st = f"{sub['t']:+.2f}" if sub else "  -"
            print(f"{name:<20}{h:>5}d{res['n_low']:>8}{res['hit']*100:>7.0f}%"
                  f"{res['avg']*100:>+8.1f}%{res['base_mean']*100:>+8.1f}%"
                  f"{res['excess']*100:>+8.1f}%{sic:>10}{st:>7}")
            rows.append({
                "指标": name, "h": h, "低估天数": res["n_low"],
                "命中率": res["hit"], "均反弹": res["avg"],
                "基线": res["base_mean"], "超额": res["excess"],
                "子样本IC": sub["ic"] if sub else None,
                "子t": sub["t"] if sub else None,
                "子N": sub["n"] if sub else None,
            })

    print("-" * 100)
    print("\n【解读·手册§3.3】")
    print("  命中率 = 低估区未来正收益占比; 超额 = 低估区均反弹 - 全样本基线 (>0 才有抄底价值)")
    print("  子样本IC<0 = 低估区内'越便宜越涨'成立 (抄底逻辑); 子t>=1 才稳")
    print("\n【caveat】")
    print("  - 低估天数是日频(重叠)计数, 用于命中率趋势观察; 子样本IC用非重叠 t-stat。")
    print("  - 底部样本天然稀少 -> 子N 偏小, 显著性弱是市场结构的诚实结果, 非代码缺陷。")
    print("  - 链上数据可能被数据源回填修正 (Layer 0 风险), 真实 live 表现或低于此回测。")

    out = PROJECT_ROOT / "experiments" / "research" / "bottoming_indicator_ic.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\n结果已保存: {out.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
