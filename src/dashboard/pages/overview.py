"""总览页 — 一眼看全貌.

KPI 行 + 信号日历 + 价格信号叠加图 + 信号分布环形图。
"""
from __future__ import annotations

import calendar as _cal
from datetime import date

from src.dashboard.data import signals, market, ledger
from src.dashboard.data import coherence, cycle_gauge
from src.performance import service


def _calendar_grid(year: int, month: int) -> list:
    """返回月历网格 (周一起头), 空格为 None, 否则 {day, date}."""
    grid = []
    first_wd, days_in_month = _cal.monthrange(year, month)  # first_wd: 0=Mon
    for _ in range(first_wd):
        grid.append(None)
    for d in range(1, days_in_month + 1):
        grid.append({"day": d, "date": f"{year:04d}-{month:02d}-{d:02d}"})
    return grid


def build(model_name: str | None) -> dict:
    # 周期温度计 (与 model 无关, 顶/底 tab 同源) — 即便无模型也显示
    try:
        gauge = cycle_gauge.build()
    except Exception:
        gauge = {"available": False}

    if not model_name:
        return {"has_data": False, "gauge": gauge}

    latest = signals.latest_signal(model_name) or {}
    price = market.price_series(days=120)
    dist = signals.signal_distribution(model_name)

    # 今日涨跌 (最后两根收盘价)
    closes = price.get("close", [])
    dates = price.get("dates", [])
    chg_pct = None
    if len(closes) >= 2 and closes[-2]:
        chg_pct = round((closes[-1] / closes[-2] - 1) * 100, 2)
    price_date = dates[-1] if dates else None

    # performance 汇总 (理论 T=21 信号质量 IC/命中)
    try:
        summary, _ = service.get_summary(model_name)
    except Exception:
        summary = {}

    # 生产持仓账本 (与邮件同源): 当前持仓 + regime + 真实交易战绩
    position = ledger.position(model_name)
    trades = ledger.trade_history(model_name)
    coh = coherence.build(model_name)

    # 当月信号日历
    today = date.today()
    calendar = signals.signal_calendar(model_name, today.year, today.month)

    # 价格图上标 BUY 点
    hist = signals.signal_history(model_name, limit=400)
    buy_dates = {s["date"] for s in hist if s.get("signal") == "BUY"}
    buy_points = [
        {"x": d, "y": c}
        for d, c in zip(price.get("dates", []), closes)
        if d in buy_dates
    ]

    return {
        "has_data": True,
        "latest": latest,
        "price": price,
        "current_price": closes[-1] if closes else None,
        "price_date": price_date,
        "chg_pct": chg_pct,
        "summary": summary,
        "position": position,
        "trades": trades,
        "coherence": coh,
        "distribution": dist,
        "calendar": calendar,
        "calendar_grid": _calendar_grid(today.year, today.month),
        "cal_year": today.year,
        "cal_month": today.month,
        "buy_points": buy_points,
        "gauge": gauge,
    }
