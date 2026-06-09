"""顶部研判数据层 — 三层精英制危险分级 (Layer A/B/C).

实证依据见 docs/reports/btc_topping_ic_analysis_20260608.html:
  - Layer A 主信号: Reserve Risk (唯一 |t|>=2 的真 alpha)
  - Layer B 确认:   LTH-MVRV(首选)/LTH-SOPR/LTH-NUPL/MVRV-Z/Puell (Regime 依赖)
  - Layer C 触发:   SMA50 破位 / 周线 MACD 转负 / 吊灯止损 (仅 A/B 警报后激活)

通用分位引擎/技术面/历史回放已抽到 cycle_core (DRY, 与底部共用)。
本模块只保留顶部专属: Layer B 清单、分批计划、危险分级阈值。
币本位视角: 高位减仓换稳定币, 为低位接回攒更多 BTC。
"""
from __future__ import annotations

from src.dashboard.data import cycle_core as core

# Layer B 确认信号 (name -> csv 文件名), LTH-MVRV 为实证首选
LAYER_B = [
    ("LTH-MVRV", "lth_mvrv.csv", True),   # 首选 (90d IC -0.296)
    ("LTH-SOPR", "lth_sopr.csv", False),
    ("LTH-NUPL", "lth_nupl.csv", False),
    ("MVRV-Z", "mvrv_zscore_data.csv", False),
    ("Puell", "puell_multiple_data.csv", False),
]
# 分批撤退计划 (与框架 §5.1 一致)
BATCHES = [("第1批", 30), ("第2批", 30), ("第3批", 40)]


def _classify(rr_pct: float | None, lb_high: int, lc_fired: int) -> dict:
    """危险分级 (框架 §5.1). 返回等级/动作/目标仓位/应减批次. 币本位: 减仓换稳定币。"""
    if rr_pct is None:
        return {"key": "unknown", "label": "数据缺失", "color": "#94a3b8",
                "action": "Reserve Risk 数据不可用", "target": None, "sold": 0}
    if rr_pct >= 95 and lb_high >= 3:
        sold = 3 if lc_fired >= 1 else 2
        return {"key": "crit", "label": "极危", "color": "#f43f5e",
                "action": "减第 2 批换稳定币" + ("，Layer C 已触发→清第 3 批" if lc_fired else "（等 Layer C 清第 3 批）"),
                "target": 100 - sum(p for _, p in BATCHES[:sold]), "sold": sold}
    if rr_pct >= 85 and lb_high >= 2:
        return {"key": "danger", "label": "危险", "color": "#f59e0b",
                "action": "分批减仓第 1 批换稳定币 (~30%)", "target": 70, "sold": 1}
    if rr_pct >= 70:
        return {"key": "warn", "label": "警示", "color": "#fbbf24",
                "action": "停止加仓，开始盯 Layer C", "target": 100, "sold": 0}
    return {"key": "safe", "label": "安全", "color": "#10b981",
            "action": "满仓持有 BTC", "target": 100, "sold": 0}


def build(hist_points: int = 120) -> dict:
    """组装顶部页 context: Layer A/B/C 读数 + 分级 + 历史回放序列。"""
    rr = core.load_onchain("reserve_risk.csv")
    rr_pct = core.latest_pct(rr)
    rr_val = round(float(rr.iloc[-1]), 6) if rr is not None and not rr.empty else None

    # Layer B
    lb_rows = []
    for name, fname, preferred in LAYER_B:
        pct = core.latest_pct(core.load_onchain(fname))
        lb_rows.append({"name": name, "pct": pct, "preferred": preferred,
                        "high": (pct is not None and pct >= 85)})
    lb_high = sum(1 for r in lb_rows if r["high"])

    # Layer C (顶部: 破位看跌)
    lc_rows = core.layer_c_signals("top")
    lc_fired = sum(1 for r in lc_rows if r["fired"])
    lc_active = (rr_pct is not None and rr_pct >= 85 and lb_high >= 2)

    verdict = _classify(rr_pct, lb_high, lc_fired)

    # 历史回放 (RR expanding 分位 + 价格, >=85 点灯); 兼容旧模板 key (rr_pct)
    replay = core.replay_history(rr, 85.0, "top", hist_points)
    hist = {"dates": replay["dates"], "rr_pct": replay["pct"],
            "price": replay["price"], "fire": replay["fire"]}

    batches = [{"name": n, "pct": p, "done": i < verdict["sold"]}
               for i, (n, p) in enumerate(BATCHES)]

    return {
        "rr_val": rr_val, "rr_pct": rr_pct,
        "lb_rows": lb_rows, "lb_high": lb_high,
        "lc_rows": lc_rows, "lc_active": lc_active, "lc_fired": lc_fired,
        "verdict": verdict, "batches": batches, "hist": hist,
    }
