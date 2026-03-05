"""第二档外部数据下载 — 衍生品 / 情绪 / 市场结构.

支持数据源:
  1. Binance Futures API — Open Interest (真实持仓量)
  2. Coinglass API       — Liquidation (强平数据)
  3. Google Trends       — BTC 搜索热度 (散户关注度)
  4. CoinGecko API       — ETH/BTC Ratio, BTC Dominance

所有函数遵循与 external.py 相同的接口约定:
  - 返回 pd.DataFrame, index=date (DatetimeIndex)
  - 支持 cache=True 本地 CSV 缓存
  - 失败时 fallback 到旧缓存

Usage:
    from src.data.external_tier2 import (
        download_binance_open_interest,
        download_coinglass_liquidations,
        download_google_trends_btc,
        download_coingecko_market_data,
        load_all_tier2_data,
    )
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


def _load_cache_if_fresh(
    path: Path, max_age_hours: float = 12,
) -> pd.DataFrame | None:
    """若缓存存在且未过期, 返回 DataFrame; 否则返回 None."""
    if path.exists():
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(hours=max_age_hours):
            logger.info(f"使用缓存: {path}")
            return pd.read_csv(path, parse_dates=["date"], index_col="date")
    return None


def _load_cache_fallback(path: Path) -> pd.DataFrame:
    """API 失败时 fallback 到旧缓存."""
    if path.exists():
        logger.info(f"API 失败, 使用旧缓存: {path}")
        return pd.read_csv(path, parse_dates=["date"], index_col="date")
    return pd.DataFrame()


# ============================================================
# 1. Binance Futures API — Open Interest (真实持仓量)
# ============================================================

def download_binance_open_interest(
    symbol: str = "BTCUSDT",
    period: str = "1d",
    start: str = "2020-01-01",
    cache: bool = True,
) -> pd.DataFrame:
    """下载 Binance USDT 永续合约 Open Interest 历史.

    数据说明:
      - sumOpenInterest: 合约张数 (BTC 单位)
      - sumOpenInterestValue: 合约价值 (USDT 单位)

    衍生特征 (下载后可自行计算):
      - OI 变化率: oi_pct_change = OI.pct_change()
      - OI/成交量比: oi_volume_ratio = OI / volume
      - OI 偏离均值: oi_zscore = (OI - OI.rolling(30).mean()) / OI.rolling(30).std()

    API: GET /futures/data/openInterestHist
    限制: 每次最多 500 条, 需分页

    Returns
    -------
    pd.DataFrame
        index=date, columns=[oi_btc, oi_usdt]
    """
    _ensure_cache_dir()
    cache_path = CACHE_DIR / f"open_interest_{symbol}.csv"

    if cache:
        cached = _load_cache_if_fresh(cache_path)
        if cached is not None:
            return cached

    base_url = "https://fapi.binance.com/futures/data/openInterestHist"
    start_ts = int(datetime.strptime(start, "%Y-%m-%d").timestamp() * 1000)
    limit = 500

    all_data = []
    current_start = start_ts

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
            logger.warning(f"Open Interest API 请求失败: {e}")
            break

        if not data:
            break

        all_data.extend(data)
        current_start = data[-1]["timestamp"] + 1

        if len(data) < limit:
            break

        time.sleep(0.2)

    if not all_data:
        logger.warning("Open Interest 无数据返回")
        return _load_cache_fallback(cache_path)

    df = pd.DataFrame(all_data)
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms").dt.normalize()
    df["oi_btc"] = df["sumOpenInterest"].astype(float)
    df["oi_usdt"] = df["sumOpenInterestValue"].astype(float)

    daily = df.groupby("date").agg(
        oi_btc=("oi_btc", "last"),
        oi_usdt=("oi_usdt", "last"),
    )
    daily.index.name = "date"

    daily.to_csv(cache_path)
    logger.info(
        f"Open Interest 已保存: {cache_path}, "
        f"{daily.index[0].date()} ~ {daily.index[-1].date()}, {len(daily)} 天"
    )
    return daily


# ============================================================
# 2. Coinglass API — Liquidation (强平数据)
# ============================================================

def download_coinglass_liquidations(
    symbol: str = "BTC",
    time_type: int = 2,  # 1=1h, 2=12h, 3=24h
    cache: bool = True,
    api_key: str | None = None,
) -> pd.DataFrame:
    """下载 Coinglass 全网清算数据.

    数据说明:
      - longLiquidationUsd:  多头清算金额 (USD)
      - shortLiquidationUsd: 空头清算金额 (USD)
      - 净清算 = long - short (正数=多头被清算更多=下跌压力)

    API: GET /public/v2/indicator/liquidation_history
    需要 API Key (免费注册 https://www.coinglass.com/)

    Parameters
    ----------
    symbol : str
        币种, 如 "BTC", "ETH"
    time_type : int
        时间粒度: 1=1h, 2=12h, 3=24h
    cache : bool
        是否使用缓存
    api_key : str | None
        Coinglass API key. 如果为 None, 从环境变量 COINGLASS_API_KEY 读取.

    Returns
    -------
    pd.DataFrame
        index=date, columns=[liq_long_usd, liq_short_usd, liq_net_usd, liq_total_usd]
    """
    import os

    _ensure_cache_dir()
    cache_path = CACHE_DIR / f"liquidations_{symbol}.csv"

    if cache:
        cached = _load_cache_if_fresh(cache_path)
        if cached is not None:
            return cached

    api_key = api_key or os.environ.get("COINGLASS_API_KEY")
    if not api_key:
        logger.warning(
            "Coinglass API key 未设置。"
            "请设置环境变量 COINGLASS_API_KEY 或传入 api_key 参数。"
            "免费注册: https://www.coinglass.com/"
        )
        return _load_cache_fallback(cache_path)

    base_url = "https://open-api-v3.coinglass.com/api/futures/liquidation/v2/history"
    headers = {
        "accept": "application/json",
        "CG-API-KEY": api_key,
    }
    params = {
        "symbol": symbol,
        "time_type": time_type,
    }

    try:
        resp = requests.get(base_url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()
    except Exception as e:
        logger.warning(f"Coinglass Liquidation API 失败: {e}")
        return _load_cache_fallback(cache_path)

    if not result.get("success") or not result.get("data"):
        logger.warning(f"Coinglass 返回异常: {result.get('msg', 'unknown')}")
        return _load_cache_fallback(cache_path)

    rows = []
    for item in result["data"]:
        rows.append({
            "date": pd.to_datetime(item["createTime"], unit="ms").normalize(),
            "liq_long_usd": float(item.get("longLiquidationUsd", 0)),
            "liq_short_usd": float(item.get("shortLiquidationUsd", 0)),
        })

    df = pd.DataFrame(rows)
    daily = df.groupby("date").agg(
        liq_long_usd=("liq_long_usd", "sum"),
        liq_short_usd=("liq_short_usd", "sum"),
    )
    daily["liq_net_usd"] = daily["liq_long_usd"] - daily["liq_short_usd"]
    daily["liq_total_usd"] = daily["liq_long_usd"] + daily["liq_short_usd"]
    daily.index.name = "date"

    daily.to_csv(cache_path)
    logger.info(
        f"Liquidations 已保存: {cache_path}, "
        f"{daily.index[0].date()} ~ {daily.index[-1].date()}, {len(daily)} 天"
    )
    return daily


# ============================================================
# 3. Google Trends — BTC 搜索热度
# ============================================================

def download_google_trends_btc(
    keyword: str = "bitcoin",
    timeframe: str = "2018-01-01 2026-03-01",
    geo: str = "",  # 空 = 全球
    cache: bool = True,
) -> pd.DataFrame:
    """下载 Google Trends 搜索热度 (0~100 相对值).

    数据说明:
      - gt_interest: 0~100 相对热度 (100=该时段最高)
      - 粒度: 日 (timeframe > 90 天时 Google 自动降到周/月)
        为保证日粒度, 自动分段查询 (每段 270 天) 后拼接

    依赖: pip install pytrends

    Returns
    -------
    pd.DataFrame
        index=date, columns=[gt_interest]
    """
    _ensure_cache_dir()
    cache_path = CACHE_DIR / "google_trends_btc.csv"

    if cache:
        cached = _load_cache_if_fresh(cache_path)
        if cached is not None:
            return cached

    try:
        from pytrends.request import TrendReq
    except ImportError:
        logger.error(
            "pytrends 未安装。请运行: "
            "pip install pytrends --index-url https://pypi.ci.artifacts.walmart.com/"
            "artifactory/api/pypi/external-pypi/simple "
            "--allow-insecure-host pypi.ci.artifacts.walmart.com"
        )
        return _load_cache_fallback(cache_path)

    # 解析时间范围
    parts = timeframe.split()
    start_date = datetime.strptime(parts[0], "%Y-%m-%d")
    end_date = datetime.strptime(parts[1], "%Y-%m-%d")

    # 分段查询 (每段 270 天) 以保持日粒度
    segment_days = 270
    segments = []
    seg_start = start_date

    while seg_start < end_date:
        seg_end = min(seg_start + timedelta(days=segment_days), end_date)
        segments.append((seg_start, seg_end))
        # 重叠 30 天用于对齐
        seg_start = seg_end - timedelta(days=30)

    pytrends = TrendReq(hl="en-US", tz=0, timeout=(10, 30))
    all_dfs = []

    for i, (seg_s, seg_e) in enumerate(segments):
        tf = f"{seg_s.strftime('%Y-%m-%d')} {seg_e.strftime('%Y-%m-%d')}"
        try:
            pytrends.build_payload([keyword], timeframe=tf, geo=geo)
            df_seg = pytrends.interest_over_time()
            if df_seg.empty:
                logger.warning(f"Google Trends 段 {i+1}/{len(segments)} 无数据")
                continue
            df_seg = df_seg[[keyword]].rename(columns={keyword: "gt_interest"})
            df_seg.index = df_seg.index.tz_localize(None)
            df_seg.index.name = "date"
            all_dfs.append(df_seg)
            logger.info(f"  段 {i+1}/{len(segments)}: {tf}, {len(df_seg)} 行")
            time.sleep(2)  # Google 限流严格
        except Exception as e:
            logger.warning(f"Google Trends 段 {i+1} 失败: {e}")
            continue

    if not all_dfs:
        logger.warning("Google Trends 全部失败")
        return _load_cache_fallback(cache_path)

    # 拼接 + 用重叠区域做归一化对齐
    result = _stitch_google_trends_segments(all_dfs)

    result.to_csv(cache_path)
    logger.info(
        f"Google Trends 已保存: {cache_path}, "
        f"{result.index[0].date()} ~ {result.index[-1].date()}, {len(result)} 天"
    )
    return result


def _stitch_google_trends_segments(
    segments: list[pd.DataFrame],
) -> pd.DataFrame:
    """将分段查询的 Google Trends 数据拼接对齐.

    每段的 0~100 值是相对于该段最高点的，
    需要用重叠区域计算缩放因子来统一基准。
    """
    if len(segments) == 1:
        return segments[0]

    # 以第一段为基准
    base = segments[0].copy()

    for i in range(1, len(segments)):
        cur = segments[i].copy()
        # 找重叠日期
        overlap = base.index.intersection(cur.index)
        if len(overlap) < 5:
            # 重叠不足, 直接拼接 (不缩放)
            new_dates = cur.index.difference(base.index)
            base = pd.concat([base, cur.loc[new_dates]])
            continue

        # 计算缩放因子: scale = median(base_overlap / cur_overlap)
        base_vals = base.loc[overlap, "gt_interest"].values
        cur_vals = cur.loc[overlap, "gt_interest"].values
        # 避免除零
        valid = cur_vals > 0
        if valid.sum() < 3:
            new_dates = cur.index.difference(base.index)
            base = pd.concat([base, cur.loc[new_dates]])
            continue

        scale = float(np.median(base_vals[valid] / cur_vals[valid]))
        cur["gt_interest"] = (cur["gt_interest"] * scale).round(2)

        # 只取非重叠部分拼接
        new_dates = cur.index.difference(base.index)
        base = pd.concat([base, cur.loc[new_dates]])

    return base.sort_index()


# ============================================================
# 4. CoinGecko API — ETH/BTC Ratio + BTC Dominance
#    (实现在 src/data/external_coingecko.py)
# ============================================================

from src.data.external_coingecko import download_coingecko_market_data  # noqa: E402


# ============================================================
# 5. 统一加载接口
# ============================================================

TIER2_SOURCES = [
    "open_interest",
    "liquidation",
    "google_trends",
    "coingecko_market",
]


def load_all_tier2_data(
    sources: list[str] | None = None,
    cache: bool = True,
) -> pd.DataFrame:
    """加载所有第二档外部数据, 合并为一个 DataFrame.

    Parameters
    ----------
    sources : list[str] | None
        要加载的数据源列表. None = 全部.
        可选: open_interest, liquidation, google_trends, coingecko_market
    cache : bool
        是否使用缓存

    Returns
    -------
    pd.DataFrame
        合并后的数据, index=date
    """
    if sources is None:
        sources = TIER2_SOURCES

    dfs = []
    status = []

    if "open_interest" in sources:
        try:
            oi = download_binance_open_interest(cache=cache)
            if not oi.empty:
                dfs.append(oi)
                status.append(f"  ✅ Open Interest: {len(oi)} 天")
            else:
                status.append("  ⚠️ Open Interest: 无数据")
        except Exception as e:
            status.append(f"  ❌ Open Interest: {e}")

    if "liquidation" in sources:
        try:
            liq = download_coinglass_liquidations(cache=cache)
            if not liq.empty:
                dfs.append(liq)
                status.append(f"  ✅ Liquidations: {len(liq)} 天")
            else:
                status.append("  ⚠️ Liquidations: 无数据 (需要 COINGLASS_API_KEY)")
        except Exception as e:
            status.append(f"  ❌ Liquidations: {e}")

    if "google_trends" in sources:
        try:
            gt = download_google_trends_btc(cache=cache)
            if not gt.empty:
                dfs.append(gt)
                status.append(f"  ✅ Google Trends: {len(gt)} 天")
            else:
                status.append("  ⚠️ Google Trends: 无数据")
        except Exception as e:
            status.append(f"  ❌ Google Trends: {e}")

    if "coingecko_market" in sources:
        try:
            cg = download_coingecko_market_data(cache=cache)
            if not cg.empty:
                dfs.append(cg)
                status.append(f"  ✅ CoinGecko Market: {len(cg)} 天")
            else:
                status.append("  ⚠️ CoinGecko Market: 无数据")
        except Exception as e:
            status.append(f"  ❌ CoinGecko Market: {e}")

    # 打印状态
    for s in status:
        logger.info(s)

    if not dfs:
        logger.warning("所有第二档数据源加载失败")
        return pd.DataFrame()

    merged = pd.concat(dfs, axis=1, join="outer")
    merged = merged.sort_index()

    logger.info(
        f"第二档数据合并完成: {len(merged)} 行, {len(merged.columns)} 列"
    )
    return merged
