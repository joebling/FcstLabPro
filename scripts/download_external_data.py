#!/usr/bin/env python3
"""下载外部数据（包含第一档 + 第二档）.

第一档 (已有): FGI, 宏观因子, Funding Rate, Long/Short Ratio
第二档 (新增): Open Interest, Liquidation, Google Trends, ETH/BTC + BTC Dominance

Usage:
    python scripts/download_external_data.py                         # 全部下载
    python scripts/download_external_data.py --sources fgi macro      # 第一档指定
    python scripts/download_external_data.py --tier2                  # 只下载第二档
    python scripts/download_external_data.py --tier2 --sources open_interest coingecko_market
    python scripts/download_external_data.py --all                   # 两档全下
    python scripts/download_external_data.py --no-cache              # 强制刷新
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 自动加载 .env 文件中的 API key
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from src.utils.logging import setup_logging


def download_tier1(sources: list[str] | None, start: str, cache: bool):
    """下载第一档数据."""
    from src.data.external import load_all_external_data

    print("\n" + "─" * 50)
    print("📥 第一档: FGI / 宏观因子 / Funding Rate / Long-Short Ratio")
    print("─" * 50)

    merged = load_all_external_data(start=start, sources=sources, cache=cache)

    if len(merged) > 0:
        print(f"  ✅ {len(merged)} 行, {len(merged.columns)} 列")
        print(f"  📅 {merged.index[0].date()} ~ {merged.index[-1].date()}")
        _print_missing_rates(merged)
    else:
        print("  ⚠️ 无数据返回")

    return merged


def download_tier2(sources: list[str] | None, cache: bool):
    """下载第二档数据."""
    from src.data.external_tier2 import load_all_tier2_data

    print("\n" + "─" * 50)
    print("📥 第二档: Open Interest / Liquidation / Google Trends / CoinGecko")
    print("─" * 50)

    merged = load_all_tier2_data(sources=sources, cache=cache)

    if len(merged) > 0:
        print(f"  ✅ {len(merged)} 行, {len(merged.columns)} 列")
        print(f"  📅 {merged.index[0].date()} ~ {merged.index[-1].date()}")
        _print_missing_rates(merged)
    else:
        print("  ⚠️ 无数据返回")

    return merged


def _print_missing_rates(df):
    """Print per-column missing rates."""
    print("  📋 各列缺失率:")
    for col in df.columns:
        miss = df[col].isnull().mean()
        status = "✅" if miss < 0.1 else "⚠️" if miss < 0.5 else "❌"
        print(f"    {status} {col}: {miss:.1%}")


def main():
    parser = argparse.ArgumentParser(description="下载外部数据 (第一档 + 第二档)")
    parser.add_argument(
        "--sources", nargs="*", default=None,
        help="指定数据源 (属于哪个档由 --tier1/--tier2 决定)",
    )
    parser.add_argument("--tier1", action="store_true",
                        help="下载第一档 (FGI/宏观/FR/LS)")
    parser.add_argument("--tier2", action="store_true",
                        help="下载第二档 (OI/Liquidation/GoogleTrends/CoinGecko)")
    parser.add_argument("--all", action="store_true",
                        help="两档全部下载")
    parser.add_argument("--start", default="2018-01-01", help="起始日期")
    parser.add_argument("--no-cache", action="store_true", help="强制重新下载")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    setup_logging(level=args.log_level)
    cache = not args.no_cache

    # 默认行为: 不指定 tier 时下载第一档 (向后兼容)
    if not args.tier1 and not args.tier2 and not args.all:
        args.tier1 = True

    if args.all:
        args.tier1 = True
        args.tier2 = True

    print("=" * 60)
    print("📥 FcstLabPro 外部数据下载")
    print("=" * 60)

    if args.tier1:
        download_tier1(args.sources, args.start, cache)

    if args.tier2:
        download_tier2(args.sources, cache)

    print("\n" + "=" * 60)
    print("✅ 完成! 数据保存在: data/external/")
    print("=" * 60)


if __name__ == "__main__":
    main()
