#!/usr/bin/env python3
"""参数搜索 — 批量跑不同 T/X 组合.

Usage:
    python scripts/param_search.py \
        --config configs/experiments/exp_001_baseline.yaml \
        --T_list 7 14 21 \
        --X_list 0.06 0.08 0.10 0.12
"""

import argparse
import itertools
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logging import setup_logging
from src.experiment.runner import run_experiment


def main():
    parser = argparse.ArgumentParser(description="FcstLabPro 参数搜索")
    parser.add_argument("--config", required=True, help="基础实验配置")
    parser.add_argument("--T_list", nargs="+", type=int, default=[14], help="T 值列表")
    parser.add_argument("--X_list", nargs="+", type=float, default=[0.08], help="X 值列表")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    setup_logging(level=args.log_level)

    combos = list(itertools.product(args.T_list, args.X_list))
    print(f"\n🔍 参数搜索: {len(combos)} 个组合")
    print(f"   T: {args.T_list}")
    print(f"   X: {args.X_list}")
    print()

    results = []
    for i, (T, X) in enumerate(combos, 1):
        print(f"--- [{i}/{len(combos)}] T={T}, X={X} ---")
        try:
            exp_id = run_experiment(
                config_path=args.config,
                overrides=[f"label.T={T}", f"label.X={X}",
                           f"experiment.name=search_T{T}_X{int(X*100)}"],
            )
            results.append({"T": T, "X": X, "experiment_id": exp_id, "status": "ok"})
        except Exception as e:
            print(f"   ❌ 失败: {e}")
            results.append({"T": T, "X": X, "experiment_id": None, "status": str(e)})

    print(f"\n{'='*60}")
    print(f"参数搜索完成: {sum(1 for r in results if r['status']=='ok')}/{len(results)} 成功")
    for r in results:
        status = "✅" if r["status"] == "ok" else "❌"
        print(f"  {status} T={r['T']}, X={r['X']} -> {r['experiment_id'] or r['status']}")


if __name__ == "__main__":
    main()
