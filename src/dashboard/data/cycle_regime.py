"""RR cycle regime helpers shared by dashboard weak-coupling views.

Single purpose: map a date to the point-in-time Reserve Risk rolling-2y
percentile and classify it into bottom / neutral / top zones.  No model logic,
no trading side effects.  Just boring glue — the best kind of glue.
"""
from __future__ import annotations

from math import isnan
from typing import Iterable

import pandas as pd

from src.dashboard.data import cycle_core as core
from src.dashboard.data.cycle import BOTTOM_ZONE, TOP_ZONE

_REGIME_META = {
    "top": {
        "key": "top",
        "label": "顶部期",
        "short": "顶",
        "color": "rose",
        "hex": "#f43f5e",
        "bg": "bg-rose-50",
        "text": "text-rose-700",
        "border": "border-rose-200",
    },
    "bottom": {
        "key": "bottom",
        "label": "底部期",
        "short": "底",
        "color": "emerald",
        "hex": "#10b981",
        "bg": "bg-emerald-50",
        "text": "text-emerald-700",
        "border": "border-emerald-200",
    },
    "neutral": {
        "key": "neutral",
        "label": "中性期",
        "short": "中",
        "color": "slate",
        "hex": "#64748b",
        "bg": "bg-slate-50",
        "text": "text-slate-600",
        "border": "border-slate-200",
    },
    "unknown": {
        "key": "unknown",
        "label": "未知",
        "short": "?",
        "color": "slate",
        "hex": "#94a3b8",
        "bg": "bg-slate-50",
        "text": "text-slate-400",
        "border": "border-slate-200",
    },
}


def classify_pct(pct: float | None) -> dict:
    """Classify RR percentile into top / bottom / neutral / unknown metadata."""
    if pct is None:
        return dict(_REGIME_META["unknown"], pct=None)
    try:
        val = float(pct)
    except (TypeError, ValueError):
        return dict(_REGIME_META["unknown"], pct=None)
    if isnan(val):
        return dict(_REGIME_META["unknown"], pct=None)
    if val >= TOP_ZONE:
        key = "top"
    elif val <= BOTTOM_ZONE:
        key = "bottom"
    else:
        key = "neutral"
    return dict(_REGIME_META[key], pct=round(val, 1))


def rr_pct_series() -> pd.Series:
    """Return point-in-time RR percentile series; empty if data is unavailable."""
    rr = core.load_onchain("reserve_risk.csv")
    if rr is None or rr.empty:
        return pd.Series(dtype=float)
    return core.position_pct(rr).dropna()


def pct_at(pct_series: pd.Series, date_str: str | None) -> float | None:
    """Point-in-time RR percentile as of ``date_str`` using pandas asof."""
    if not date_str or pct_series.empty:
        return None
    try:
        ts = pd.Timestamp(date_str)
    except (TypeError, ValueError):
        return None
    val = pct_series.asof(ts)
    if val is None or val != val:
        return None
    return float(val)


def context_for_date(date_str: str | None, pct_series: pd.Series | None = None) -> dict:
    """Return regime metadata for a date, including ``pct``."""
    series = rr_pct_series() if pct_series is None else pct_series
    return classify_pct(pct_at(series, date_str))


def annotate_rows(rows: Iterable[dict], date_key: str) -> list[dict]:
    """Copy rows and add ``cycle_regime`` based on each row's date key."""
    series = rr_pct_series()
    out = []
    for row in rows:
        r = dict(row)
        r["cycle_regime"] = context_for_date(r.get(date_key), series)
        out.append(r)
    return out
