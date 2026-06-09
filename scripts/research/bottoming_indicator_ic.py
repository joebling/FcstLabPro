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

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# 让脚本可直接 `python scripts/research/bottoming_indicator_ic.py` 运行:
# 把项目根目录塞进 sys.path, 否则下面的 `from scripts.research...` 会 ModuleNotFoundError。
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 复用逃顶脚本的数据加载 + IC 内核 (DRY, 保证两端方法论严格可比)
from scripts.research.topping_indicator_ic import (  # noqa: E402
    INDICATORS,
    ic_nonoverlap,
    load_indicator,
    load_price,
)

HORIZONS = [30, 90, 180]  # 底部反弹关心中-长期 (比顶部多看 180d)
LOW_Q = 20.0              # "极度低估" 阈值: expanding 历史分位 <= 20%
MIN_PCT_WIN = 365        # 分位最少需要 1 年历史才稳 (早期不算)

# 统一基线窗口 (修 review §2.2 苹果比橘): 所有指标用同一价格口径基线,
# 超额才可横向排名。窗口 = 剖资金费率(2019-09上线)后的指标交集,
# 以保住 2018 + 2022 两个周期底。资金费率因 history 太短, 基线单独降级。
BASELINE_START = pd.Timestamp("2018-02-01")
BASELINE_END = pd.Timestamp("2025-12-28")


def expanding_pct(s: pd.Series) -> pd.Series:
    """每点的 expanding 历史分位 (0~100), 只用 <=当日数据 (防未来函数).

    与 src/dashboard/data/topping._expanding_pct 同口径 (那是展示层, 此处研究层,
    刻意不跨层 import; 逻辑微小重复但保持层间解耦, 见手册架构约束)。
    """
    return s.expanding(min_periods=MIN_PCT_WIN).apply(
        lambda w: float((w <= w.iloc[-1]).sum()) / len(w) * 100.0, raw=False
    )


def unified_baseline(price: pd.Series, h: int) -> float:
    """统一基线: 固定共同窗口 [BASELINE_START, BASELINE_END] 上的无条件 h 天前瞻收益均值.

    只依赖 price, 与具体指标无关 -> 所有指标共用同一基线, 超额可严格横向比
    (修 review §2.2: 旧版按各指标可用样本期分别算基线 -> 苹果比橘)。
    """
    fwd = price.shift(-h) / price - 1.0
    win = fwd[(fwd.index >= BASELINE_START) & (fwd.index <= BASELINE_END)].dropna()
    return float(win.mean()) if len(win) else float("nan")


def low_events(low_idx: pd.Index, h: int) -> pd.DatetimeIndex:
    """把重叠低估日塌缩成非重叠事件: 相邻低估日间隔 > h 天则视为新事件段, 取每段首日.

    修 review §2.1 日频重叠: MVRV-Z 的 358 低估日去重后只剩 ~6 段独立低估期。
    间隔阈值用 h -> 事件首日彼此 > h 天 -> 前瞻窗口不重叠。进场点 = 低估段首日
    (无前瞻 / 最贴近可交易, 项目方确认口径)。
    """
    if len(low_idx) == 0:
        return pd.DatetimeIndex([])
    dates = pd.DatetimeIndex(sorted(low_idx))
    starts = [dates[0]]
    for prev, cur in zip(dates[:-1], dates[1:]):
        if (cur - prev).days > h:
            starts.append(cur)
    return pd.DatetimeIndex(starts)


def conditional_bottom(
    sig: pd.Series, price: pd.Series, h: int, base_mean: float
) -> dict | None:
    """底部条件分析: 仅在 expanding 历史低分位 (<=LOW_Q) 子样本上看未来反弹.

    双口径输出 (review §2.1):
      - 日频(重叠): 仅供排序, 命中率被重叠夸大
      - 事件级(非重叠): 主口径, 每个低估段取首日
    base_mean 为统一基线 (由 unified_baseline 算好传入, 全指标共用)。
    """
    pct = expanding_pct(sig)
    fwd = price.shift(-h) / price - 1.0  # future_return[t -> t+h]
    df = pd.concat(
        [sig.rename("s"), pct.rename("pct"), fwd.rename("r")], axis=1
    ).dropna()
    if len(df) < MIN_PCT_WIN:
        return None

    low = df[df["pct"] <= LOW_Q]
    if len(low) < 5:
        return {"n_low": len(low), "insufficient": True, "base_mean": base_mean}

    # ---- 日频(重叠)口径: 仅供排序, 命中率被重叠夸大 (review §2.1) ----
    hit_d = float((low["r"] > 0).mean())
    avg_d = float(low["r"].mean())
    excess_d = avg_d - base_mean

    # ---- 事件级(非重叠)口径: 主口径, 每个低估段取首日 ----
    ev_starts = low_events(low.index, h)
    ev_r = df.loc[ev_starts, "r"]
    n_ev = int(len(ev_r))
    if n_ev > 0:
        hit_e: float | None = float((ev_r > 0).mean())
        avg_e: float | None = float(ev_r.mean())
        excess_e: float | None = avg_e - base_mean
    else:
        hit_e = avg_e = excess_e = None

    # 子样本 IC (非重叠): 低估区内 指标 vs 未来收益, 拄底预期为负 (越低越涨)
    low_no = low.iloc[::h]
    sub = None
    if len(low_no) >= 8:
        ic, _ = spearmanr(low_no["s"], low_no["r"])
        if not np.isnan(ic) and abs(ic) < 1:
            t = ic * np.sqrt(len(low_no) - 2) / np.sqrt(1 - ic**2)
            sub = {"ic": float(ic), "t": float(t), "n": int(len(low_no))}

    return {
        "n_low": int(len(low)), "insufficient": False,
        "hit_d": hit_d, "avg_d": avg_d, "excess_d": excess_d,
        "n_ev": n_ev, "hit_e": hit_e, "avg_e": avg_e, "excess_e": excess_e,
        "base_mean": base_mean, "sub_ic": sub,
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
    base = {h: unified_baseline(price, h) for h in HORIZONS}
    print("\n" + "=" * 116)
    print("[Part B] 条件分位分析 — 极度低估区 (分位<=20%) 的未来反弹 (底部专属预测力)")
    print(f"统一基线窗口: {BASELINE_START.date()} ~ {BASELINE_END.date()} (全指标共用, 价格口径)")
    print(f"  基线 h=30:{base[30]*100:+.1f}%  h=90:{base[90]*100:+.1f}%  h=180:{base[180]*100:+.1f}%")
    print("=" * 116)
    print(f"{'指标':<20}{'窗口':>6}{'事件N':>6}{'事命中':>7}{'事超额':>8}"
          f"{'|':>3}{'日N':>6}{'日命中':>7}{'日超额':>8}{'子ICt':>8}")
    print("-" * 116)

    rows = []
    for name, (rel, col, _) in INDICATORS.items():
        try:
            sig = load_indicator(rel, col)
        except Exception:  # noqa: BLE001
            continue
        for h in HORIZONS:
            res = conditional_bottom(sig, price, h, base[h])
            if res is None:
                continue
            if res.get("insufficient"):
                print(f"{name:<20}{h:>5}d  (低估样本<5, 跳过)")
                continue
            sub = res["sub_ic"]
            st = f"{sub['t']:+.1f}" if sub else "  n/a"
            he = f"{res['hit_e']*100:>5.0f}%" if res["hit_e"] is not None else "  n/a"
            xe = f"{res['excess_e']*100:>+6.1f}%" if res["excess_e"] is not None else "   n/a"
            print(f"{name:<20}{h:>5}d{res['n_ev']:>6}{he:>7}{xe:>8}"
                  f"{'|':>3}{res['n_low']:>6}{res['hit_d']*100:>6.0f}%"
                  f"{res['excess_d']*100:>+7.1f}%{st:>8}")
            rows.append({
                "指标": name, "h": h,
                # 事件级(非重叠) = 主口径
                "事件N": res["n_ev"],
                "事命中率": res["hit_e"], "事均反弹": res["avg_e"], "事超额": res["excess_e"],
                # 日频(重叠) = 仅排序
                "低估天数": res["n_low"],
                "日命中率": res["hit_d"], "日均反弹": res["avg_d"], "日超额": res["excess_d"],
                "统一基线": res["base_mean"],
                "子样本IC": sub["ic"] if sub else None,
                "子t": sub["t"] if sub else None,
                "子N": sub["n"] if sub else None,
            })

    print("-" * 116)
    print("\n【解读·review V2】")
    print("  事件级(非重叠) = 主口径: 每个低估段取首日, N 诚实反映周期数(~3-6); 这才是能依赖的证据。")
    print("  日频(重叠) = 仅排序: 命中率被重叠夸大(6个故事讲358遍), 不能当独立同分布硬结论。")
    print("  超额 = 该口径均反弹 - 统一基线(全指标共用) (>0 才有拄底价值)。")
    print("\n【caveat】")
    print("  - 子样本IC 非重叠后 N<8 多为 n/a 是 BTC 只有 3-4 大底的结构性宿命, 非代码缺陷。")
    print("  - 本位: 超额/命中是 USD 价格收益口径(判方向+排序); 能不能攒更多币靠币本位轮动回测。")
    print("  - 链上数据可能被数据源回填修正 (Layer 0 风险), 真实 live 表现或低于此回测。")

    out = PROJECT_ROOT / "experiments" / "research" / "bottoming_indicator_ic.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\n结果已保存: {out.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
