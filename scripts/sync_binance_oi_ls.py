#!/usr/bin/env python3
"""Binance OI & Long/Short Ratio 累积脚本

功能:
  - 从 Binance API 获取 Open Interest 和 Long/Short Ratio 数据
  - 累加到本地 CSV 文件（自动合并历史数据）
  - 每次运行自动获取最近 ~28 天数据

Usage:
    python scripts/sync_binance_oi_ls.py

开机自启动 (macOS):
    # 添加到 crontab
    crontab -e
    # 添加行: @daily /Users/qiubling/Desktop/projects/FcstLabPro/venv_py310/bin/python /Users/qiubling/Desktop/projects/FcstLabPro/scripts/sync_binance_oi_ls.py
"""

import os
import sys
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd  # requests 惰性导入 (见 download_* 函数) — 模块无网依赖即可 import/mock

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# 路径配置
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "external"
CACHE_DIR = DATA_DIR
SYMBOL = "BTCUSDT"

# ============================================================
# 1. 下载 Long/Short Ratio
# ============================================================


def download_long_short_ratio(symbol: str = "BTCUSDT", period: str = "1d") -> pd.DataFrame:
    """从 Binance 下载 Long/Short Ratio (顶级交易员)"""
    import requests
    base_url = "https://fapi.binance.com/futures/data/topLongShortAccountRatio"

    params = {
        "symbol": symbol,
        "period": period,
        "limit": 500,  # 最多返回约 28 条日线数据
    }

    try:
        resp = requests.get(base_url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"Long/Short Ratio API 请求失败: {e}")
        return pd.DataFrame()

    if not data:
        logger.warning("Long/Short Ratio 无数据返回")
        return pd.DataFrame()

    # 转换为 DataFrame
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("date")
    df = df.rename(columns={
        "longAccount": "long_account",
        "shortAccount": "short_account",
        "longShortRatio": "long_short_ratio",
    })
    df = df[["long_account", "short_account", "long_short_ratio"]].astype(float)

    return df


# ============================================================
# 2. 下载 Open Interest
# ============================================================


def download_open_interest(symbol: str = "BTCUSDT", period: str = "1d") -> pd.DataFrame:
    """从 Binance 下载 Open Interest 历史"""
    import requests
    base_url = "https://fapi.binance.com/futures/data/openInterestHist"

    params = {
        "symbol": symbol,
        "period": period,
        "limit": 500,  # 最多返回约 28 条日线数据
    }

    try:
        resp = requests.get(base_url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"Open Interest API 请求失败: {e}")
        return pd.DataFrame()

    if not data:
        logger.warning("Open Interest 无数据返回")
        return pd.DataFrame()

    # 转换为 DataFrame
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("date")
    df = df.rename(columns={
        "sumOpenInterest": "open_interest",
        "sumOpenInterestValue": "open_interest_usd",
    })
    df = df[["open_interest", "open_interest_usd"]].astype(float)

    return df


# ============================================================
# 3. 合并并保存数据
# ============================================================


def merge_and_save(new_df: pd.DataFrame, cache_path: Path, columns: list[str]) -> None:
    """将新数据合并到现有 CSV"""
    if new_df.empty:
        logger.warning(f"无新数据，跳过保存: {cache_path}")
        return

    # 如果缓存文件存在，读取并合并
    if cache_path.exists():
        old_df = pd.read_csv(cache_path, parse_dates=["date"], index_col="date")
        # 合并：去重，保留最新的
        combined = pd.concat([old_df, new_df])
        combined = combined[~combined.index.duplicated(keep="last")]
        combined = combined.sort_index()
    else:
        combined = new_df

    # 只保留需要的列
    combined = combined[columns]

    # 保存
    combined.to_csv(cache_path)
    logger.info(f"已保存: {cache_path}, {len(combined)} 行, {combined.index[0].date()} ~ {combined.index[-1].date()}")


def sync_oi_ls(symbol: str = SYMBOL) -> dict:
    """同步 OI + 多空比到 data/external (merge 累积历史) — 可 import 入口.

    Binance 接口只给最近 ~30 天, 故用 merge_and_save 逐日累积。
    单源失败只记录, 不抛 (另一源照常)。

    Returns
    -------
    dict : {"long_short": bool, "open_interest": bool} 各源是否成功落盘。
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    result = {"long_short": False, "open_interest": False}

    logger.info("下载 Long/Short Ratio...")
    ls_df = download_long_short_ratio(symbol)
    if not ls_df.empty:
        merge_and_save(ls_df, CACHE_DIR / f"long_short_ratio_{symbol}.csv",
                       ["long_account", "short_account", "long_short_ratio"])
        result["long_short"] = True
    else:
        logger.warning("Long/Short Ratio 下载失败")

    time.sleep(0.5)

    logger.info("下载 Open Interest...")
    oi_df = download_open_interest(symbol)
    if not oi_df.empty:
        merge_and_save(oi_df, CACHE_DIR / f"open_interest_{symbol}.csv",
                       ["open_interest", "open_interest_usd"])
        result["open_interest"] = True
    else:
        logger.warning("Open Interest 下载失败")

    return result


def main():
    """CLI 薄壳 — 委托给 sync_oi_ls()."""
    logger.info("=" * 50)
    logger.info("同步 Binance OI & Long/Short Ratio 数据")
    logger.info("=" * 50)
    result = sync_oi_ls()
    logger.info(f"同步完成! {result}")
    print(f"\n数据保存位置: {DATA_DIR}")
    return result


if __name__ == "__main__":
    main()
