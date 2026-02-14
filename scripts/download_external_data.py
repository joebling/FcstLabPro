#!/usr/bin/env python3
"""下载外部数据（宏观因子、FGI、Funding Rate 等）.

Usage:
    python scripts/download_external_data.py                     # 下载全部
    python scripts/download_external_data.py --sources fgi macro  # 指定数据源
    python scripts/download_external_data.py --no-cache           # 强制刷新
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logging import setup_logging
from src.data.external import (
    download_fear_greed_index,
    download_macro_factors,
    download_binance_funding_rate,
    download_binance_long_short_ratio,
    load_all_external_data,
)


def main():
    parser = argparse.ArgumentParser(description="下载外部数据")
    parser.add_argument(
        "--sources", nargs="*", default=None,
        choices=["fgi", "macro", "funding_rate", "long_short"],
        help="要下载的数据源，默认全部",
    )
    parser.add_argument("--start", default="2018-01-01", help="起始日期")
    parser.add_argument("--no-cache", action="store_true", help="强制重新下载")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    setup_logging(level=args.log_level)
    cache = not args.no_cache

    print("=" * 60)
    print("📥 FcstLabPro 外部数据下载")
    print("=" * 60)

    merged = load_all_external_data(
        start=args.start,
        sources=args.sources,
        cache=cache,
    )

    print(f"\n✅ 下载完成!")
    print(f"📊 合并数据: {len(merged)} 行, {len(merged.columns)} 列")
    if len(merged) > 0:
        print(f"📅 时间范围: {merged.index[0].date()} ~ {merged.index[-1].date()}")
        print(f"\n📋 各列缺失率:")
        for col in merged.columns:
            miss = merged[col].isnull().mean()
            status = "✅" if miss < 0.1 else "⚠️" if miss < 0.5 else "❌"
            print(f"  {status} {col}: {miss:.1%}")

    print(f"\n📁 数据保存在: data/external/")


if __name__ == "__main__":
    main()
