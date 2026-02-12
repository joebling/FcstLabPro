#!/usr/bin/env python3
"""运行单次实验.

Usage:
    python scripts/run_experiment.py --config configs/experiments/exp_001_baseline.yaml
    python scripts/run_experiment.py --config configs/experiments/exp_001_baseline.yaml --override label.T=21
"""

import argparse
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logging import setup_logging
from src.experiment.runner import run_experiment


def main():
    parser = argparse.ArgumentParser(description="运行 FcstLabPro 实验")
    parser.add_argument("--config", required=True, help="实验配置 YAML 文件路径")
    parser.add_argument("--override", nargs="*", default=[], help="参数覆盖, 如 label.T=21 label.X=0.10")
    parser.add_argument("--log-level", default="INFO", help="日志级别")
    args = parser.parse_args()

    setup_logging(level=args.log_level)

    experiment_id = run_experiment(
        config_path=args.config,
        overrides=args.override if args.override else None,
    )

    print(f"\n✅ 实验完成: {experiment_id}")
    print(f"📁 产物目录: experiments/{experiment_id}/")
    print(f"📋 实验报告: experiments/{experiment_id}/report.md")


if __name__ == "__main__":
    main()
