#!/usr/bin/env python3
"""下载 BTC MVRV 链上估值数据 (CoinMetrics Community API).

MVRV = Market Value / Realized Value
  - MV (CapMrktCurUSD): 流通市值 = 当前价格 × 流通量
  - RV (CapRealUSD):    已实现市值 = Σ(每个 UTXO 上次移动时的价格)

MVRV 是慢变量, 与价格行为低相关, 能识别整个减半周期:
  历史顶部峰值: 2013-11 (5.5) / 2017-12 (4.7) / 2021-04 (3.9) / 2021-11 (3.0)
  历史底部: ≤1 (跌破持仓成本线, 矿工/长期持有者亏损区)

数据源: CoinMetrics Community API (免费, 无 KYC, 2010 至今, 日频)
  https://docs.coinmetrics.io/api/v4

⚠️ 本脚本须在能访问外网的环境 (如 VPS) 运行, 产出 CSV 后回传到项目环境。
   Walmart jupyter 环境无外网, 不要在那边跑。

Usage:
    python scripts/download_mvrv.py                      # 默认 2018-01-01 至今
    python scripts/download_mvrv.py --start 2010-07-01   # 全历史
    python scripts/download_mvrv.py --out data/external/mvrv_btc.csv
    HTTP_PROXY=http://... HTTPS_PROXY=http://... python scripts/download_mvrv.py  # 走代理

输出: data/external/mvrv_btc.csv
  列: date(index), mv, rv, mvrv
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = PROJECT_ROOT / "data" / "external" / "mvrv_btc.csv"

API_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
METRICS = ["CapMrktCurUSD", "CapRealUSD"]  # MV, RV


def rows_to_mvrv(rows: list[dict]) -> pd.DataFrame:
    """把 CoinMetrics 原始 rows 转成 date 索引的 mv/rv/mvrv DataFrame (纯函数, 可离线测试)."""
    if not rows:
        raise SystemExit("❌ CoinMetrics 无数据返回, 检查网络/代理/日期参数")

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["time"]).dt.tz_localize(None).dt.normalize()
    df["mv"] = pd.to_numeric(df["CapMrktCurUSD"], errors="coerce")
    df["rv"] = pd.to_numeric(df["CapRealUSD"], errors="coerce")
    df = df.set_index("date")[["mv", "rv"]].sort_index()

    # MVRV = 市值 / 已实现市值
    df["mvrv"] = df["mv"] / df["rv"]

    # 健全性: 丢掉任何核心列缺失的行
    before = len(df)
    df = df.dropna(subset=["mv", "rv", "mvrv"])
    if len(df) < before:
        print(f"  ⚠️ 丢弃 {before - len(df)} 行缺失数据")

    return df


def fetch_mvrv(start: str, end: str | None, max_retries: int = 3) -> pd.DataFrame:
    """从 CoinMetrics 拉取 MV/RV 并计算 MVRV, 返回 date 索引的 DataFrame."""
    end = end or datetime.utcnow().strftime("%Y-%m-%d")
    rows: list[dict] = []
    next_page = None

    print(f"📡 CoinMetrics: 拉取 BTC {METRICS} | {start} ~ {end}")

    while True:
        params = {
            "assets": "btc",
            "metrics": ",".join(METRICS),
            "frequency": "1d",
            "start_time": start,
            "end_time": end,
            "page_size": 10000,
        }
        if next_page:
            params["next_page_token"] = next_page

        data = _get_with_retry(params, max_retries)
        batch = data.get("data", [])
        rows.extend(batch)
        print(f"  · 累计 {len(rows)} 行")

        next_page = data.get("next_page_token")
        if not next_page:
            break
        time.sleep(0.25)  # 礼貌限流

    return rows_to_mvrv(rows)


def _get_with_retry(params: dict, max_retries: int) -> dict:
    """带指数退避的 GET (应对限流/瞬断)."""
    import requests  # 懒加载: 仅下载时需要, 离线逻辑测试不依赖

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(API_URL, params=params, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            wait = 2 ** attempt
            print(f"  ⚠️ 第 {attempt}/{max_retries} 次失败: {exc} — {wait}s 后重试")
            time.sleep(wait)
    raise SystemExit(f"❌ CoinMetrics 请求连续失败: {last_err}")


def main() -> int:
    parser = argparse.ArgumentParser(description="下载 BTC MVRV (CoinMetrics)")
    parser.add_argument("--start", default="2018-01-01", help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="结束日期 (默认今天)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="输出 CSV 路径")
    args = parser.parse_args()

    df = fetch_mvrv(args.start, args.end)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out)

    print("\n" + "=" * 56)
    print(f"✅ 已保存: {out}")
    print(f"   行数: {len(df)} | 区间: {df.index[0].date()} ~ {df.index[-1].date()}")
    print(f"   MVRV 范围: {df['mvrv'].min():.2f} ~ {df['mvrv'].max():.2f} "
          f"(均值 {df['mvrv'].mean():.2f})")
    print("=" * 56)
    print("\n📌 下一步: 把此 CSV 回传到项目 data/external/, 再跑 E18 实验")
    return 0


if __name__ == "__main__":
    sys.exit(main())
