"""v8 系列实验对比脚本.

对比 v7c (基线) vs v8a (回归+阈值) vs v8b (Stacking) vs v8c (分类+阈值优化)。
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def find_latest_experiment(category: str, name_prefix: str) -> Path | None:
    """在实验目录中找到某前缀的最新实验."""
    exp_dir = PROJECT_ROOT / "experiments" / category
    if not exp_dir.exists():
        return None

    candidates = sorted(
        [d for d in exp_dir.iterdir() if d.is_dir() and d.name.startswith(name_prefix)],
        key=lambda x: x.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def load_metrics(exp_dir: Path) -> dict:
    """加载实验指标."""
    metrics_file = exp_dir / "metrics.json"
    if metrics_file.exists():
        with open(metrics_file) as f:
            return json.load(f)
    return {}


def main():
    """对比所有 v7c/v8 系列实验."""
    versions = [
        ("weekly_bull_v7c", "Bull v7c (基线)"),
        ("weekly_bull_v8a", "Bull v8a (回归+阈值)"),
        ("weekly_bull_v8b", "Bull v8b (Stacking)"),
        ("weekly_bull_v8c", "Bull v8c (分类+阈值)"),
        ("weekly_bear_v7c", "Bear v7c (基线)"),
        ("weekly_bear_v8a", "Bear v8a (回归+阈值)"),
        ("weekly_bear_v8b", "Bear v8b (Stacking)"),
        ("weekly_bear_v8c", "Bear v8c (分类+阈值)"),
    ]

    print("=" * 100)
    print("v8 系列实验对比报告")
    print("=" * 100)

    key_metrics = ["accuracy", "f1_binary", "f1_macro", "cohen_kappa", "precision_binary", "recall_binary"]

    # 表头
    header = f"{'版本':<30}" + "".join(f"{m:<18}" for m in key_metrics)
    print(header)
    print("-" * 100)

    results = {}
    for prefix, label in versions:
        exp_dir = find_latest_experiment("weekly", prefix)
        if exp_dir is None:
            print(f"{label:<30} — 未找到实验")
            continue

        metrics = load_metrics(exp_dir)
        if not metrics:
            print(f"{label:<30} — 指标文件为空")
            continue

        results[prefix] = metrics
        row = f"{label:<30}"
        for m in key_metrics:
            val = metrics.get(m, float("nan"))
            row += f"{val:<18.4f}"
        print(row)

    print("-" * 100)

    # 对比分析
    print("\n📊 对比分析:")

    for direction in ["bull", "bear"]:
        dir_label = "Bull" if direction == "bull" else "Bear"
        baseline_key = f"weekly_{direction}_v7c"
        v8_keys = [f"weekly_{direction}_v8a", f"weekly_{direction}_v8b", f"weekly_{direction}_v8c"]

        if baseline_key not in results:
            continue

        baseline = results[baseline_key]
        print(f"\n  {dir_label} 方向:")
        print(f"    v7c (基线): Kappa={baseline.get('cohen_kappa', 0):.4f}, F1_macro={baseline.get('f1_macro', 0):.4f}")

        for vk in v8_keys:
            if vk not in results:
                continue
            m = results[vk]
            kappa_diff = m.get("cohen_kappa", 0) - baseline.get("cohen_kappa", 0)
            f1_diff = m.get("f1_macro", 0) - baseline.get("f1_macro", 0)
            symbol = "🟢" if kappa_diff > 0 else ("🔴" if kappa_diff < 0 else "⚪")
            name = vk.replace(f"weekly_{direction}_", "")
            print(f"    {name}: Kappa={m.get('cohen_kappa', 0):.4f} ({kappa_diff:+.4f}), "
                  f"F1_macro={m.get('f1_macro', 0):.4f} ({f1_diff:+.4f}) {symbol}")

    # 保存 Markdown 报告
    report_path = PROJECT_ROOT / "reports" / "v8_comparison_report.md"
    with open(report_path, "w") as f:
        f.write("# v8 系列实验对比报告\n\n")
        f.write("## 实验概要\n\n")
        f.write("| 版本 | 策略 | 说明 |\n")
        f.write("|------|------|------|\n")
        f.write("| v7c | LightGBM 分类 | 基线: 外部数据 + reversal + 优化调参 |\n")
        f.write("| v8a | LightGBM 回归 | 回归目标 + 概率阈值优化 |\n")
        f.write("| v8b | Stacking 集成 | 4 个 LightGBM 基学习器 + 逻辑回归元学习器 |\n")
        f.write("| v8c | LightGBM 分类 | 更多迭代 + 更低学习率 + 概率阈值优化(Kappa) |\n\n")
        f.write("## 指标对比\n\n")
        f.write("| 版本 | " + " | ".join(key_metrics) + " |\n")
        f.write("|------|" + "|".join(["------"] * len(key_metrics)) + "|\n")

        for prefix, label in versions:
            if prefix in results:
                m = results[prefix]
                vals = " | ".join(f"{m.get(k, 0):.4f}" for k in key_metrics)
                f.write(f"| {label} | {vals} |\n")

        f.write("\n## 结论\n\n")
        f.write("（实验运行后自动填充）\n")

    print(f"\n📄 报告已保存到: {report_path}")


if __name__ == "__main__":
    main()
