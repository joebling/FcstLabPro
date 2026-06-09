"""数据下载模块 — 支持 Binance / Yahoo 数据源."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

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
    import requests  # lazy: 纯函数/守卫逻辑不该被网络库拖累

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


def _guard_raw_overwrite(output_path: Path, allow_overwrite_raw: bool) -> None:
    """防护: 拒绝将下载数据覆盖 data/raw/ 下的不可变训练基准.

    依据 lesson_0602: VPS --download 曾把实时数据写进 data/raw/ 基准文件,
    静默覆盖导致复现链断裂。实时下载一律写 data/live/, 基准只读。
    确需重建基准时显式传 allow_overwrite_raw=True。
    """
    parts = output_path.resolve().parts
    in_raw = "data" in parts and "raw" in parts and parts.index("raw") == parts.index("data") + 1
    if in_raw and output_path.exists() and not allow_overwrite_raw:
        raise PermissionError(
            f"🔴 拒绝覆盖训练基准: {output_path}\n"
            "    data/raw/ 是不可变基准 (sha 锁定), 实时下载请写 data/live/.\n"
            "    确需重建基准: download_binance_klines(..., allow_overwrite_raw=True)\n"
            "    参考: docs/lessons/lesson_0602_download_overwrite_baseline.md"
        )


def _drop_incomplete_tail_bar(
    df: pd.DataFrame,
    interval: str,
    *,
    now_utc: datetime | None = None,
) -> pd.DataFrame:
    """剔除末尾可能的未闭合 bar (lesson_0609 双保险).

    Binance 返回的 K 线列表中, 最后一根可能是未闭合的 partial bar:
      - 1d: 未过 UTC 24:00 的 bar
      - 1w: 未过本周 UTC 周一 00:00 的 bar
      ...

    判定: bar 的 open_time (= index) >= 当前周期起点 → 未闭合 → drop.

    为什么在 downloader 层 drop 而不仅靠下游防护:
      - downloader 写 csv 的那一刻就刪雨量, 都下游 (live_signal / freshness gate /
        人手工打开 csv) 只能看到完整数据, 避免 "多防护依赖" 的获果.
      - lesson_0602 / lesson_0609 共同教训: 越靠上游拦截越好.

    Parameters
    ----------
    interval : '1d', '1w', '1M' — Binance K 线周期
    now_utc : 注入 UTC 时刻, 仅供测试
    """
    if df.empty:
        return df
    now = now_utc or datetime.now(timezone.utc)
    last_open = df.index[-1]
    # 当前周期的起点 (open_time 应处于此点之前才是完整 bar)
    if interval == "1d":
        period_start = pd.Timestamp(now.date())  # UTC 今日 00:00
    elif interval == "1w":
        # Binance 周线的 open_time = 本周一 UTC 00:00
        days_since_monday = now.weekday()
        period_start = pd.Timestamp(now.date()) - pd.Timedelta(days=days_since_monday)
    elif interval == "1M":
        period_start = pd.Timestamp(year=now.year, month=now.month, day=1)
    else:
        # 未知 interval, 保守不 drop 仅会 logger.warning
        logger.warning(f"_drop_incomplete_tail_bar: 未知 interval={interval}, 跳过 drop")
        return df

    if last_open.normalize() >= period_start:
        logger.warning(
            f"剔除未闭合 bar (open_time={last_open.date()}, interval={interval}); "
            f"使用倒数第二根 {df.index[-2].date()} 作为最新完整 bar (lesson_0609)"
        )
        return df.iloc[:-1]
    return df


def download_binance_klines(
    symbol: str = "BTCUSDT",
    interval: str = "1d",
    start: str = "2018-01-01",
    end: str | None = None,
    output_path: str | Path | None = None,
    allow_overwrite_raw: bool = False,
    *,
    drop_incomplete_bar: bool = True,
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
    drop_incomplete_bar : bool, default True
        lesson_0609 双保险: 剔除末尾未闭合 bar.
        默认 True (安全优先). 仅在背面测试 / 调试需要看实时中 bar 时设 False.

    Returns
    -------
    pd.DataFrame
        OHLCV 数据, 列名: open_time(date), open, high, low, close, volume
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

    # lesson_0609: 下载后立即剔除末尾未闭合 bar (双保险, 上游拦截)
    if drop_incomplete_bar:
        df = _drop_incomplete_tail_bar(df, interval)

    if output_path:
        output_path = Path(output_path)
        _guard_raw_overwrite(output_path, allow_overwrite_raw)
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
