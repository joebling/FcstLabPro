#!/usr/bin/env python3
"""市场展示数据同步 — 独立 best-effort 任务 (与信号 pipeline 解耦).

刷新 dashboard 市场页用的 4 个展示数据源:
  - 资金费率 funding_rate_BTCUSDT.csv   (Binance, 全量历史自愈)
  - 多空比   long_short_ratio_BTCUSDT.csv (Binance, 仅最近~30天, merge 累积)
  - 持仓量   open_interest_BTCUSDT.csv    (Binance, 仅最近~30天, merge 累积)
  - 宏观     macro_factors.csv            (yfinance, 全量历史自愈)

设计要点 (见操作手册 Layer 0 边界):
  * 这些**不是**生产模型 (E1/E8) 的特征 — 模型只吃 OHLCV+FGI。
    故本任务**完全独立**于信号 pipeline, 挂了只影响市场图, 信号毫发无伤。
  * **每源独立 try/except** — 单源失败 (如 yfinance 抽风) 不传染其他源。
  * FGI 不在此处刷 — 它是生产特征, 由信号 pipeline stage 2 每日下载 (单一真相源)。
  * OI/多空比 Binance 只给最近 ~30 天, 历史无法回补; merge_and_save 从今天起累积。

退出码: 全部成功=0; 任一源失败=1 (供 cron/监控告警)。

Usage:
    python scripts/sync_market_data.py
"""
from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

# 直接运行时确保能 import src.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sync_market_data")

# 下载结果的最新日期超过这么多天 → 视为未真正刷新。
# 关键: 许多 download_* 函数在 API 失败时会回退读旧缓存(非空 stale df),
# 仅检查 not df.empty 会被旧缓存骗过 → 谎报成功。故改用新鲜度判定。
# 取 4 天: 对齐 dashboard market.STALE_DAYS, 容忍 macro business-day 周末滞后。
FRESH_MAX_AGE_DAYS = 4


def _is_fresh(df: pd.DataFrame | None) -> bool:
    """下载结果是否真正新鲜 (最新日期在 FRESH_MAX_AGE_DAYS 内)。

    用于识破 "API 失败→回退旧缓存" 的假成功: 空/陈旧都算失败。
    """
    if df is None or df.empty:
        return False
    try:
        latest = pd.Timestamp(df.index.max()).date()
    except (ValueError, TypeError):
        return False
    return (date.today() - latest).days <= FRESH_MAX_AGE_DAYS


def _refresh_funding() -> bool:
    """资金费率 — 全量历史自愈 (cache=False 强制刷)。

     走 Binance 期货接口 fapi.binance.com, 部分地区被 451 封锁 →
    download 会回退旧缓存, 故用 _is_fresh 识破。
    """
    from src.data.external import download_binance_funding_rate
    return _is_fresh(download_binance_funding_rate(cache=False))


def _refresh_oi_ls() -> bool:
    """OI + 多空比 — merge 累积 (复用 sync_binance_oi_ls.sync_oi_ls, DRY)。

    download 失败返回空 df → sync_oi_ls 直接报 False, 无需 _is_fresh。
    """
    from scripts.sync_binance_oi_ls import sync_oi_ls
    r = sync_oi_ls()
    # 两个子源都成功才算这一源 OK
    return bool(r.get("long_short")) and bool(r.get("open_interest"))


def _refresh_macro() -> bool:
    """宏观 — 全量历史自愈 (cache=False)。yfinance 最易抽风, 隔离在此。"""
    from src.data.external import download_macro_factors
    return _is_fresh(download_macro_factors(cache=False))


# 源名 → 刷新函数 (单一注册表, 加新源只改这里)
SOURCES = {
    "funding": _refresh_funding,
    "oi_ls": _refresh_oi_ls,
    "macro": _refresh_macro,
}


def sync_market_data() -> dict[str, bool]:
    """逐源刷新市场展示数据, 单源失败不传染。

    Returns
    -------
    dict : {源名: 是否成功}
    """
    results: dict[str, bool] = {}
    for name, fn in SOURCES.items():
        try:
            ok = fn()
            results[name] = ok
            logger.info("[%s] %s", name, "OK" if ok else "空数据")
        except Exception as exc:  # noqa: BLE001 — best-effort: 任何异常都隔离
            results[name] = False
            logger.warning("[%s] 失败: %s", name, exc)
    return results


def main() -> int:
    logger.info("=" * 50)
    logger.info("市场展示数据同步 (best-effort, 独立于信号 pipeline)")
    logger.info("=" * 50)
    results = sync_market_data()

    ok = [n for n, v in results.items() if v]
    bad = [n for n, v in results.items() if not v]
    logger.info("汇总 — 成功: %s | 失败: %s", ok or "无", bad or "无")
    print(f"\n市场数据同步: 成功 {len(ok)}/{len(results)} 源"
          + (f"; 失败: {', '.join(bad)}" if bad else ""))

    # 任一源失败 → 退出码 1, 供监控告警 (但已成功的源照常落盘)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
