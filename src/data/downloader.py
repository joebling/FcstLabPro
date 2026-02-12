"""数据下载模块 — 支持 Binance / Yahoo 数据源."""

import logging
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests

logger = logging.getLogger(__name__)


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
    base_url = "https://api.binance.com/api/v3/klines"
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

        resp = requests.get(base_url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

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
