"""底部研判数据层 — 三层框架, 严格右侧 (Layer A/B/C).

实证依据见 docs/reports/btc_bottoming_ic_analysis_20260608.html (V2 事件级校准):
  - Layer A 主信号: Reserve Risk (事件级 180d 超额 +12.4%/命中75%, 底部最稳)
  - Layer B 确认:   AVIV / MVRV-Z 互验 (事件级唯一微弱正 edge)
  - 避坑名单:       LTH-NUPL / NUPL (日频+40% 是重叠幻觉, 事件级翻负 = 左侧接飞刀)
  - Layer C 触发:   站上 SMA50 / 周线 MACD 转正 / 放量突破 (强制右侧, 防接飞刀)

核心不对称 (与顶部相反): 逃顶错=踏空(仅机会成本), 抄底错=接飞刀(真亏本金)。
故底部 A/B 低位仅标"机会区间", 必须 Layer C 右侧确认才提示接回 BTC。
币本位视角: 低位用稳定币接回 BTC, 攒更多币。
"""
from __future__ import annotations

from src.dashboard.data import cycle_core as core

# Layer B 确认信号 (name, csv, 是否首选) — 事件级微弱正 edge
LAYER_B = [
    ("AVIV", "aviv.csv", True),               # 首选 (事件 180d +10.5%)
    ("MVRV-Z", "mvrv_zscore_data.csv", False),  # 事件 180d +6.6%
]
# 避坑名单 — 日频神器幻觉, 事件级翻负 (UI 红标警告, 不计入确认)
AVOID = [
    ("LTH-NUPL", "lth_nupl.csv", "事件级 -35.7%: 左侧首日接飞刀"),
    ("NUPL", "nupl_data.csv", "事件级 -19.3%: 左侧首日接飞刀"),
]
# 分批接回计划 (币本位: 用稳定币换 BTC)
BATCHES = [("第1批", 30), ("第2批", 30), ("第3批", 40)]

# 低分位阈值 (底部: 越低越接近底)
DEEP_Q = 15.0   # A/B 深度低估门槛
WATCH_Q = 30.0  # 接近低估区门槛


def _classify(rr_pct: float | None, lb_low: int, lc_fired: int) -> dict:
    """机会分级 (严格右侧). 返回等级/动作/接回批次/飞刀警告.

    深度机会 = Reserve Risk 极低分位(<=DEEP_Q) 且 Layer B >=2 低位。
    严格右侧: 深度机会但 Layer C 未触发 -> 仅"机会区间", 警告勿接飞刀, 不接回。
    """
    if rr_pct is None:
        return {"key": "unknown", "label": "数据缺失", "color": "#94a3b8",
                "action": "Reserve Risk 数据不可用", "bought": 0, "warn": False}

    deep = rr_pct <= DEEP_Q and lb_low >= 2
    if deep and lc_fired >= 1:
        bought = 3 if (rr_pct <= 5 and lc_fired >= 2) else (2 if lc_fired >= 2 else 1)
        return {"key": "confirm", "label": "右侧确认", "color": "#10b981",
                "action": f"用稳定币分批接回 BTC (已具备右侧确认 {lc_fired}/3)",
                "bought": bought, "warn": False}
    if deep:
        return {"key": "opportunity", "label": "机会区间", "color": "#f59e0b",
                "action": "A/B 深度低估，但右侧未确认 —— 严禁左侧抄底，等 Layer C 信号",
                "bought": 0, "warn": True}
    if rr_pct <= WATCH_Q:
        if rr_pct <= DEEP_Q:   # Layer A 已深度低估, 但 lb_low<2 (B 未共振) 才落到这里
            return {"key": "watch", "label": "关注", "color": "#3b82f6",
                    "action": "Layer A(RR) 已深度低估，但 Layer B 估值类未共振确认；备好稳定币，盯 B 转低 + Layer C 右侧",
                    "bought": 0, "warn": False}
        return {"key": "watch", "label": "关注", "color": "#3b82f6",
                "action": "接近低估区，备好稳定币，开始盯 Layer C 右侧信号",
                "bought": 0, "warn": False}
    return {"key": "idle", "label": "观望", "color": "#94a3b8",
            "action": "离底尚远，持币不动 (HODL)", "bought": 0, "warn": False}


def build(hist_points: int = 120) -> dict:
    """组装底部页 context: Layer A/B/C 读数 + 分级 + 避坑名单 + 历史回放。"""
    rr = core.load_onchain("reserve_risk.csv")
    rr_pct = core.latest_pct(rr)
    rr_val = round(float(rr.iloc[-1]), 6) if rr is not None and not rr.empty else None

    # Layer B (低位计数: 分位 <= DEEP_Q 视为低估)
    lb_rows = []
    for name, fname, preferred in LAYER_B:
        pct = core.latest_pct(core.load_onchain(fname))
        lb_rows.append({"name": name, "pct": pct, "preferred": preferred,
                        "low": (pct is not None and pct <= DEEP_Q)})
    lb_low = sum(1 for r in lb_rows if r["low"])

    # 避坑名单 (展示其分位 + 警告语, 不计入确认)
    avoid_rows = []
    for name, fname, why in AVOID:
        pct = core.latest_pct(core.load_onchain(fname))
        avoid_rows.append({"name": name, "pct": pct, "why": why})

    # 恐惧贪婪 — 极恐特判 (恐惧 != 底部)
    fgi = core.load_series(core.EXTERNAL_DIR / "fear_greed_index.csv", "fgi_value")
    fgi_val = int(fgi.iloc[-1]) if fgi is not None and not fgi.empty else None
    fgi_extreme = fgi_val is not None and fgi_val <= 20

    # Layer C (底部: 右侧确认看涨)
    lc_rows = core.layer_c_signals("bottom")
    lc_fired = sum(1 for r in lc_rows if r["fired"])
    deep = rr_pct is not None and rr_pct <= DEEP_Q and lb_low >= 2
    lc_active = deep  # 仅深度机会时 Layer C 才有意义 (右侧扳机)

    verdict = _classify(rr_pct, lb_low, lc_fired)

    # 历史回放 (RR expanding 分位 + 价格, <=15 分位点灯 = 历史低估机会)
    replay = core.replay_history(rr, DEEP_Q, "bottom", hist_points)
    hist = {"dates": replay["dates"], "rr_pct": replay["pct"],
            "price": replay["price"], "fire": replay["fire"]}

    batches = [{"name": n, "pct": p, "done": i < verdict["bought"]}
               for i, (n, p) in enumerate(BATCHES)]

    return {
        "rr_val": rr_val, "rr_pct": rr_pct,
        "lb_rows": lb_rows, "lb_low": lb_low,
        "avoid_rows": avoid_rows,
        "fgi_val": fgi_val, "fgi_extreme": fgi_extreme,
        "lc_rows": lc_rows, "lc_active": lc_active, "lc_fired": lc_fired,
        "verdict": verdict, "batches": batches, "hist": hist,
        "deep_q": DEEP_Q, "watch_q": WATCH_Q,
    }
