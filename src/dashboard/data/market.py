"""市场数据读取 — OHLCV + 外部数据源.

复用 src/performance/backfill.load_ohlcv 读价格 (DRY)。
外部数据 (FGI/funding/多空比/持仓量/宏观) 各有 loader, 统一返回
最近 N 天的 {dates: [...], values: [...]} 给 Chart.js。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXTERNAL_DIR = PROJECT_ROOT / "data" / "external"

# 超过这么多天没更新 → 标记陈旧并在 UI 黄字告警。
# 取 4 天: 容忍 business-day 数据 (macro) 的周末/节假日正常滞后, 又能揪出真陈旧。
STALE_DAYS = 4


def _freshness(last_ts) -> dict:
    """根据某序列最后日期算新鲜度 → {as_of, age_days, stale}.

    单一真相源 (DRY): 所有面板的「数据截止」标注与陈旧告警都走这里。
    """
    if last_ts is None:
        return {"as_of": None, "age_days": None, "stale": True}
    as_of = pd.Timestamp(last_ts).date()
    age = (date.today() - as_of).days
    return {"as_of": as_of.strftime("%Y-%m-%d"), "age_days": age, "stale": age > STALE_DAYS}


def _load_csv(name: str) -> pd.DataFrame | None:
    path = EXTERNAL_DIR / name
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, parse_dates=["date"])
        return df.set_index("date").sort_index()
    except (OSError, ValueError, KeyError):
        return None


def _series(df: pd.DataFrame | None, col: str, days: int) -> dict:
    """取某列最近 N 天 → {dates, series} (给 Chart.js).

    注意 key 用 'series' 不用 'values' — Jinja2 里 dict.values 会撞内置方法。
    """
    if df is None or col not in df.columns:
        return {"dates": [], "series": [], **_freshness(None)}
    tail = df[col].dropna().tail(days)
    last = tail.index[-1] if len(tail) else None
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in tail.index],
        "series": [round(float(v), 6) for v in tail.values],
        **_freshness(last),
    }


def price_series(days: int = 180) -> dict:
    """OHLCV 收盘价 + 成交量 (优先 data/live/ 实时落点, 缺失回退 data/raw/)."""
    from src.dashboard.data import load_display_ohlcv
    try:
        df, _ = load_display_ohlcv()
    except (OSError, ValueError):
        return {"dates": [], "close": [], "volume": [], **_freshness(None)}
    tail = df.tail(days)
    last = tail.index[-1] if len(tail) else None
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in tail.index],
        "close": [round(float(v), 2) for v in tail["close"]],
        "volume": [round(float(v), 2) for v in tail["volume"]],
        **_freshness(last),
    }


def fgi_series(days: int = 180) -> dict:
    """恐惧贪婪指数 + 最新分类."""
    df = _load_csv("fear_greed_index.csv")
    s = _series(df, "fgi_value", days)
    latest_class = None
    latest_value = None
    if df is not None and not df.empty:
        latest_class = str(df["fgi_class"].iloc[-1]) if "fgi_class" in df else None
        latest_value = int(df["fgi_value"].iloc[-1]) if "fgi_value" in df else None
    return {**s, "latest_class": latest_class, "latest_value": latest_value}


def funding_series(days: int = 180) -> dict:
    """资金费率 (mean)."""
    return _series(_load_csv("funding_rate_BTCUSDT.csv"), "funding_rate_mean", days)


def long_short_series(days: int = 180) -> dict:
    """多空比."""
    return _series(_load_csv("long_short_ratio_BTCUSDT.csv"), "long_short_ratio", days)


def open_interest_series(days: int = 180) -> dict:
    """持仓量 (USD)."""
    return _series(_load_csv("open_interest_BTCUSDT.csv"), "open_interest_usd", days)


def macro_series(days: int = 180) -> dict[str, dict]:
    """宏观因子 (DXY/VIX/纳指/标普/黄金/美债)."""
    df = _load_csv("macro_factors.csv")
    last = df.index[-1] if df is not None and not df.empty else None
    return {
        "dxy": _series(df, "dxy_close", days),
        "vix": _series(df, "vix_close", days),
        "spx": _series(df, "spx_close", days),
        "gold": _series(df, "gold_close", days),
        **_freshness(last),  # 面板级新鲜度 (给 macro 卡片标注)
    }
