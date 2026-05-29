#!/usr/bin/env python3
"""模型晋升脚本: 实验 → 生产.

按 CLAUDE.md 的部署前自检流程：
  1. 验证实验完成状态
  2. 检查指标门槛 (Kappa, PF, MaxDD)
  3. 复制模型 + 配置 + 元数据 → models/production/
  4. 生成 manifest.json (模型谱系)
  5. 上传到 GCS (可选)

Usage:
    # 晋升 E1 模型
    python scripts/promote_model.py \
        --experiment experiments/weekly/weekly_bear_v0305_E1_decontam \
        --name e1-conservative \
        --variant conservative

    # 干跑 (只检查，不复制)
    python scripts/promote_model.py \
        --experiment experiments/weekly/weekly_bear_v0305_E1_decontam \
        --dry-run

    # 晋升并上传 GCS
    python scripts/promote_model.py \
        --experiment experiments/weekly/weekly_bear_v0305_E1_decontam \
        --name e1-conservative \
        --gcs gs://forecastlab-prod-models/v0305-e1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_DIR = PROJECT_ROOT / "models" / "production"
sys.path.insert(0, str(PROJECT_ROOT))

from src.serving.contracts import (  # noqa: E402
    build_data_manifest,
    build_execution_policy,
    build_lifecycle,
    build_validation_gates,
)

# =====================================================================
# CLAUDE.md 部署前自检 (Section 5.1)
# =====================================================================

MIN_KAPPA = 0.10          # IC/Kappa 最低门槛
MIN_PROFIT_FACTOR = 1.10  # 盈亏比最低门槛
MAX_DRAWDOWN_LIMIT = -0.30  # MaxDD 不能超过 30%


def check_experiment_status(exp_dir: Path) -> list[str]:
    """检查实验是否完成，返回错误列表."""
    errors = []

    # 必要文件
    required = ["model.joblib", "config.yaml", "meta.json", "metrics.json"]
    for f in required:
        if not (exp_dir / f).exists():
            errors.append(f"❌ 缺少必要文件: {f}")

    # meta.json 状态
    meta_path = exp_dir / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        if meta.get("status") != "completed":
            errors.append(f"❌ 实验未完成: status={meta.get('status')}")
    return errors


def check_metrics_thresholds(exp_dir: Path, target_variant: str = "conservative") -> tuple[list[str], list[str]]:
    """检查指标门槛，返回 (errors, warnings). 只对目标变体严格检查."""
    errors, warnings = [], []

    # 分类指标
    metrics_path = exp_dir / "metrics.json"
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text())
        kappa = metrics.get("cohen_kappa", 0)
        if kappa < MIN_KAPPA:
            errors.append(f"❌ Kappa={kappa:.3f} < {MIN_KAPPA} (门槛)")
        if kappa > 0.50:
            warnings.append(f"⚠️ Kappa={kappa:.3f} > 0.50，可能存在数据泄露 (CLAUDE.md 3.3)")

    # PnL 指标
    pnl_path = exp_dir / "pnl_metrics.json"
    if pnl_path.exists():
        pnl = json.loads(pnl_path.read_text())

        # 目标变体名映射
        target_variant_map = {
            "base": "策略(无开关)",
            "moderate": "策略(+止盈)",
            "conservative": "策略(止盈+regime)",
        }
        target_key = target_variant_map.get(target_variant, "")

        for variant_name, variant_metrics in pnl.items():
            if variant_name == "买入持有":
                continue
            pf = variant_metrics.get("profit_factor", 0)
            mdd = variant_metrics.get("max_drawdown", 0)

            is_target = (variant_name == target_key)

            if pf < MIN_PROFIT_FACTOR:
                msg = f"{variant_name}: PF={pf:.2f} < {MIN_PROFIT_FACTOR}"
                if is_target:
                    errors.append(f"❌ {msg} (目标变体)")
                else:
                    warnings.append(f"⚠️ {msg}")
            if mdd < MAX_DRAWDOWN_LIMIT:
                msg = f"{variant_name}: MaxDD={mdd:.1%} < {MAX_DRAWDOWN_LIMIT:.0%}"
                if is_target:
                    errors.append(f"❌ {msg} (目标变体)")
                else:
                    warnings.append(f"⚠️ {msg}")
    else:
        warnings.append("⚠️ 无 pnl_metrics.json，无法验证 PnL 门槛")

    return errors, warnings


def compute_model_hash(model_path: Path) -> str:
    """SHA256 of model file for integrity verification."""
    h = hashlib.sha256()
    with open(model_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def get_git_info() -> dict:
    """Get current git state."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(PROJECT_ROOT), text=True,
        ).strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(PROJECT_ROOT), text=True,
        ).strip()
        dirty = bool(subprocess.call(
            ["git", "diff", "--quiet"],
            cwd=str(PROJECT_ROOT),
        ))
        return {"commit": commit, "branch": branch, "dirty": dirty}
    except Exception:
        return {"commit": "unknown", "branch": "unknown", "dirty": True}


# =====================================================================
# Promotion
# =====================================================================

def promote(
    exp_dir: Path,
    name: str,
    variant: str = "conservative",
    role: str = "risk_control",
    status: str = "paper",
    gcs_path: str | None = None,
    dry_run: bool = False,
) -> bool:
    """Promote experiment model to production."""
    print("=" * 60)
    print(f"  🚀 模型晋升: {exp_dir.name} → models/production/{name}")
    print("=" * 60)

    # --- Phase 1: 自检 (CLAUDE.md 5.1) ---
    print("\n🔍 Phase 1: 部署前自检 (CLAUDE.md 5.1)")

    status_errors = check_experiment_status(exp_dir)
    metric_errors, metric_warnings = check_metrics_thresholds(exp_dir, target_variant=variant)

    all_errors = status_errors + metric_errors
    all_warnings = metric_warnings

    # 输出检查结果
    for e in all_errors:
        print(f"  {e}")
    for w in all_warnings:
        print(f"  {w}")

    if all_errors:
        print(f"\n❌ 自检失败: {len(all_errors)} 个错误，无法晋升")
        return False

    # 输出关键指标
    metrics = json.loads((exp_dir / "metrics.json").read_text())
    print(f"  ✅ Kappa: {metrics.get('cohen_kappa', 0):.3f}")
    print(f"  ✅ Precision: {metrics.get('precision_binary', 0):.3f}")
    print(f"  ✅ Recall: {metrics.get('recall_binary', 0):.3f}")

    if (exp_dir / "pnl_metrics.json").exists():
        pnl = json.loads((exp_dir / "pnl_metrics.json").read_text())
        for vname, vm in pnl.items():
            if vname == "买入持有":
                continue
            print(f"  ✅ {vname}: PF={vm.get('profit_factor',0):.2f}, "
                  f"MaxDD={vm.get('max_drawdown',0):.1%}, "
                  f"CAGR={vm.get('cagr',0):.1%}")

    print(f"\n  ✅ 自检通过 ({len(all_warnings)} 个警告)")

    if dry_run:
        print("\n💨 干跑模式，不执行复制")
        return True

    # --- Phase 2: 复制到生产目录 ---
    print(f"\n📦 Phase 2: 复制到 models/production/{name}/")
    target_dir = PRODUCTION_DIR / name
    target_dir.mkdir(parents=True, exist_ok=True)

    # 复制核心文件
    files_to_copy = ["model.joblib", "config.yaml", "meta.json",
                     "metrics.json", "pnl_metrics.json",
                     # 特征列名快照与重要性 (推理时需要)
                     "feature_cols.json", "feature_importance.csv"]
    for f in files_to_copy:
        src = exp_dir / f
        if src.exists():
            shutil.copy2(src, target_dir / f)
            print(f"  ✅ {f}")
        elif f == "feature_cols.json":
            # 老实验 (在 runner.py 加此产物之前跑的) 可能没有, 响亮警告
            print(f"  ⚠️  {f} 不存于实验目录 — 推理时列序校验将被跳过 (P0 隐患)")

    # --- Phase 3: 生成 manifest ---
    print("\n📝 Phase 3: 生成 manifest.json")

    meta = json.loads((exp_dir / "meta.json").read_text())
    config = __import__("yaml").safe_load((exp_dir / "config.yaml").read_text())
    model_hash = compute_model_hash(exp_dir / "model.joblib")
    has_pnl = (exp_dir / "pnl_metrics.json").exists()
    decontaminated = bool(config.get("features", {}).get("drop_features"))

    # 特征数量从 feature_cols.json 动态读取 (不再硬编码 129)
    feature_count = None
    feature_cols_sha256 = None
    if (target_dir / "feature_cols.json").exists():
        fc = json.loads((target_dir / "feature_cols.json").read_text())
        feature_count = fc.get("n_features")
        feature_cols_sha256 = fc.get("sha256")

    manifest = {
        "name": name,
        "promoted_at": datetime.utcnow().isoformat() + "Z",
        "lifecycle": build_lifecycle(status=status, role=role),
        "source_experiment": {
            "id": meta.get("experiment_id"),
            "path": str(exp_dir.relative_to(PROJECT_ROOT)),
            "created_at": meta.get("created_at"),
            "git_commit": meta.get("git", {}).get("commit"),
        },
        "model": {
            "type": config.get("model", {}).get("type"),
            "sha256_prefix": model_hash,
            "size_bytes": (exp_dir / "model.joblib").stat().st_size,
        },
        "strategy": {
            "label": config.get("label", {}).get("strategy"),
            "variant": variant,
            "T": config.get("label", {}).get("T"),
            "X": config.get("label", {}).get("X"),
        },
        "features": {
            "sets": config.get("features", {}).get("sets"),
            "drop_features": config.get("features", {}).get("drop_features"),
            "count": feature_count,
            "feature_cols_sha256": feature_cols_sha256,
        },
        "metrics": {
            "classification": metrics,
            "pnl": json.loads((exp_dir / "pnl_metrics.json").read_text())
                   if has_pnl else None,
        },
        "deployment": {
            "variant": variant,
            "cli_flags": " ".join(
                build_execution_policy(variant)["execution"]["cli_flags"]
            ),
            "memory": "2Gi",
            "cpu": "2",
        },
        "fallback": {
            "model_name": "e1-conservative",
            "trigger": "feature_schema_mismatch or data_stale",
        },
        "promotion_git": get_git_info(),
        "validation_gates": build_validation_gates(metrics, has_pnl, decontaminated),
    }

    manifest_path = target_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print("  ✅ manifest.json (含 lifecycle / validation_gates / fallback)")

    # --- Phase 3b: 生成 data_manifest.json + execution_policy.yaml ---
    print("\n📝 Phase 3b: 生成数据谱系 + 执行层合同")
    data_path = PROJECT_ROOT / config.get("data", {}).get("path", "")
    if data_path.exists():
        data_manifest = build_data_manifest(data_path)
        (target_dir / "data_manifest.json").write_text(
            json.dumps(data_manifest, indent=2, ensure_ascii=False)
        )
        print(f"  ✅ data_manifest.json (rows={data_manifest['raw_ohlcv']['rows']}, "
              f"{data_manifest['raw_ohlcv']['start']}~{data_manifest['raw_ohlcv']['end']})")
    else:
        print(f"  ⚠️  data.path 不存在, 跳过 data_manifest: {data_path}")

    exec_policy = build_execution_policy(variant)
    import yaml as _yaml
    (target_dir / "execution_policy.yaml").write_text(
        _yaml.dump(exec_policy, default_flow_style=False, allow_unicode=True, sort_keys=False)
    )
    print("  ✅ execution_policy.yaml (成本/滑点/延迟/kill-switch — verified=false 待确认)")

    # --- Phase 4: GCS 上传 (可选) ---
    if gcs_path:
        print(f"\n☁️ Phase 4: 上传到 GCS: {gcs_path}")
        try:
            subprocess.run(
                ["gsutil", "-m", "cp", "-r", f"{target_dir}/*", f"{gcs_path}/"],
                check=True, capture_output=True, text=True,
            )
            print(f"  ✅ 已上传到 {gcs_path}/")
        except Exception as e:
            print(f"  ⚠️ GCS 上传失败: {e}")

    # 完成
    print("\n" + "=" * 60)
    print(f"  ✅ 模型已晋升到: models/production/{name}/")
    print(f"  ✅ 模型哈希: {model_hash}")
    print("=" * 60)
    print(f"\n下一步:")
    print(f"  1. git add models/production/{name}/")
    print(f"  2. git commit -m \"promote: {name} from {meta.get('experiment_id')}\"")
    print(f"  3. ./deploy/deploy_v0305.sh")
    return True


def main():
    parser = argparse.ArgumentParser(description="模型晋升: 实验 → 生产")
    parser.add_argument("--experiment", required=True, help="实验目录路径")
    parser.add_argument("--name", default="e1-conservative", help="生产模型名称")
    parser.add_argument("--variant", default="conservative",
                        choices=["base", "moderate", "conservative"],
                        help="策略变体")
    parser.add_argument("--role", default="risk_control",
                        choices=["risk_control", "return_enhancement", "sota_candidate"],
                        help="模型角色 (写入 manifest.lifecycle)")
    parser.add_argument("--status", default="paper",
                        choices=["live", "paper", "offline_only"],
                        help="生命周期状态 (默认 paper, 需手动改 active.yaml 才 live)")
    parser.add_argument("--gcs", default=None, help="GCS 上传路径")
    parser.add_argument("--dry-run", action="store_true", help="只检查不复制")
    args = parser.parse_args()

    exp_dir = Path(args.experiment)
    if not exp_dir.is_absolute():
        exp_dir = PROJECT_ROOT / exp_dir

    if not exp_dir.exists():
        print(f"❌ 实验目录不存在: {exp_dir}")
        sys.exit(1)

    success = promote(
        exp_dir=exp_dir,
        name=args.name,
        variant=args.variant,
        role=args.role,
        status=args.status,
        gcs_path=args.gcs,
        dry_run=args.dry_run,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
