"""市场页 — 市场环境上下文 (BTC 信号项目此前完全没展示的部分)."""
from __future__ import annotations

from src.dashboard.data import market


def build() -> dict:
    return {
        "price": market.price_series(days=180),
        "fgi": market.fgi_series(days=180),
        "funding": market.funding_series(days=180),
        "long_short": market.long_short_series(days=180),
        "open_interest": market.open_interest_series(days=180),
        "macro": market.macro_series(days=180),
    }
