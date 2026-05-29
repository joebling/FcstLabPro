#!/usr/bin/env python3
"""生成 performance 产物 (batches.json + summary.json).

对 active.yaml 里的每个模型, 回填实现结果并写 JSON, 供 dashboard 读取。
可手动跑, 也可由信号 pipeline 每日顺带调用 (performance_tracking.md P-5)。

Usage:
    python scripts/build_performance.py                # 所有 active 模型
    python scripts/build_performance.py --model e1-conservative
    python scripts/build_performance.py --out-dir /opt/fcstlabpro/performance
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.performance.aggregate import write_performance
from src.performance.backfill import load_ohlcv
from src.serving.active_config import load_active_models


def _label_T(config_path: Path) -> int:
    cfg = yaml.safe_load(config_path.read_text()) or {}
    return int(cfg["label"]["T"])


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 performance JSON 产物")
    ap.add_argument("--model", default=None, help="只跑指定模型 (默认所有 active)")
    ap.add_argument("--out-dir", default=None, help="输出根目录 (默认 data/live/performance)")
    args = ap.parse_args()

    models = load_active_models()
    targets = (
        [m for m in models.values() if m.name == args.model]
        if args.model else list(models.values())
    )
    if not targets:
        print(f"❌ 找不到模型: {args.model}")
        return 1

    ohlcv = load_ohlcv()
    out_dir = Path(args.out_dir) if args.out_dir else None

    print("=" * 56)
    print("  📊 生成 performance 产物")
    print("=" * 56)
    for m in targets:
        T = _label_T(m.config_path)
        paths = write_performance(m.name, label_T=T, ohlcv=ohlcv, out_dir=out_dir)
        # 简报
        import json
        summ = json.loads(paths["summary"].read_text())
        print(f"\n→ {m.name} (T={T})")
        print(f"  总 {summ['n_total']} 条 | 成熟 {summ['n_mature']} | 待定 {summ['n_pending']}")
        if summ["n_mature"]:
            print(f"  命中率 {summ['hit_rate']}% | 平均实现收益 {summ['avg_realized_return']}%"
                  f" | Rank IC {summ['rank_ic']}")
        print(f"  ✅ {paths['batches'].relative_to(paths['batches'].parents[2])}")

    print("\n" + "=" * 56)
    print("  ✅ 完成")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    sys.exit(main())
