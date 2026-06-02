#!/usr/bin/env python3
"""下载数据.

Usage:
    python scripts/download_data.py --symbol BTCUSDT --interval 1d --start 2018-01-01
    python scripts/download_data.py --source yahoo --symbol BTC-USD --start 2018-01-01
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logging import setup_logging
from src.data.downloader import download_binance_klines, download_yahoo


def main():
    parser = argparse.ArgumentParser(description="下载金融数据")
    parser.add_argument("--source", default="binance", choices=["binance", "yahoo"])
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--output", default=None, help="输出路径, 默认自动生成 (data/live/)")
    parser.add_argument(
        "--rebuild-baseline", action="store_true",
        help="重建 data/raw/ 训练基准 (会覆盖 sha 锁定文件, 慎用!). "
             "不加此 flag 时下载一律写 data/live/ (lesson_0602).",
    )
    args = parser.parse_args()

    setup_logging()

    # 默认写 data/live/ (可变区); --rebuild-baseline 才写 data/raw/ (不可变基准)
    target_dir = "data/raw" if args.rebuild_baseline else "data/live"
    if args.output is None:
        safe_symbol = args.symbol.replace("-", "")
        args.output = f"{target_dir}/btc_{args.source}_{safe_symbol}_{args.interval}.csv"

    output_path = Path(args.output)

    if args.source == "binance":
        df = download_binance_klines(
            symbol=args.symbol,
            interval=args.interval,
            start=args.start,
            end=args.end,
            output_path=output_path,
            allow_overwrite_raw=args.rebuild_baseline,
        )
    else:
        df = download_yahoo(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            output_path=output_path,
        )

    print(f"\n✅ 数据下载完成")
    print(f"📁 文件: {output_path}")
    print(f"📊 行数: {len(df)}")
    print(f"📅 范围: {df.index[0]} ~ {df.index[-1]}")


if __name__ == "__main__":
    main()
