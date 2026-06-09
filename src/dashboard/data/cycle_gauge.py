"""周期温度计 — 总览页用的精简读数 (委托 cycle, DRY).

不再自带阈值/重复 build, 直接复用 cycle.build() 的 regime gate 结果,
保证温度计与周期研判页 100% 一致。
"""
from __future__ import annotations

from src.dashboard.data import cycle


def build() -> dict:
    """返回温度计 context: 位置/区域/双向 verdict (取自 cycle 的单一真相)。"""
    c = cycle.build()
    if not c.get("available"):
        return {"available": False}

    regime = c["regime"]
    top_v = c["top"]["verdict"]
    bot_v = c["bot"]["verdict"]
    return {
        "available": True,
        "position": c["rr_pct"],      # 0=深底, 100=极顶
        "zone": regime["label"],
        "color": regime["color"],
        "top_label": top_v["label"],
        "top_action": top_v["action"],
        "bot_label": bot_v["label"],
        "bot_action": bot_v["action"],
    }
