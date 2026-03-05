"""CoinGecko API 数据下载器 — ETH/BTC Ratio + BTC Dominance.

从 external_tier2.py 拆分出来, 保持文件在 600 行以内。

使用:
    from src.data.external_coingecko import download_coingecko_market_data
"""

import logging
import os
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


def _load_cache_if_fresh(
    path: Path, max_age_hours: float = 12,
) -> pd.DataFrame | None:
    if path.exists():
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(hours=max_age_hours):
            logger.info(f"使用缓存: {path}")
            return pd.read_csv(path, parse_dates=["date"], index_col="date")
    return None


def _load_cache_fallback(path: Path) -> pd.DataFrame:
    if path.exists():
        logger.info(f"API 失败, 使用旧缓存: {path}")
        return pd.read_csv(path, parse_dates=["date"], index_col="date")
    return pd.DataFrame()


# ============================================================
# 主入口
# ============================================================

def download_coingecko_market_data(
    cache: bool = True,
    api_key: str | None = None,
) -> pd.DataFrame:
    """下载 CoinGecko 市场结构数据.

    包含:
      - eth_btc_ratio: ETH 以 BTC 计价 (市场风格轮动指标)
      - btc_mcap_usd: BTC USD 市值
      - btc_dominance_proxy: BTC 市值 / 90日均值 (市占率代理)

    ETH/BTC:
      - 上升 = ETH 跑赢 BTC = 山寨季 / 风险偏好上升
      - 下降 = BTC 强势 = 避险 / 资金回流主流

    免费 Demo key 注册: https://www.coingecko.com/en/api/pricing
    设置环境变量 COINGECKO_API_KEY 或传入 api_key。

    Returns
    -------
    pd.DataFrame
        index=date, columns=[eth_btc_ratio, btc_mcap_usd, btc_dominance_proxy]
    """
    _ensure_cache_dir()
    cache_path = CACHE_DIR / "coingecko_market.csv"

    if cache:
        cached = _load_cache_if_fresh(cache_path)
        if cached is not None:
            return cached

    cg_key = api_key or os.environ.get("COINGECKO_API_KEY")
    headers = {}
    if cg_key:
        headers["x-cg-demo-api-key"] = cg_key
        logger.info("CoinGecko: 使用 API key")
    else:
        logger.warning(
            "CoinGecko API key 未设置, market_chart 可能被限制。"
            "免费注册: https://www.coingecko.com/en/api/pricing "
            "然后设置 COINGECKO_API_KEY 环境变量。"
        )

    dfs = []

    eth_btc = _download_eth_btc(headers)
    if eth_btc is not None:
        dfs.append(eth_btc)

    time.sleep(1.5)

    btc_dom = _download_btc_dominance(headers)
    if btc_dom is not None:
        dfs.append(btc_dom)

    if not dfs:
        logger.warning("CoinGecko 全部失败")
        return _load_cache_fallback(cache_path)

    result = pd.concat(dfs, axis=1).sort_index()
    result.index.name = "date"

    result.to_csv(cache_path)
    logger.info(
        f"CoinGecko 市场数据已保存: {cache_path}, "
        f"{result.index[0].date()} ~ {result.index[-1].date()}, {len(result)} 天"
    )
    return result


# ============================================================
# 内部函数
# ============================================================

def _download_eth_btc(headers: dict) -> pd.DataFrame | None:
    """获取 ETH 以 BTC 计价的历史价格."""
    url = "https://api.coingecko.com/api/v3/coins/ethereum/market_chart"
    params = {"vs_currency": "btc", "days": "max", "interval": "daily"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        prices = resp.json().get("prices", [])
    except Exception as e:
        logger.warning(f"CoinGecko ETH/BTC 失败: {e}")
        return None

    if not prices:
        return None

    df = pd.DataFrame(prices, columns=["timestamp", "eth_btc_ratio"])
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms").dt.normalize()
    result = df.groupby("date")["eth_btc_ratio"].last().to_frame()
    result.index.name = "date"
    logger.info(f"ETH/BTC: {result.index[0].date()} ~ {result.index[-1].date()}, {len(result)} 天")
    return result


def _download_btc_dominance(headers: dict) -> pd.DataFrame | None:
    """推算 BTC 市占率历史 (BTC mcap + 当前快照).

    CoinGecko 免费 API 无历史 dominance, 用 BTC 市值 / 90日均值作为 proxy。
    """
    btc_mcap = _fetch_market_cap("bitcoin", headers)
    if btc_mcap is None:
        return None

    time.sleep(1.5)

    # 当前 dominance 快照
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/global",
            headers=headers, timeout=30,
        )
        resp.raise_for_status()
        global_data = resp.json().get("data", {})
        current_dominance = global_data.get("market_cap_percentage", {}).get("btc")
    except Exception as e:
        logger.warning(f"CoinGecko /global 失败: {e}")
        return None

    if not current_dominance:
        logger.warning("CoinGecko /global 数据不完整")
        return None

    result = btc_mcap.rename(columns={"market_cap": "btc_mcap_usd"})
    result["btc_dominance_proxy"] = (
        result["btc_mcap_usd"] / result["btc_mcap_usd"].rolling(90).mean()
    )

    logger.info(
        f"BTC Dominance (proxy): {result.index[0].date()} ~ {result.index[-1].date()}, "
        f"{len(result)} 天, 当前真实 dominance={current_dominance:.1f}%"
    )
    return result


def _fetch_market_cap(coin_id: str, headers: dict) -> pd.DataFrame | None:
    """获取指定币种的 USD 市值历史."""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": "max", "interval": "daily"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        mcaps = resp.json().get("market_caps", [])
    except Exception as e:
        logger.warning(f"CoinGecko {coin_id} market_chart 失败: {e}")
        return None

    if not mcaps:
        return None

    df = pd.DataFrame(mcaps, columns=["timestamp", "market_cap"])
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms").dt.normalize()
    result = df.groupby("date")["market_cap"].last().to_frame()
    result.index.name = "date"
    return result
