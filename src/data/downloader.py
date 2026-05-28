"""数据下载模块 — 支持 Binance / Yahoo 数据源."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests

logger = logging.getLogger(__name__)


_BINANCE_KLINES_ENDPOINT = "/api/v3/klines"
_DEFAULT_BINANCE_BASE_URLS = [
    "https://api.binance.com",
    "https://data-api.binance.vision",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    "https://api4.binance.com",
]


def _binance_base_urls() -> list[str]:
    """Return Binance base URLs with env-configurable fallback order."""
    env_urls = []
    for key in ("BINANCE_BASE_URL", "BINANCE_API_BASE_URL", "BINANCE_BASE_URLS"):
        raw = os.getenv(key, "").strip()
        if raw:
            env_urls.extend(part.strip() for part in raw.split(",") if part.strip())

    urls: list[str] = []
    for url in [*env_urls, *_DEFAULT_BINANCE_BASE_URLS]:
        normalized = url.rstrip("/")
        if normalized not in urls:
            urls.append(normalized)
    return urls


def _get_binance_klines(params: dict, base_urls: list[str]) -> tuple[list, str]:
    """Fetch klines from the first Binance endpoint that works."""
    errors: list[str] = []
    for base_url in base_urls:
        url = f"{base_url}{_BINANCE_KLINES_ENDPOINT}"
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json(), base_url
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            errors.append(f"{base_url}: HTTP {status}")
            # 451/403 常见于地域限制；继续试备用端点。
            if status in (403, 451, 418, 429):
                continue
            raise
        except requests.RequestException as exc:
            errors.append(f"{base_url}: {exc}")
            continue

    raise requests.HTTPError("所有 Binance Klines 端点均失败: " + "; ".join(errors))


def download_binance_klines(
    symbol: str = "BTCUSDT",
    interval: str = "1d",
    start: str = "2018-01-01",
    end: str | None = None,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """从 Binance API 下载 K 线数据.

    Parameters
    ----------
    symbol : str
        交易对, 如 "BTCUSDT"
    interval : str
        K线周期, "1d" / "1w"
    start : str
        起始日期 "YYYY-MM-DD"
    end : str | None
        结束日期, None 表示到当前
    output_path : str | Path | None
        保存路径, None 则不保存

    Returns
    -------
    pd.DataFrame
        OHLCV 数据, 列名: open_time, open, high, low, close, volume
    """
    base_urls = _binance_base_urls()
    active_base_url = base_urls[0]
    start_ts = int(datetime.strptime(start, "%Y-%m-%d").timestamp() * 1000)
    end_ts = int(datetime.strptime(end, "%Y-%m-%d").timestamp() * 1000) if end else None

    all_data = []
    current_start = start_ts
    limit = 1000

    while True:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": current_start,
            "limit": limit,
        }
        if end_ts:
            params["endTime"] = end_ts

        data, active_base_url = _get_binance_klines(params, base_urls)

        if not data:
            break

        all_data.extend(data)
        current_start = data[-1][0] + 1  # next ms

        if len(data) < limit:
            break

        logger.info(f"已下载 {len(all_data)} 条记录...")

    df = pd.DataFrame(all_data, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore",
    ])

    # 类型转换
    for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
        df[col] = df[col].astype(float)

    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")

    # 只保留 OHLCV 核心列
    df = df[["open_time", "open", "high", "low", "close", "volume", "quote_volume", "trades"]].copy()
    df = df.rename(columns={"open_time": "date"})
    df = df.set_index("date")

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path)
        logger.info(f"数据已保存至 {output_path}, 共 {len(df)} 条")

    return df


def download_yahoo(
    symbol: str = "BTC-USD",
    start: str = "2018-01-01",
    end: str | None = None,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """从 Yahoo Finance 下载数据."""
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start, end=end)
    df.index.name = "date"

    # 统一列名为小写
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path)
        logger.info(f"数据已保存至 {output_path}, 共 {len(df)} 条")

    return df
