#!/usr/bin/env python3
"""Regime 研究脚本 (纯研究, 不碰生产).

目的: 对比「现有 regime (63日收益≤-10%)」vs「多维 regime」在 BTC 历史上的表现,
直观看出二者差异, 为是否升级生产 regime 提供依据。

⚠️ point-in-time 原则: 所有指标只用 <=t 数据, 无未来函数。
   - 滚动统计用 .rolling() (只回看)
   - 波动率分位数用 rolling 历史分位 (不用全样本分位)

用法:
    python scripts/research/regime_analysis.py
输出:
    experiments/research/regime/regime_analysis.png   (可视化)
    experiments/research/regime/regime_summary.csv    (逐日 regime 标签)
    控制台: 各 regime 占比 + 切换频率统计
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = PROJECT_ROOT / "experiments" / "research" / "regime"


def load_prices() -> pd.DataFrame:
    """加载 OHLCV (优先 live, 回退 raw 基准)."""
    live = PROJECT_ROOT / "data" / "live" / "btc_binance_BTCUSDT_1d.csv"
    raw = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"
    path = live if live.exists() else raw
    df = pd.read_csv(path, index_col=0).sort_index()
    df.index = pd.to_datetime(df.index)
    print(f"[data] {path.name} | {len(df)} 行 | {df.index[0].date()} ~ {df.index[-1].date()}")
    return df


# =====================================================================
# 各 regime 维度 (全部 point-in-time)
# =====================================================================

def regime_legacy(close: pd.Series, window: int = 63, threshold: float = -0.10) -> pd.Series:
    """现有生产 regime: 63日滚动收益 <= -10% → 熊市(1), 否则 0."""
    roll_ret = close / close.shift(window) - 1
    return (roll_ret <= threshold).astype(int)


def dim_trend(close: pd.Series, window: int = 200) -> pd.Series:
    """趋势维度: 价格 vs N日均线. >0 = 上方(牛), <0 = 下方(熊)."""
    sma = close.rolling(window).mean()
    return close / sma - 1


def dim_drawdown(close: pd.Series, window: int = 90) -> pd.Series:
    """回撤维度: 距 N 日滚动高点的回撤 (贴合体感). 0 = 在高点, 负数 = 回撤中."""
    roll_high = close.rolling(window).max()
    return close / roll_high - 1


def dim_vol_pctile(close: pd.Series, vol_win: int = 20, lookback: int = 365) -> pd.Series:
    """波动率分位数 (自适应阈值): 当前已实现波动率在过去 lookback 天的分位 [0,1].

    point-in-time: 用 rolling 历史分位, 不用全样本分位 (那会泄露未来)。
    """
    daily_ret = close.pct_change()
    rvol = daily_ret.rolling(vol_win).std() * np.sqrt(365)  # 年化已实现波动率

    def _pctile(x: np.ndarray) -> float:
        return (x[:-1] < x[-1]).mean() if len(x) > 1 else np.nan

    return rvol.rolling(lookback, min_periods=60).apply(_pctile, raw=True)


def regime_multidim(
    close: pd.Series,
    trend_win: int = 200,
    dd_win: int = 90,
    dd_thresh: float = -0.15,
    vol_win: int = 20,
    vol_lookback: int = 365,
    vol_hi: float = 0.80,
    dwell: int = 5,
) -> pd.DataFrame:
    """多维 regime: 联合趋势/回撤/波动, 输出 3 态 + dwell 滞后防抖.

    状态:
      2 = risk_off (风险厌恶): 跌破均线 且 (深度回撤 或 高波动)
      0 = risk_on  (风险偏好): 站上均线 且 回撤温和 且 非高波动
      1 = neutral  (中性):     其余
    dwell: 连续 N 天确认才切换, 避免抖动 (减少交易成本)。
    """
    trend = dim_trend(close, trend_win)
    dd = dim_drawdown(close, dd_win)
    volp = dim_vol_pctile(close, vol_win, vol_lookback)

    raw_state = pd.Series(1, index=close.index, dtype=int)  # 默认中性
    risk_off = (trend < 0) & ((dd <= dd_thresh) | (volp >= vol_hi))
    risk_on = (trend > 0) & (dd > dd_thresh) & (volp < vol_hi)
    raw_state[risk_off] = 2
    raw_state[risk_on] = 0

    # dwell 滞后: 连续 dwell 天信号一致才真正切换
    confirmed = raw_state.copy()
    cur = int(raw_state.iloc[0])
    candidate = cur
    streak = 0
    for i in range(len(raw_state)):
        s = int(raw_state.iloc[i])
        if s == cur:
            streak = 0
        elif s == candidate:
            streak += 1
            if streak >= dwell:
                cur = candidate
                streak = 0
        else:
            candidate = s
            streak = 1
        confirmed.iloc[i] = cur

    return pd.DataFrame({
        "trend": trend,
        "drawdown": dd,
        "vol_pctile": volp,
        "raw_state": raw_state,
        "regime": confirmed,
    })


# =====================================================================
# 分析 + 可视化
# =====================================================================

def switch_count(s: pd.Series) -> int:
    """状态切换次数 (越少越稳定)."""
    return int((s != s.shift(1)).sum() - 1)


def _shade(ax, index, mask, color, alpha, label):
    """在 mask=True 的区间画背景阴影."""
    mask = mask.fillna(False).values
    in_block = False
    start = None
    labeled = False
    for i, m in enumerate(mask):
        if m and not in_block:
            in_block, start = True, index[i]
        elif not m and in_block:
            ax.axvspan(start, index[i], color=color, alpha=alpha,
                       label=None if labeled else label)
            in_block, labeled = False, True
    if in_block:
        ax.axvspan(start, index[-1], color=color, alpha=alpha,
                   label=None if labeled else label)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_prices()
    close = df["close"].astype(float)

    legacy = regime_legacy(close)
    multi = regime_multidim(close)

    # ── 控制台汇总 ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("【现有 regime】63日收益 ≤ -10% → 熊市")
    print("=" * 60)
    bear_days = int(legacy.sum())
    print(f"  熊市天数: {bear_days} / {len(legacy)} ({bear_days/len(legacy):.1%})")
    print(f"  切换次数: {switch_count(legacy)}")
    print(f"  当前状态: {'🐻 熊市' if legacy.iloc[-1] else '🟢 非熊市'}")

    print("\n" + "=" * 60)
    print("【多维 regime】趋势 + 回撤 + 波动分位 (+5日dwell防抖)")
    print("=" * 60)
    label_map = {0: "🟢 risk_on", 1: "🟡 neutral", 2: "🔴 risk_off"}
    vc = multi["regime"].value_counts().sort_index()
    for k, v in vc.items():
        print(f"  {label_map[k]}: {v} 天 ({v/len(multi):.1%})")
    print(f"  切换次数: {switch_count(multi['regime'])}")
    print(f"  当前状态: {label_map[int(multi['regime'].iloc[-1])]}")
    print(f"  当前维度: trend={multi['trend'].iloc[-1]:+.1%}, "
          f"drawdown={multi['drawdown'].iloc[-1]:+.1%}, "
          f"vol分位={multi['vol_pctile'].iloc[-1]:.0%}")

    # ── 可视化 ──────────────────────────────────────────────────
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(4, 1, figsize=(15, 13), sharex=True,
                             gridspec_kw={"height_ratios": [3, 1, 1, 1]})

    ax = axes[0]
    ax.plot(close.index, close.values, color="#0053e2", lw=1, label="BTC 收盘")
    ax.set_yscale("log")
    _shade(ax, close.index, legacy == 1, "#ea1100", 0.12, "现有: 熊市")
    _shade(ax, close.index, multi["regime"] == 2, "#995213", 0.10, "多维: risk_off")
    ax.set_title("BTC 价格 (log) + Regime 对比  [红=现有熊市, 棕=多维risk_off]", fontsize=12)
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.2)

    ax = axes[1]
    ax.plot(multi.index, multi["trend"] * 100, color="#2a8703", lw=0.8)
    ax.axhline(0, color="gray", ls="--", lw=0.8)
    ax.set_ylabel("vs 200日均线 %")
    ax.grid(alpha=0.2)

    ax = axes[2]
    ax.fill_between(multi.index, multi["drawdown"] * 100, 0, color="#ea1100", alpha=0.4)
    ax.axhline(-15, color="#995213", ls="--", lw=0.8, label="risk_off 阈值 -15%")
    ax.set_ylabel("距90日高点 %")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.2)

    ax = axes[3]
    ax.plot(multi.index, multi["vol_pctile"] * 100, color="#ffc220", lw=0.8)
    ax.axhline(80, color="#ea1100", ls="--", lw=0.8, label="高波动 80分位")
    ax.set_ylabel("波动率分位 %")
    ax.set_xlabel("日期")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.2)

    plt.tight_layout()
    png = OUT_DIR / "regime_analysis.png"
    plt.savefig(png, dpi=120, bbox_inches="tight")
    print(f"\n📊 图已保存: {png}")

    # ── 落 CSV ──────────────────────────────────────────────────
    out = pd.DataFrame({
        "close": close,
        "legacy_bear": legacy,
        "trend": multi["trend"],
        "drawdown": multi["drawdown"],
        "vol_pctile": multi["vol_pctile"],
        "multidim_regime": multi["regime"],
    })
    csv = OUT_DIR / "regime_summary.csv"
    out.to_csv(csv)
    print(f"📄 数据已保存: {csv}")


if __name__ == "__main__":
    main()
