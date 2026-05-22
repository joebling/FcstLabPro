#!/usr/bin/env python3
"""实验管理 CLI — 列表 / 筛选 / 清理 / 归档 / 详情 / 最佳.

Usage:
    # 列出所有实验
    python scripts/manage_experiments.py list

    # 只看成功的实验，按 accuracy 降序
    python scripts/manage_experiments.py list --status completed --sort accuracy --desc

    # 按标签筛选
    python scripts/manage_experiments.py list --tags baseline v1

    # 搜索名称包含 "flow" 的实验
    python scripts/manage_experiments.py list --search flow

    # 查看单个实验详情
    python scripts/manage_experiments.py show <experiment_id>

    # 查看指标最优的实验
    python scripts/manage_experiments.py best --metric f1_macro

    # 清理所有失败的实验（删除目录+注册表）
    python scripts/manage_experiments.py cleanup

    # 归档指定日期之前的实验
    python scripts/manage_experiments.py archive --before 2026-02-01

    # 归档指定实验
    python scripts/manage_experiments.py archive --ids exp_id_1 exp_id_2

    # 删除指定实验
    python scripts/manage_experiments.py delete <experiment_id>

    # 导出注册表为 CSV
    python scripts/manage_experiments.py export --output docs/reports/experiments.csv
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logging import setup_logging
from src.experiment.tracker import (
    list_experiments,
    filter_experiments,
    delete_experiment,
    cleanup_failed,
    archive_experiments,
    get_experiment_summary,
    get_experiment_dir,
    get_best_experiment,
    EXPERIMENTS_DIR,
)


# ─── 格式化辅助 ───────────────────────────────────────────

def _status_icon(status: str) -> str:
    return {"completed": "✅", "failed": "❌", "running": "🔄"}.get(status, "❓")


def _duration_str(seconds) -> str:
    if seconds is None:
        return "-"
    if seconds < 60:
        return f"{seconds:.0f}s"
    return f"{seconds / 60:.1f}min"


def _metric_str(val) -> str:
    if val is None:
        return "-"
    if isinstance(val, float):
        return f"{val:.4f}"
    return str(val)


def _print_table(rows: list[dict], columns: list[tuple[str, str, int]]):
    """简易表格打印.

    columns: [(key, header, width), ...]
    """
    # 表头
    header = " | ".join(h.ljust(w) for _, h, w in columns)
    sep = "-+-".join("-" * w for _, _, w in columns)
    print(header)
    print(sep)
    for row in rows:
        line = " | ".join(str(row.get(k, "-"))[:w].ljust(w) for k, _, w in columns)
        print(line)


def _format_experiment_row(entry: dict) -> dict:
    """将注册表条目格式化为可显示的行."""
    metrics = entry.get("aggregate_metrics", {})
    created = entry.get("created_at", "")
    if created:
        try:
            dt = datetime.fromisoformat(created)
            created = dt.strftime("%m-%d %H:%M")
        except Exception:
            created = created[:16]

    return {
        "status": _status_icon(entry.get("status", "")),
        "id": entry.get("experiment_id", "")[-20:],  # 截短显示
        "full_id": entry.get("experiment_id", ""),
        "name": entry.get("name", ""),
        "category": entry.get("category", ""),
        "tags": ",".join(entry.get("tags", [])),
        "created": created,
        "duration": _duration_str(entry.get("duration_seconds")),
        "acc": _metric_str(metrics.get("accuracy")),
        "f1": _metric_str(metrics.get("f1_macro")),
        "kappa": _metric_str(metrics.get("cohen_kappa")),
        "git": entry.get("git_commit", "?"),
        "error": (entry.get("error") or "")[:40],
    }


# ─── 子命令实现 ───────────────────────────────────────────

def cmd_list(args):
    """列出实验."""
    results = filter_experiments(
        status=args.status,
        category=getattr(args, 'category', None),
        tags=args.tags,
        name_contains=args.search,
        sort_by=args.sort,
        ascending=not args.desc,
        top_n=args.top,
    )

    if not results:
        print("📭 没有找到符合条件的实验")
        return

    rows = [_format_experiment_row(e) for e in results]

    print(f"\n📋 共 {len(results)} 个实验\n")

    columns = [
        ("status", "St", 2),
        ("category", "Category", 14),
        ("name", "Name", 18),
        ("created", "Created", 11),
        ("duration", "Time", 7),
        ("acc", "Acc", 6),
        ("f1", "F1", 6),
        ("kappa", "Kappa", 6),
        ("git", "Git", 7),
        ("id", "ID (last 20)", 20),
    ]
    _print_table(rows, columns)

    # 如果有失败的，额外提示
    failed_count = sum(1 for e in results if e.get("status") == "failed")
    if failed_count:
        print(f"\n⚠️  有 {failed_count} 个失败实验，可用 `cleanup` 清理")


def cmd_show(args):
    """查看实验详情."""
    # 支持部分 ID 匹配
    experiment_id = _resolve_experiment_id(args.experiment_id)
    if not experiment_id:
        return

    summary = get_experiment_summary(experiment_id)
    if not summary:
        print(f"❌ 找不到实验: {experiment_id}")
        return

    print(f"\n{'='*60}")
    print(f"  实验详情: {experiment_id}")
    print(f"{'='*60}")
    print(f"  状态:     {_status_icon(summary.get('status', ''))} {summary.get('status', '')}")
    print(f"  名称:     {summary.get('name', '')}")
    print(f"  大类:     {summary.get('category', 'default')}")
    print(f"  描述:     {summary.get('description', '')}")
    print(f"  标签:     {summary.get('tags', [])}")
    print(f"  创建时间: {summary.get('created_at', '')}")
    print(f"  耗时:     {_duration_str(summary.get('duration_seconds'))}")
    print(f"  种子:     {summary.get('seed')}")

    git = summary.get("git", {})
    print(f"  Git:      {git.get('branch', '?')}@{git.get('commit', '?')} {'(dirty)' if git.get('dirty') else '(clean)'}")

    metrics = summary.get("aggregate_metrics", {})
    if metrics:
        print(f"\n  📊 汇总指标:")
        for k, v in metrics.items():
            print(f"     {k:20s}: {_metric_str(v)}")

    if summary.get("error"):
        print(f"\n  ❌ 错误: {summary['error']}")

    # 检查产物
    exp_dir = get_experiment_dir(experiment_id)
    if exp_dir and exp_dir.exists():
        files = sorted(exp_dir.iterdir())
        print(f"\n  📁 产物 ({len(files)} 文件):")
        for f in files:
            size = f.stat().st_size
            size_str = f"{size / 1024:.1f}KB" if size > 1024 else f"{size}B"
            print(f"     {f.name:30s}  {size_str}")

    print(f"{'='*60}\n")


def cmd_best(args):
    """查看最优实验."""
    best = get_best_experiment(
        metric=args.metric,
        higher_is_better=not args.lower,
    )
    if not best:
        print("📭 没有找到成功完成的实验")
        return

    metrics = best.get("aggregate_metrics", {})
    print(f"\n🏆 最优实验 (按 {args.metric}):")
    print(f"   ID:     {best['experiment_id']}")
    print(f"   Name:   {best.get('name', '')}")
    print(f"   {args.metric}: {_metric_str(metrics.get(args.metric))}")
    print(f"   所有指标: {json.dumps(metrics, indent=2)}")
    print()


def cmd_cleanup(args):
    """清理失败的实验."""
    if not args.yes:
        failed = filter_experiments(status="failed")
        if not failed:
            print("✅ 没有失败的实验需要清理")
            return
        print(f"⚠️  将清理以下 {len(failed)} 个失败实验:")
        for e in failed:
            print(f"   - {e['experiment_id']}")
        confirm = input("\n确认删除? (y/N): ").strip().lower()
        if confirm != "y":
            print("已取消")
            return

    deleted = cleanup_failed(delete_files=True)
    if deleted:
        print(f"\n🧹 已清理 {len(deleted)} 个失败实验:")
        for eid in deleted:
            print(f"   ✅ {eid}")
    else:
        print("✅ 没有失败的实验需要清理")


def cmd_archive(args):
    """归档实验."""
    archived = archive_experiments(
        experiment_ids=args.ids,
        before_date=args.before,
        status=args.status,
    )
    if archived:
        print(f"\n📦 已归档 {len(archived)} 个实验:")
        for eid in archived:
            print(f"   📦 {eid}")
        print(f"\n归档目录: experiments_archive/")
    else:
        print("📭 没有符合条件的实验需要归档")


def cmd_delete(args):
    """删除指定实验."""
    experiment_id = _resolve_experiment_id(args.experiment_id)
    if not experiment_id:
        return

    if not args.yes:
        confirm = input(f"⚠️  确认删除实验 '{experiment_id}'? (y/N): ").strip().lower()
        if confirm != "y":
            print("已取消")
            return

    if delete_experiment(experiment_id, delete_files=True):
        print(f"✅ 已删除实验: {experiment_id}")
    else:
        print(f"❌ 删除失败: {experiment_id}")


def cmd_export(args):
    """导出注册表为 CSV."""
    registry = list_experiments()
    if not registry:
        print("📭 注册表为空")
        return

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    # 收集所有可能的指标名
    all_metric_keys = set()
    for e in registry:
        all_metric_keys.update(e.get("aggregate_metrics", {}).keys())
    all_metric_keys = sorted(all_metric_keys)

    fieldnames = [
        "experiment_id", "name", "status", "created_at",
        "duration_seconds", "git_commit", "git_branch", "seed", "tags",
    ] + all_metric_keys + ["error"]

    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for entry in registry:
            row = {**entry}
            row["tags"] = ",".join(entry.get("tags", []))
            # 展平 metrics
            for mk in all_metric_keys:
                row[mk] = entry.get("aggregate_metrics", {}).get(mk)
            writer.writerow(row)

    print(f"✅ 已导出 {len(registry)} 条记录到 {output}")


# ─── 辅助 ─────────────────────────────────────────────────

def _resolve_experiment_id(partial_id: str) -> str | None:
    """支持部分 ID 匹配（从注册表中查找唯一匹配）."""
    registry = list_experiments()
    matches = [e for e in registry if partial_id in e["experiment_id"]]

    if len(matches) == 0:
        print(f"❌ 找不到匹配 '{partial_id}' 的实验")
        return None
    elif len(matches) == 1:
        return matches[0]["experiment_id"]
    else:
        print(f"⚠️  '{partial_id}' 匹配了多个实验，请更精确:")
        for m in matches:
            print(f"   - {m['experiment_id']}")
        return None


# ─── CLI 入口 ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="FcstLabPro 实验管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # list
    p_list = subparsers.add_parser("list", aliases=["ls"], help="列出实验")
    p_list.add_argument("--status", choices=["completed", "failed", "running"], help="按状态筛选")
    p_list.add_argument("--category", help="按大类筛选 (baseline/feature_study/param_tuning/model_compare/production)")
    p_list.add_argument("--tags", nargs="+", help="按标签筛选（必须包含所有指定标签）")
    p_list.add_argument("--search", help="搜索名称/ID")
    p_list.add_argument("--sort", help="排序字段 (created_at/duration_seconds/accuracy/f1_macro/...)")
    p_list.add_argument("--desc", action="store_true", help="降序排列")
    p_list.add_argument("--top", type=int, help="只显示前 N 个")

    # show
    p_show = subparsers.add_parser("show", help="查看实验详情")
    p_show.add_argument("experiment_id", help="实验 ID（支持部分匹配）")

    # best
    p_best = subparsers.add_parser("best", help="查看最优实验")
    p_best.add_argument("--metric", default="accuracy", help="评比指标 (默认: accuracy)")
    p_best.add_argument("--lower", action="store_true", help="越低越好（如 loss）")

    # cleanup
    p_cleanup = subparsers.add_parser("cleanup", help="清理所有失败的实验")
    p_cleanup.add_argument("-y", "--yes", action="store_true", help="跳过确认")

    # archive
    p_archive = subparsers.add_parser("archive", help="归档实验")
    p_archive.add_argument("--ids", nargs="+", help="指定实验 ID")
    p_archive.add_argument("--before", help="归档此日期之前的实验 (ISO 格式)")
    p_archive.add_argument("--status", help="归档指定状态的实验")

    # delete
    p_delete = subparsers.add_parser("delete", aliases=["rm"], help="删除实验")
    p_delete.add_argument("experiment_id", help="实验 ID（支持部分匹配）")
    p_delete.add_argument("-y", "--yes", action="store_true", help="跳过确认")

    # export
    p_export = subparsers.add_parser("export", help="导出注册表为 CSV")
    p_export.add_argument("--output", default="docs/reports/experiments_registry.csv", help="输出文件路径")

    args = parser.parse_args()

    setup_logging(level="INFO")

    if args.command in ("list", "ls"):
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "best":
        cmd_best(args)
    elif args.command == "cleanup":
        cmd_cleanup(args)
    elif args.command == "archive":
        cmd_archive(args)
    elif args.command in ("delete", "rm"):
        cmd_delete(args)
    elif args.command == "export":
        cmd_export(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
