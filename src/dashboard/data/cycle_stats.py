"""周期 regime 事件研究 — 历史跨入顶/底区后 BTC 前瞻收益统计.

供周期研判邮件的「历史战绩」用。纯只读 event study, 不下单 (周期研判无 ledger,
不同于模型信号的真实成交账本)。

方法: 在 RR rolling-2y 分位序列上, 找每次【从区外跨入】顶部区(>=TOP)/底部区(<=BOTTOM)
的事件日, 算其后 horizon 天的 BTC 收益。汇总: 事件数 / 均收益 / 方向命中率。

命中定义 (币本位逻辑):
  顶部区: 进区应减仓换稳定币, 后续【下跌】= 研判对 -> 命中
  底部区: 进区应买回 BTC,      后续【上涨】= 研判对 -> 命中

DRY: 分位引擎复用 cycle_core.position_pct (与 dashboard / 邮件 regime 同口径)。
"""
from __future__ import annotations

import pandas as pd

from src.dashboard.data import cycle_core as core


def _cross_in_events(pct: pd.Series, zone: float, side: str) -> list:
    """找跨入事件日: side='top' 上穿 zone (prev<zone<=v); 'bottom' 下穿 (prev>zone>=v)."""
    events: list = []
    prev = None
    for d, v in pct.items():
        if v != v:  # NaN: 跳过但重置 prev
            prev = None
            continue
        if prev is not None:
            if side == "top" and prev < zone <= v:
                events.append(d)
            elif side == "bottom" and prev > zone >= v:
                events.append(d)
        prev = v
    return events


def _fwd_returns(price: pd.Series, event_dates: list, horizon: int) -> list:
    """每个事件日后 horizon 天的收益 (用区间内最后一个可得价 vs 事件日价)."""
    out: list = []
    for d in event_dates:
        p0 = price.asof(d)
        window = price[(price.index > d) & (price.index <= d + pd.Timedelta(days=horizon))]
        if p0 is None or p0 != p0 or window.empty:
            continue
        out.append(float(window.iloc[-1]) / float(p0) - 1.0)
    return out


def _summarize(rets: list, side: str) -> dict:
    """汇总: 样本数 / 均收益% / 方向命中率% (顶部跌为胜, 底部涨为胜)."""
    n = len(rets)
    if n == 0:
        return {"n": 0, "avg": None, "hit": None}
    avg = sum(rets) / n
    hits = sum(1 for r in rets if (r < 0 if side == "top" else r > 0))
    return {"n": n, "avg": round(avg * 100, 1), "hit": round(hits / n * 100)}


def regime_event_study(
    rr: pd.Series | None,
    price: pd.Series | None,
    top_zone: float,
    bottom_zone: float,
    horizons: tuple = (30, 90),
) -> dict:
    """周期事件研究主入口. 纯函数 (rr/price 由调用方注入, 便于测试 + DRY)。

    返回 {available, horizons, top:{events, h30:{n,avg,hit}, ...}, bottom:{...}}。
    """
    if rr is None or rr.empty or price is None or price.empty:
        return {"available": False}
    pct = core.position_pct(rr).dropna()
    if pct.empty:
        return {"available": False}
    top_ev = _cross_in_events(pct, top_zone, "top")
    bot_ev = _cross_in_events(pct, bottom_zone, "bottom")
    out: dict = {
        "available": True,
        "horizons": list(horizons),
        "top": {"events": len(top_ev)},
        "bottom": {"events": len(bot_ev)},
    }
    for h in horizons:
        out["top"][f"h{h}"] = _summarize(_fwd_returns(price, top_ev, h), "top")
        out["bottom"][f"h{h}"] = _summarize(_fwd_returns(price, bot_ev, h), "bottom")
    return out
