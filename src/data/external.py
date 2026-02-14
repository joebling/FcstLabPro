"""外部数据下载模块 — 宏观因子、链上指标、情绪数据.

支持数据源:
  1. Alternative.me — 恐惧贪婪指数 (FGI)
  2. Yahoo Finance — DXY, VIX, 纳斯达克, 黄金, 美债收益率
  3. Binance API — Funding Rate, Long/Short Ratio
  4. FRED API — M2 货币供应量 (可选)
"""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "external"


def _ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 1. Alternative.me — 恐惧贪婪指数 (FGI)
# ============================================================

def download_fear_greed_index(
    days: int = 0,  # 0 = 全部历史
    cache: bool = True,
) -> pd.DataFrame:
    """下载 Alternative.me 恐惧贪婪指数.

    返回 DataFrame: index=date, columns=[fgi_value, fgi_class]
    fgi_value: 0~100 (0=极度恐惧, 100=极度贪婪)
    """
    _ensure_cache_dir()
    cache_path = CACHE_DIR / "fear_greed_index.csv"

    if cache and cache_path.exists():
        # 检查是否需要更新（超过 1 天则更新）
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(hours=12):
            logger.info(f"使用缓存 FGI 数据: {cache_path}")
            df = pd.read_csv(cache_path, parse_dates=["date"], index_col="date")
            return df

    url = "https://api.alternative.me/fng/"
    params = {"limit": days, "format": "json"}

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as e:
        logger.warning(f"FGI API 请求失败: {e}")
        if cache_path.exists():
            logger.info("使用旧缓存数据")
            return pd.read_csv(cache_path, parse_dates=["date"], index_col="date")
        raise

    rows = []
    for item in data:
        rows.append({
            "date": pd.to_datetime(int(item["timestamp"]), unit="s"),
            "fgi_value": int(item["value"]),
            "fgi_class": item["value_classification"],
        })

    df = pd.DataFrame(rows)
    df = df.set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]

    # 始终保存下载的数据
    df.to_csv(cache_path)
    logger.info(f"FGI 数据已保存: {cache_path}, {len(df)} 条")

    logger.info(f"FGI 下载完成: {df.index[0].date()} ~ {df.index[-1].date()}, {len(df)} 条")
    return df


# ============================================================
# 2. Yahoo Finance — 宏观因子
# ============================================================

MACRO_SYMBOLS = {
    "dxy":  "DX-Y.NYB",     # 美元指数
    "vix":  "^VIX",          # VIX 恐慌指数
    "ndx":  "^IXIC",         # 纳斯达克综合指数
    "spx":  "^GSPC",         # 标普500
    "gold": "GC=F",          # 黄金期货
    "tnx":  "^TNX",          # 美国10年期国债收益率
}


def download_macro_factors(
    symbols: list[str] | None = None,
    start: str = "2018-01-01",
    end: str | None = None,
    cache: bool = True,
) -> pd.DataFrame:
    """下载宏观因子数据（通过 Yahoo Finance）.

    Parameters
    ----------
    symbols : list[str] | None
        要下载的因子列表, 如 ["dxy", "vix", "gold"]。None 表示全部。
    start, end : str
        时间范围
    cache : bool
        是否使用/更新缓存

    Returns
    -------
    pd.DataFrame
        index=date, columns=[dxy_close, dxy_return, vix_close, ...]
    """
    import yfinance as yf

    _ensure_cache_dir()
    cache_path = CACHE_DIR / "macro_factors.csv"

    if cache and cache_path.exists():
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(hours=12):
            logger.info(f"使用缓存宏观数据: {cache_path}")
            return pd.read_csv(cache_path, parse_dates=["date"], index_col="date")

    if symbols is None:
        symbols = list(MACRO_SYMBOLS.keys())

    all_dfs = []
    for name in symbols:
        ticker_symbol = MACRO_SYMBOLS.get(name, name)
        try:
            logger.info(f"下载 {name} ({ticker_symbol})...")
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(start=start, end=end)
            if hist.empty:
                logger.warning(f"{name} 无数据，跳过")
                continue

            hist.index = hist.index.tz_localize(None)  # 去除时区
            hist.index.name = "date"

            # 只保留收盘价
            col = hist["Close"].rename(f"{name}_close")
            all_dfs.append(col)
            logger.info(f"  {name}: {len(hist)} 条 ({hist.index[0].date()} ~ {hist.index[-1].date()})")
            time.sleep(0.3)  # 避免限流
        except Exception as e:
            logger.warning(f"下载 {name} 失败: {e}")
            continue

    if not all_dfs:
        raise RuntimeError("所有宏观因子下载失败")

    df = pd.concat(all_dfs, axis=1)
    df = df.sort_index()

    # 始终保存下载的数据
    df.to_csv(cache_path)
    logger.info(f"宏观数据已保存: {cache_path}")

    logger.info(f"宏观因子下载完成: {len(df)} 行, {len(df.columns)} 列")
    return df


# ============================================================
# 3. Binance API — Funding Rate
# ============================================================

def download_binance_funding_rate(
    symbol: str = "BTCUSDT",
    start: str = "2019-09-01",  # Binance 永续合约上线日期
    cache: bool = True,
) -> pd.DataFrame:
    """下载 Binance 永续合约资金费率.

    资金费率每 8 小时结算一次 (00:00, 08:00, 16:00 UTC)。
    我们按天聚合为日均值和日内极值。

    Returns
    -------
    pd.DataFrame
        index=date, columns=[funding_rate_mean, funding_rate_sum,
                             funding_rate_max, funding_rate_min]
    """
    _ensure_cache_dir()
    cache_path = CACHE_DIR / f"funding_rate_{symbol}.csv"

    if cache and cache_path.exists():
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(hours=12):
            logger.info(f"使用缓存 Funding Rate 数据: {cache_path}")
            return pd.read_csv(cache_path, parse_dates=["date"], index_col="date")

    base_url = "https://fapi.binance.com/fapi/v1/fundingRate"
    start_ts = int(datetime.strptime(start, "%Y-%m-%d").timestamp() * 1000)

    all_data = []
    current_start = start_ts
    limit = 1000

    while True:
        params = {
            "symbol": symbol,
            "startTime": current_start,
            "limit": limit,
        }
        try:
            resp = requests.get(base_url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"Funding Rate API 请求失败: {e}")
            break

        if not data:
            break

        all_data.extend(data)
        current_start = data[-1]["fundingTime"] + 1

        if len(data) < limit:
            break

        time.sleep(0.2)  # 避免限流

    if not all_data:
        logger.warning("Funding Rate 无数据返回")
        if cache_path.exists():
            return pd.read_csv(cache_path, parse_dates=["date"], index_col="date")
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df["fundingTime"] = pd.to_datetime(df["fundingTime"], unit="ms")
    df["fundingRate"] = df["fundingRate"].astype(float)
    df["date"] = df["fundingTime"].dt.date
    df["date"] = pd.to_datetime(df["date"])

    # 按天聚合
    daily = df.groupby("date")["fundingRate"].agg(
        funding_rate_mean="mean",
        funding_rate_sum="sum",
        funding_rate_max="max",
        funding_rate_min="min",
    )
    daily.index.name = "date"

    # 始终保存
    daily.to_csv(cache_path)
    logger.info(f"Funding Rate 已保存: {cache_path}, {len(daily)} 天")

    logger.info(f"Funding Rate 下载完成: {daily.index[0]} ~ {daily.index[-1]}, {len(daily)} 天")
    return daily


# ============================================================
# 4. Binance API — Long/Short Ratio (顶级交易员)
# ============================================================

def download_binance_long_short_ratio(
    symbol: str = "BTCUSDT",
    period: str = "1d",
    start: str = "2020-08-01",  # 该 API 数据从 2020-08 开始可用
    cache: bool = True,
) -> pd.DataFrame:
    """下载 Binance 顶级交易员多空比.

    Returns
    -------
    pd.DataFrame
        index=date, columns=[ls_ratio, long_account, short_account]
    """
    _ensure_cache_dir()
    cache_path = CACHE_DIR / f"long_short_ratio_{symbol}.csv"

    if cache and cache_path.exists():
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(hours=12):
            logger.info(f"使用缓存 Long/Short Ratio: {cache_path}")
            return pd.read_csv(cache_path, parse_dates=["date"], index_col="date")

    base_url = "https://fapi.binance.com/futures/data/topLongShortAccountRatio"
    start_ts = int(datetime.strptime(start, "%Y-%m-%d").timestamp() * 1000)

    all_data = []
    current_start = start_ts
    limit = 500

    while True:
        params = {
            "symbol": symbol,
            "period": period,
            "startTime": current_start,
            "limit": limit,
        }
        try:
            resp = requests.get(base_url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"Long/Short Ratio API 请求失败: {e}")
            break

        if not data:
            break

        all_data.extend(data)
        current_start = data[-1]["timestamp"] + 1

        if len(data) < limit:
            break

        time.sleep(0.2)

    if not all_data:
        logger.warning("Long/Short Ratio 无数据返回")
        if cache_path.exists():
            return pd.read_csv(cache_path, parse_dates=["date"], index_col="date")
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms").dt.normalize()
    df["ls_ratio"] = df["longShortRatio"].astype(float)
    df["long_account"] = df["longAccount"].astype(float)
    df["short_account"] = df["shortAccount"].astype(float)

    daily = df.groupby("date").agg({
        "ls_ratio": "last",
        "long_account": "last",
        "short_account": "last",
    })
    daily.index.name = "date"

    # 始终保存
    daily.to_csv(cache_path)
    logger.info(f"Long/Short Ratio 已保存: {cache_path}")

    logger.info(f"Long/Short Ratio: {daily.index[0]} ~ {daily.index[-1]}, {len(daily)} 天")
    return daily


# ============================================================
# 5. 统一外部数据加载接口
# ============================================================

def load_all_external_data(
    start: str = "2018-01-01",
    end: str | None = None,
    sources: list[str] | None = None,
    cache: bool = True,
) -> pd.DataFrame:
    """加载所有外部数据源，合并为一个 DataFrame.

    Parameters
    ----------
    start : str
        起始日期
    end : str | None
        结束日期
    sources : list[str] | None
        要加载的数据源列表: ["fgi", "macro", "funding_rate", "long_short"]
        None 表示全部加载
    cache : bool
        是否使用缓存

    Returns
    -------
    pd.DataFrame
        合并后的外部数据，index=date
    """
    if sources is None:
        sources = ["fgi", "macro", "funding_rate", "long_short"]

    dfs = []

    if "fgi" in sources:
        try:
            fgi = download_fear_greed_index(cache=cache)
            dfs.append(fgi)
            logger.info(f"✅ FGI: {len(fgi)} 行")
        except Exception as e:
            logger.warning(f"❌ FGI 加载失败: {e}")

    if "macro" in sources:
        try:
            macro = download_macro_factors(start=start, end=end, cache=cache)
            dfs.append(macro)
            logger.info(f"✅ 宏观因子: {len(macro)} 行, {len(macro.columns)} 列")
        except Exception as e:
            logger.warning(f"❌ 宏观因子加载失败: {e}")

    if "funding_rate" in sources:
        try:
            fr = download_binance_funding_rate(cache=cache)
            dfs.append(fr)
            logger.info(f"✅ Funding Rate: {len(fr)} 行")
        except Exception as e:
            logger.warning(f"❌ Funding Rate 加载失败: {e}")

    if "long_short" in sources:
        try:
            ls = download_binance_long_short_ratio(cache=cache)
            dfs.append(ls)
            logger.info(f"✅ Long/Short Ratio: {len(ls)} 行")
        except Exception as e:
            logger.warning(f"❌ Long/Short Ratio 加载失败: {e}")

    if not dfs:
        logger.warning("所有外部数据源加载失败，返回空 DataFrame")
        return pd.DataFrame()

    # 合并: 外连接 + 前向填充 (宏观数据周末无交易)
    merged = pd.concat(dfs, axis=1, join="outer")
    merged = merged.sort_index()

    logger.info(f"外部数据合并完成: {len(merged)} 行, {len(merged.columns)} 列")
    logger.info(f"  时间范围: {merged.index[0]} ~ {merged.index[-1]}")
    logger.info(f"  各列缺失率:\n{merged.isnull().mean().round(3).to_string()}")

    return merged
