#!/usr/bin/env python3
"""为既有生产模型回填 feature_cols.json (一次性 bootstrap).

背景：早期 promote 的模型没有 feature_cols.json，这意味着
推理时无法做列序校验 (见 docs/specs/data_pipeline.md §10)。
此脚本按当前 config.yaml 复现 build_features() 的输出列序，
生成并写入 feature_cols.json。

⚠️ 前提：使用的 src/features/* 代码必须与训练这些模型时一致。
   如果中间有人改过 feature builder, 那些模型本来就该重新 promote。

Usage:
    python scripts/bootstrap_feature_cols.py
    python scripts/bootstrap_feature_cols.py --model-dir models/production/e1-conservative
    python scripts/bootstrap_feature_cols.py --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns


def bootstrap_one(model_dir: Path, dry_run: bool = False) -> bool:
    """为单个生产模型目录生成 feature_cols.json."""
    config_path = model_dir / "config.yaml"
    if not config_path.exists():
        print(f"  ❌ 跳过 {model_dir.name}: 缺 config.yaml")
        return False

    target = model_dir / "feature_cols.json"
    if target.exists():
        print(f"  ℹ️  {model_dir.name}: feature_cols.json 已存在，跳过 (删掉重跑可强制刷新)")
        return True

    config = yaml.safe_load(config_path.read_text())
    data_path = config["data"]["path"]
    data_full = PROJECT_ROOT / data_path

    if not data_full.exists():
        print(f"  ❌ 跳过 {model_dir.name}: 数据文件不存在 {data_full}")
        return False

    # 复现 runner.py 的 build_features 调用
    df = load_csv(str(data_full))
    feat_cfg = config["features"]
    df = build_features(
        df,
        feature_sets=feat_cfg["sets"],
        drop_na_method=feat_cfg.get("drop_na_method", "ffill_then_drop"),
        drop_features=feat_cfg.get("drop_features"),
        smoothing=feat_cfg.get("smoothing"),
    )
    feature_cols = get_feature_columns(df)

    payload = ",".join(feature_cols)
    doc = {
        "version": 1,
        "n_features": len(feature_cols),
        "feature_cols": list(feature_cols),
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "generated_by": "scripts.bootstrap_feature_cols",
        "note": "重建自当前 src/features/* 代码 + config.yaml，非原训练快照",
    }

    print(f"  ✅ {model_dir.name}: {len(feature_cols)} 列, sha256={doc['sha256'][:12]}...")

    # 跟 manifest 里的特征数交叉验证 (如果有)
    manifest_path = model_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        claimed = manifest.get("features", {}).get("count", "")
        # 字符串里的数字: "129 (after decontamination)" → 129
        import re
        m = re.search(r"\d+", str(claimed))
        if m and int(m.group()) != len(feature_cols):
            print(f"  ⚠️  manifest.features.count = {claimed!r} "
                  f"但本次计算 {len(feature_cols)} 列 — 可能 features 代码已漂移!")

    if dry_run:
        print(f"  💨 干跑模式，未写入 {target}")
        return True

    target.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    print(f"  💾 已写入 {target.relative_to(PROJECT_ROOT)}")
    return True


def main():
    parser = argparse.ArgumentParser(description="为既有生产模型回填 feature_cols.json")
    parser.add_argument("--model-dir", default=None,
                        help="指定单个模型目录；不传则遍历 models/production/*")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    args = parser.parse_args()

    print("=" * 60)
    print("  🔧 Bootstrap feature_cols.json")
    print("=" * 60)

    if args.model_dir:
        targets = [Path(args.model_dir)]
    else:
        prod = PROJECT_ROOT / "models" / "production"
        targets = sorted([p for p in prod.iterdir() if p.is_dir()])

    if not targets:
        print("(没有发现任何生产模型目录)")
        return 0

    ok = True
    for d in targets:
        print(f"\n→ {d.relative_to(PROJECT_ROOT)}")
        ok &= bootstrap_one(d, dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print(f"  {'✅ 完成' if ok else '❌ 有失败项'}")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
