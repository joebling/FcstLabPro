"""市场数据读取 — OHLCV + 外部数据源.

复用 src/performance/backfill.load_ohlcv 读价格 (DRY)。
外部数据 (FGI/funding/多空比/持仓量/宏观) 各有 loader, 统一返回
最近 N 天的 {dates: [...], values: [...]} 给 Chart.js。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXTERNAL_DIR = PROJECT_ROOT / "data" / "external"


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
    """取某列最近 N 天 → {dates, values} (给 Chart.js)."""
    if df is None or col not in df.columns:
        return {"dates": [], "values": []}
    tail = df[col].dropna().tail(days)
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in tail.index],
        "values": [round(float(v), 6) for v in tail.values],
    }


def price_series(days: int = 180) -> dict:
    """OHLCV 收盘价 + 成交量 (复用 performance 的 loader)."""
    from src.performance.backfill import load_ohlcv
    try:
        df = load_ohlcv()
    except (OSError, ValueError):
        return {"dates": [], "close": [], "volume": []}
    tail = df.tail(days)
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in tail.index],
        "close": [round(float(v), 2) for v in tail["close"]],
        "volume": [round(float(v), 2) for v in tail["volume"]],
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
    return {
        "dxy": _series(df, "dxy_close", days),
        "vix": _series(df, "vix_close", days),
        "spx": _series(df, "spx_close", days),
        "gold": _series(df, "gold_close", days),
    }
