#!/usr/bin/env python3
"""对比多个实验.

Usage:
    # 按实验 ID（目录名）对比
    python scripts/compare_experiments.py --ids exp_001_xxx exp_002_yyy

    # 按标签对比
    python scripts/compare_experiments.py --tags baseline v1

    # 列出所有实验
    python scripts/compare_experiments.py --list
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logging import setup_logging
from src.experiment.tracker import (
    list_experiments, filter_experiments, get_experiment_dir,
    EXPERIMENTS_DIR,
)
from src.evaluation.comparison import compare_experiments


def _resolve_exp_dirs(experiment_ids: list[str]) -> list[Path]:
    """通过 tracker 的递归查找解析实验目录（支持多级目录）."""
    dirs = []
    for eid in experiment_ids:
        d = get_experiment_dir(eid)
        if d and d.exists():
            dirs.append(d)
        else:
            # 支持部分 ID 匹配
            registry = list_experiments()
            matches = [e for e in registry if eid in e["experiment_id"]]
            if len(matches) == 1:
                d = get_experiment_dir(matches[0]["experiment_id"])
                if d and d.exists():
                    dirs.append(d)
                    continue
            print(f"⚠️ 实验目录不存在或匹配不唯一: {eid}")
    return dirs


def main():
    parser = argparse.ArgumentParser(description="对比 FcstLabPro 实验")
    parser.add_argument("--ids", nargs="*", help="要对比的实验 ID 列表（支持部分匹配）")
    parser.add_argument("--tags", nargs="*", help="按标签筛选实验进行对比")
    parser.add_argument("--category", help="按大类筛选实验进行对比")
    parser.add_argument("--status", default="completed", help="按状态筛选 (默认: completed)")
    parser.add_argument("--all", action="store_true", help="对比所有已完成实验")
    parser.add_argument("--list", action="store_true", help="列出所有实验")
    parser.add_argument("--output", default="reports/", help="报告输出目录")
    parser.add_argument("--log-level", default="INFO", help="日志级别")
    args = parser.parse_args()

    setup_logging(level=args.log_level)

    # 列出所有实验
    if args.list:
        experiments = list_experiments()
        if not experiments:
            print("暂无实验记录")
            return
        print(f"\n{'='*80}")
        print(f"{'实验ID':<50} {'状态':<10} {'时间':<20}")
        print(f"{'='*80}")
        for exp in experiments:
            print(f"{exp['experiment_id']:<50} {exp.get('status', 'N/A'):<10} {exp.get('created_at', 'N/A'):<20}")
        print(f"{'='*80}")
        print(f"共 {len(experiments)} 个实验")
        return

    # 确定要对比的实验
    exp_dirs = []
    if args.ids:
        exp_dirs = _resolve_exp_dirs(args.ids)
    elif args.tags:
        experiments = filter_experiments(status=args.status, tags=args.tags)
        for exp in experiments:
            d = get_experiment_dir(exp["experiment_id"])
            if d and d.exists():
                exp_dirs.append(d)
        print(f"按标签 {args.tags} 筛选到 {len(exp_dirs)} 个实验")
    elif args.category:
        experiments = filter_experiments(status=args.status, category=args.category)
        for exp in experiments:
            d = get_experiment_dir(exp["experiment_id"])
            if d and d.exists():
                exp_dirs.append(d)
        print(f"按大类 '{args.category}' 筛选到 {len(exp_dirs)} 个实验")
    elif getattr(args, 'all', False):
        experiments = filter_experiments(status=args.status)
        for exp in experiments:
            d = get_experiment_dir(exp["experiment_id"])
            if d and d.exists():
                exp_dirs.append(d)
        print(f"共找到 {len(exp_dirs)} 个 {args.status} 实验")

    if len(exp_dirs) < 2:
        print("需要至少 2 个实验才能对比，请用 --ids / --tags / --category / --all 指定")
        return

    # 生成对比报告
    ids_str = "_vs_".join([d.name[:20] for d in exp_dirs[:4]])
    if len(exp_dirs) > 4:
        ids_str += f"_and_{len(exp_dirs)-4}_more"
    output_path = Path(args.output) / f"compare_{ids_str}.md"

    report = compare_experiments(exp_dirs, output_path=output_path)
    print(f"\n✅ 对比报告已生成: {output_path}")
    print(report)


if __name__ == "__main__":
    main()
