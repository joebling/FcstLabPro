"""周期研判整合层 — 单一 regime gate, 单一自适应面板 (DRY).

设计 (解决"两 tab 结论打架"):
  - 周期位置 = Reserve Risk 的 expanding 历史分位 (0=深底, 100=极顶), 单一标尺。
  - regime gate 纯按 RR 分位, 路由到唯一一套自适应三层面板:
      >= TOP_ZONE   -> 顶部区, 面板按逃顶读数 (跌破/极高估/转跌)
      <= BOTTOM_ZONE-> 底部区, 面板按抄底读数 (站上/极低估/转涨)
      其间          -> 中性区, 持有观望
  - 全框架只认一个"周期仓位状态": 顶部区把 BTC 换稳定币 / 底部区把稳定币换回 BTC /
    中性区不动。无"两套剧本"概念, 任一时刻只有一个研判、一个动作、一个仓位倾向。

复用 topping.build() / bottoming.build() 作为两端的指标引擎 (非两个页面),
不重复实现指标逻辑。
"""
from __future__ import annotations

from src.dashboard.data import topping, bottoming, cycle_core as core

TOP_ZONE = 70.0     # RR 分位 >= 此值 = 顶部区
BOTTOM_ZONE = 30.0  # RR 分位 <= 此值 = 底部区


def build(hist_points: int = 120) -> dict:
    """组装周期研判页 context: regime + 当前自适应面板 + 双向回放。"""
    top = topping.build(hist_points)
    bot = bottoming.build(hist_points)
    rr_pct = top.get("rr_pct")  # 顶底共用 Reserve Risk

    if rr_pct is None:
        return {"available": False, "top": top, "bot": bot}

    if rr_pct >= TOP_ZONE:
        regime = {"key": "top", "label": "顶部区", "color": "#f43f5e",
                  "desc": "周期高位 · 逃顶读数", "stance": "倾向把 BTC 换成稳定币"}
        active_verdict = top["verdict"]
    elif rr_pct <= BOTTOM_ZONE:
        regime = {"key": "bottom", "label": "底部区", "color": "#10b981",
                  "desc": "周期低位 · 抄底读数 (严格右侧)", "stance": "倾向把稳定币换回 BTC"}
        active_verdict = bot["verdict"]
    else:
        regime = {"key": "neutral", "label": "中性区", "color": "#3b82f6",
                  "desc": "周期中段 · 离顶离底都有距离", "stance": "持有不动 (HODL)"}
        active_verdict = {"key": "hold", "label": "持有观望",
                          "action": "离顶离底都有距离，持有 BTC 不动，等周期走向两端再行动",
                          "color": "#3b82f6"}

    # 双向历史点灯 (一张图看顶/底两端)
    rr = core.load_onchain("reserve_risk.csv")
    hist = core.replay_dual(rr, TOP_ZONE, BOTTOM_ZONE, hist_points)

    return {
        "available": True,
        "rr_pct": rr_pct, "rr_val": top.get("rr_val"),
        "regime": regime,
        "active_verdict": active_verdict,
        "top": top, "bot": bot,
        "hist": hist,
        "top_zone": TOP_ZONE, "bottom_zone": BOTTOM_ZONE,
    }
