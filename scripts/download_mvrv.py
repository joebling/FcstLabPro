#!/usr/bin/env python3
"""下载 BTC MVRV Z-Score 链上估值数据 (bitcoin-data.com).

MVRV Z-Score = (Market Cap - Realized Cap) / σ(Market Cap)
  比原始 MVRV 比值更稳定, 是业界识别周期顶/底的标准指标。
  历史顶部信号: z > 7  (2013-11, 2017-12, 2021-04)
  历史底部信号: z < 0  (2015-01, 2018-12, 2022-12)

数据源选型 (2026-06-01 调研结论):
  ❌ CoinMetrics community: CapRealUSD 是付费 metric, 403 Forbidden
  ❌ BGeometrics: 需 API token + 之前未跑通
  ✅ bitcoin-data.com: 免费/无 KYC/JSON 干净, 但 free tier 只给最近 4 年
     (2022-06 至今), 无法拿 2018-2022 历史 — 须另寻历史数据源合并

数据格式 (API 返回):
  [{"d": "2022-06-01", "unixTs": 1654041600, "mvrvZscore": 0.4243}, ...]

⚠️ 本脚本须在能访问外网的环境 (如 VPS) 运行。
   Walmart jupyter 环境无外网, 不要在那边跑。

Usage:
    python scripts/download_mvrv.py
    python scripts/download_mvrv.py --out data/external/mvrv_zscore_btc.csv
    HTTP_PROXY=... HTTPS_PROXY=... python scripts/download_mvrv.py  # 走代理

输出: data/external/mvrv_zscore_btc.csv
  列: date(index), mvrv_zscore
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = PROJECT_ROOT / "data" / "external" / "mvrv_zscore_btc.csv"

API_URL = "https://bitcoin-data.com/api/v1/mvrv-zscore"


def rows_to_zscore_df(rows: list[dict]) -> pd.DataFrame:
    """把 bitcoin-data.com 原始 rows 转成 date 索引的 mvrv_zscore DataFrame.

    纯函数, 不依赖 requests, 可离线测试。
    """
    if not rows:
        raise SystemExit("❌ bitcoin-data.com 无数据返回, 检查网络/代理")

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["d"]).dt.normalize()
    df["mvrv_zscore"] = pd.to_numeric(df["mvrvZscore"], errors="coerce")
    df = df.set_index("date")[["mvrv_zscore"]].sort_index()

    before = len(df)
    df = df.dropna(subset=["mvrv_zscore"])
    if len(df) < before:
        print(f"  ⚠️ 丢弃 {before - len(df)} 行缺失数据")

    return df


def fetch_mvrv_zscore(max_retries: int = 3) -> pd.DataFrame:
    """从 bitcoin-data.com 拉取 MVRV Z-Score, 返回 date 索引的 DataFrame.

    Note: bitcoin-data.com free tier 不支持 start_date 参数,
    一次性返回最近 4 年全部数据 (~1461 行), 不需要分页。
    """
    print("📡 bitcoin-data.com: 拉取 BTC MVRV Z-Score")
    rows = _get_with_retry(API_URL, max_retries)
    print(f"  · 累计 {len(rows)} 行")
    return rows_to_zscore_df(rows)


def _get_with_retry(url: str, max_retries: int) -> list:
    """带指数退避的 GET (应对限流/瞬断)."""
    import requests  # 懒加载: 仅下载时需要, 离线逻辑测试不依赖

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            wait = 2 ** attempt
            print(f"  ⚠️ 第 {attempt}/{max_retries} 次失败: {exc} — {wait}s 后重试")
            time.sleep(wait)
    raise SystemExit(f"❌ bitcoin-data.com 请求连续失败: {last_err}")


def main() -> int:
    parser = argparse.ArgumentParser(description="下载 BTC MVRV Z-Score (bitcoin-data.com)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="输出 CSV 路径")
    args = parser.parse_args()

    df = fetch_mvrv_zscore()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out)

    print("\n" + "=" * 56)
    print(f"✅ 已保存: {out}")
    print(f"   行数: {len(df)} | 区间: {df.index[0].date()} ~ {df.index[-1].date()}")
    print(f"   MVRV Z-Score: {df['mvrv_zscore'].min():.2f} ~ {df['mvrv_zscore'].max():.2f} "
          f"(均值 {df['mvrv_zscore'].mean():.2f})")
    print("=" * 56)
    print("\n📌 后续步骤:")
    print("   1. 把此 CSV commit/push, 回传到 jupyter 环境")
    print("   2. 找 2018-2022 历史数据源 (free tier 只给最近 4 年)")
    print("   3. 等历史数据齐全后, 跑 E18 实验")
    return 0


if __name__ == "__main__":
    sys.exit(main())
