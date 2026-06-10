"""Cycle × LightGBM coherence banner for overview.

Weak coupling only: read cycle regime and latest production signal, then explain
whether they agree.  Never mutates state, never downgrades the model output.
"""
from __future__ import annotations

from src.dashboard.data import cycle, ledger


def _signal_key(sig: str | None) -> str:
    s = (sig or "").upper()
    if s in {"BUY", "SELL", "HOLD"}:
        return s
    return "SILENT"


def build(model_name: str) -> dict:
    """Return overview banner context for current cycle regime × latest signal."""
    try:
        c = cycle.build(hist_points=40)
    except Exception:
        c = {"available": False}
    pos = ledger.position(model_name)
    sig = _signal_key(pos.get("last_signal"))

    if not c.get("available") or not pos.get("has_state"):
        return {
            "available": False,
            "reason": "cycle_or_state_missing",
        }

    regime = c["regime"]
    rkey = regime.get("key")
    rr_pct = c.get("rr_pct")

    # Defaults: neutral / informational.
    level = "neutral"
    title = "周期-信号中性"
    message = "周期处于中性区, 当前按模型信号执行即可; 不额外加宏观方向偏置。"
    action = "按模型走, 继续观察 RR 是否靠近 30/70 两端。"
    classes = "bg-slate-50 border-slate-200 text-slate-700"

    if rkey == "top" and sig == "BUY":
        level = "conflict"
        title = "周期-信号冲突"
        message = "周期在顶部区, 但 LightGBM 给 BUY。短线可能有反弹, 但中周期逆风。"
        action = "建议人工降级为 HOLD 或减半仓位, 先看 perfmon 顶部期开仓战绩。"
        classes = "bg-rose-50 border-rose-200 text-rose-800"
    elif rkey == "top" and sig in {"SELL", "HOLD", "SILENT"}:
        level = "aligned"
        title = "周期-信号协同"
        message = "周期在顶部区, 模型也没有要求追多。两者共同指向防守。"
        action = "顺势离场/观望, 不在周期高位硬接飞刀。"
        classes = "bg-emerald-50 border-emerald-200 text-emerald-800"
    elif rkey == "bottom" and sig == "BUY":
        level = "strong_aligned"
        title = "周期-信号双重确认"
        message = "周期在底部区, LightGBM 同步给 BUY。战略位置和战术择时同向。"
        action = "这是最值得重点看的组合, 但仍按原仓位纪律执行。"
        classes = "bg-emerald-50 border-emerald-200 text-emerald-800"
    elif rkey == "bottom" and sig == "SELL":
        level = "conflict"
        title = "周期-信号冲突"
        message = "周期在底部区, 但 LightGBM 给 SELL。可能是短线继续走弱。"
        action = "不急着追空; 建议人工复核, 等右侧确认或下一次 BUY。"
        classes = "bg-amber-50 border-amber-200 text-amber-800"
    elif rkey == "bottom":
        level = "watch"
        title = "周期底部区 · 等战术触发"
        message = "周期位置偏便宜, 但 LightGBM 尚未给 BUY。战略偏多, 战术未扣扳机。"
        action = "耐心等模型触发, 别提前把规则引擎当交易信号。"
        classes = "bg-amber-50 border-amber-200 text-amber-800"

    return {
        "available": True,
        "level": level,
        "title": title,
        "message": message,
        "action": action,
        "classes": classes,
        "signal": sig,
        "signal_date": pos.get("last_signal_date"),
        "regime_key": rkey,
        "regime_label": regime.get("label"),
        "rr_pct": rr_pct,
    }
