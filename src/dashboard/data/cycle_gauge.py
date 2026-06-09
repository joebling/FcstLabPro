"""周期温度计 — 合成"现在大概在周期的顶/中/底"的单一读数 (DRY).

直接复用 topping / bottoming 的 verdict, 保证与两个 tab 完全一致。
周期位置 = Reserve Risk 的 expanding 历史分位 (低=底, 高=顶), 这是最自然的 0-100 标尺。
纯只读, 不预测, 只标"当前在历史分布的哪一档"。
"""
from __future__ import annotations

from src.dashboard.data import topping, bottoming


def build() -> dict:
    """返回温度计 context: 位置/区域/双向 verdict/速读。"""
    top = topping.build()
    bot = bottoming.build()
    rr_pct = top.get("rr_pct")  # 顶底共用 Reserve Risk

    if rr_pct is None:
        return {"available": False}

    if rr_pct >= 70:
        zone, color = "顶部区", "#f43f5e"
    elif rr_pct <= 30:
        zone, color = "底部区", "#10b981"
    else:
        zone, color = "中性区", "#3b82f6"

    # 速读: 用两端 verdict 互证
    readout = (
        f"Reserve Risk 处历史 {rr_pct} 分位（{zone}）· "
        f"顶部研判：{top['verdict']['label']} · 底部研判：{bot['verdict']['label']}"
    )

    return {
        "available": True,
        "position": rr_pct,           # 0=深底, 100=极顶
        "zone": zone,
        "color": color,
        "top_label": top["verdict"]["label"],
        "top_action": top["verdict"]["action"],
        "bot_label": bot["verdict"]["label"],
        "bot_action": bot["verdict"]["action"],
        "readout": readout,
    }
