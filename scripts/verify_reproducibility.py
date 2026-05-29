#!/usr/bin/env python3
"""复现性验证 — 重跑 E1/E8 并与黄金基线逐位对账.

这是 Phase 0 的核心守门员: 任何重构 / 代码修改后, 跑这个脚本确认
生产模型数值未漂移 (bit-exact)。

背景 (2026-05-29 发现的三重漂移根因):
  1. 依赖未锁版本 — Py3.10→3.9, LightGBM→4.6 导致 Kappa 漂移
  2. 数据文件被更新 — data/raw 的 CSV 含了基线之后的未来数据
  3. loader 曾忽略 config 的 data.start/end — 已修复, 现在基线按 end=2025-12-31 截断

解决方案 (本脚本强制执行):
  * 用 requirements.lock.txt 锁定的环境 (Py3.10 + LightGBM 4.3.0)
  * 用 baseline_snapshot/ 里冻结的基线数据 + config 的 data.start/end 边界
  * 与 baseline_snapshot/{model}/metrics.json 逐 key 对账

Usage:
    .venv/bin/python scripts/verify_reproducibility.py
    .venv/bin/python scripts/verify_reproducibility.py --model e1-conservative
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASELINE_DIR = PROJECT_ROOT / "baseline_snapshot"
BASELINE_CSV = BASELINE_DIR / "btc_baseline_693b7b1.csv"

# 数值容差: bit-exact 要求 0, 但保留极小 epsilon 防御平台级浮点表示差异
TOLERANCE = 1e-12

MODELS = {
    "e1-conservative": "models/production/e1-conservative/config.yaml",
    "e8-touch": "models/production/e8-touch/config.yaml",
}


def _run_experiment(model_name: str, config_path: str, tmp_data: Path) -> dict:
    """用基线数据重跑实验, 返回 metrics dict."""
    exp_name = f"_repro_{model_name.replace('-', '_')}"
    cmd = [
        str(PROJECT_ROOT / ".venv/bin/python"),
        str(PROJECT_ROOT / "scripts/run_experiment.py"),
        "--config", config_path,
        "--override",
        f"data.path={tmp_data.relative_to(PROJECT_ROOT)}",
        f"experiment.name={exp_name}",
        "--overwrite",
    ]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        raise RuntimeError(f"实验运行失败: {model_name}")

    metrics_path = PROJECT_ROOT / "experiments" / "weekly" / exp_name / "metrics.json"
    metrics = json.loads(metrics_path.read_text())

    # 清理临时产物
    shutil.rmtree(metrics_path.parent, ignore_errors=True)
    return metrics


def _compare(model_name: str, fresh: dict, golden: dict) -> bool:
    """逐 key 对账, 返回是否 bit-exact."""
    print(f"\n{'='*60}")
    print(f"  📊 {model_name}")
    print(f"{'='*60}")
    ok = True
    for key in sorted(golden):
        g = golden[key]
        f = fresh.get(key)
        if f is None:
            print(f"  ❌ {key}: 重跑结果缺失")
            ok = False
            continue
        diff = abs(f - g)
        mark = "✅" if diff <= TOLERANCE else "❌"
        if diff > TOLERANCE:
            ok = False
        print(f"  {mark} {key}: golden={g:.16f} fresh={f:.16f} diff={diff:.2e}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="复现性验证 — E1/E8 bit-exact 对账")
    parser.add_argument("--model", choices=list(MODELS), default=None,
                        help="只验证指定模型 (默认全部)")
    args = parser.parse_args()

    if not BASELINE_CSV.exists():
        print(f"❌ 基线数据不存在: {BASELINE_CSV}")
        print("   请确认 baseline_snapshot/ 已提交到 git。")
        return 2

    # 把基线数据复制进项目 (loader 需要项目内相对路径)
    tmp_data = PROJECT_ROOT / "data" / "raw" / "_repro_baseline.csv"
    shutil.copy2(BASELINE_CSV, tmp_data)

    targets = [args.model] if args.model else list(MODELS)
    all_ok = True
    try:
        for model_name in targets:
            golden = json.loads(
                (BASELINE_DIR / model_name / "metrics.json").read_text()
            )
            fresh = _run_experiment(model_name, MODELS[model_name], tmp_data)
            if not _compare(model_name, fresh, golden):
                all_ok = False
    finally:
        tmp_data.unlink(missing_ok=True)
        # 还原 registry (run_experiment 会写它)
        subprocess.run(
            ["git", "checkout", "experiments/registry.json"],
            cwd=str(PROJECT_ROOT), capture_output=True,
        )

    print(f"\n{'='*60}")
    if all_ok:
        print("  🎉 复现性验证通过 — 所有模型 bit-exact!")
        print(f"{'='*60}")
        return 0
    print("  🚨 复现性验证失败 — 数值漂移! 不要部署/晋升!")
    print("     检查: 依赖版本 (requirements.lock.txt) / 数据 / 代码逻辑")
    print(f"{'='*60}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
