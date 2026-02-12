"""实验对比分析模块 — 生成详细的 Markdown 对比报告."""

import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from tabulate import tabulate

logger = logging.getLogger(__name__)


def load_experiment_metrics(exp_dir: str | Path) -> dict:
    """加载单个实验的指标."""
    exp_dir = Path(exp_dir)
    metrics_path = exp_dir / "metrics.json"
    if not metrics_path.exists():
        raise FileNotFoundError(f"指标文件不存在: {metrics_path}")
    with open(metrics_path) as f:
        return json.load(f)


def load_experiment_meta(exp_dir: str | Path) -> dict:
    """加载单个实验的元信息."""
    exp_dir = Path(exp_dir)
    meta_path = exp_dir / "meta.json"
    if not meta_path.exists():
        return {}
    with open(meta_path) as f:
        return json.load(f)


def load_experiment_config(exp_dir: str | Path) -> dict:
    """加载单个实验的配置."""
    import yaml
    exp_dir = Path(exp_dir)
    config_path = exp_dir / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_fold_metrics(exp_dir: str | Path) -> pd.DataFrame | None:
    """加载 fold 指标."""
    exp_dir = Path(exp_dir)
    fold_path = exp_dir / "fold_metrics.csv"
    if not fold_path.exists():
        return None
    return pd.read_csv(fold_path)


def load_feature_importance(exp_dir: str | Path) -> pd.DataFrame | None:
    """加载特征重要性."""
    exp_dir = Path(exp_dir)
    fi_path = exp_dir / "feature_importance.csv"
    if not fi_path.exists():
        return None
    return pd.read_csv(fi_path)


def _fmt(val, fmt=".4f") -> str:
    """格式化数值."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "-"
    if isinstance(val, float):
        return f"{val:{fmt}}"
    return str(val)


def _delta_str(val: float, higher_is_better: bool = True) -> str:
    """格式化差值，带涨跌箭头."""
    if val > 0:
        arrow = "📈" if higher_is_better else "📉"
        return f"{arrow} +{val:.4f}"
    elif val < 0:
        arrow = "📉" if higher_is_better else "📈"
        return f"{arrow} {val:.4f}"
    return "→ 0.0000"


# 指标是否越高越好
_HIGHER_IS_BETTER = {
    "accuracy": True,
    "f1_macro": True,
    "precision_macro": True,
    "recall_macro": True,
    "cohen_kappa": True,
}


def compare_experiments(
    experiment_dirs: list[str | Path],
    output_path: str | Path | None = None,
) -> str:
    """对比多个实验，生成详细 Markdown 对比报告.

    Parameters
    ----------
    experiment_dirs : list[str | Path]
        实验目录列表
    output_path : str | Path | None
        报告输出路径

    Returns
    -------
    str
        Markdown 格式的对比报告
    """
    # ── 收集所有实验数据 ──
    experiments = []
    for exp_dir in experiment_dirs:
        exp_dir = Path(exp_dir)
        exp_id = exp_dir.name
        try:
            metrics = load_experiment_metrics(exp_dir)
            config = load_experiment_config(exp_dir)
            meta = load_experiment_meta(exp_dir)
            fold_df = load_fold_metrics(exp_dir)
            fi_df = load_feature_importance(exp_dir)
        except FileNotFoundError as e:
            logger.warning(f"跳过实验 {exp_id}: {e}")
            continue

        experiments.append({
            "id": exp_id,
            "short_id": meta.get("name", exp_id[:25]),
            "metrics": metrics,
            "config": config,
            "meta": meta,
            "fold_df": fold_df,
            "fi_df": fi_df,
            "dir": exp_dir,
        })

    if not experiments:
        return "没有可对比的实验数据"

    lines = []

    # ══════════════════════════════════════════
    # 标题
    # ══════════════════════════════════════════
    lines.append("# 📊 FcstLabPro 实验对比报告")
    lines.append("")
    lines.append(f"> **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    lines.append(f"> **对比实验数**: {len(experiments)}  ")
    lines.append(f"> **平台**: FcstLabPro")
    lines.append("")

    # ══════════════════════════════════════════
    # 1. 实验概览
    # ══════════════════════════════════════════
    lines.append("---")
    lines.append("## 1. 实验概览")
    lines.append("")

    overview_rows = []
    for exp in experiments:
        meta = exp["meta"]
        cfg = exp["config"]
        feat_sets = cfg.get("features", {}).get("sets", [])
        overview_rows.append({
            "实验名": exp["short_id"],
            "大类": meta.get("category", "default"),
            "标签": ", ".join(meta.get("tags", [])),
            "描述": meta.get("description", "")[:50],
            "特征集数": len(feat_sets),
            "创建时间": meta.get("created_at", "")[:19],
            "耗时": f"{meta.get('duration_seconds', 0):.0f}s",
            "Git": meta.get("git", {}).get("commit", "?"),
            "状态": meta.get("status", "?"),
        })

    lines.append(tabulate(overview_rows, headers="keys", tablefmt="pipe"))
    lines.append("")

    # ══════════════════════════════════════════
    # 2. 核心指标对比
    # ══════════════════════════════════════════
    lines.append("---")
    lines.append("## 2. 核心指标对比")
    lines.append("")

    # 构建指标表
    all_metric_keys = sorted(set().union(*(exp["metrics"].keys() for exp in experiments)))
    metric_rows = []
    for exp in experiments:
        row = {"实验": exp["short_id"]}
        for k in all_metric_keys:
            row[k] = _fmt(exp["metrics"].get(k))
        metric_rows.append(row)

    lines.append(tabulate(metric_rows, headers="keys", tablefmt="pipe"))
    lines.append("")

    # 如果有 2 个实验，显示差值对比
    if len(experiments) == 2:
        lines.append("### 指标差异 (实验2 − 实验1)")
        lines.append("")
        exp1, exp2 = experiments[0], experiments[1]
        for k in all_metric_keys:
            v1 = exp1["metrics"].get(k, 0) or 0
            v2 = exp2["metrics"].get(k, 0) or 0
            delta = v2 - v1
            hib = _HIGHER_IS_BETTER.get(k, True)
            lines.append(f"- **{k}**: {_delta_str(delta, hib)}")
        lines.append("")

    # 最佳指标高亮
    if len(experiments) > 1:
        lines.append("### 🏆 各指标最佳")
        lines.append("")
        for k in all_metric_keys:
            hib = _HIGHER_IS_BETTER.get(k, True)
            best_exp = max(experiments, key=lambda e: e["metrics"].get(k, float('-inf')) if hib
                          else -e["metrics"].get(k, float('inf')))
            best_val = best_exp["metrics"].get(k, 0)
            lines.append(f"- **{k}**: {best_exp['short_id']} ({_fmt(best_val)})")
        lines.append("")

    # ══════════════════════════════════════════
    # 3. 配置差异对比
    # ══════════════════════════════════════════
    lines.append("---")
    lines.append("## 3. 配置差异对比")
    lines.append("")

    # 关键配置项对比
    config_compare_keys = [
        ("features.sets", lambda c: ", ".join(c.get("features", {}).get("sets", []))),
        ("features.sets (数量)", lambda c: str(len(c.get("features", {}).get("sets", [])))),
        ("label.strategy", lambda c: str(c.get("label", {}).get("strategy", "N/A"))),
        ("label.T", lambda c: str(c.get("label", {}).get("T", "N/A"))),
        ("label.X", lambda c: str(c.get("label", {}).get("X", "N/A"))),
        ("model.type", lambda c: str(c.get("model", {}).get("type", "N/A"))),
        ("model.n_estimators", lambda c: str(c.get("model", {}).get("params", {}).get("n_estimators", "N/A"))),
        ("model.max_depth", lambda c: str(c.get("model", {}).get("params", {}).get("max_depth", "N/A"))),
        ("model.learning_rate", lambda c: str(c.get("model", {}).get("params", {}).get("learning_rate", "N/A"))),
        ("model.num_leaves", lambda c: str(c.get("model", {}).get("params", {}).get("num_leaves", "N/A"))),
        ("model.subsample", lambda c: str(c.get("model", {}).get("params", {}).get("subsample", "N/A"))),
        ("eval.init_train", lambda c: str(c.get("evaluation", {}).get("init_train", "N/A"))),
        ("eval.oos_window", lambda c: str(c.get("evaluation", {}).get("oos_window", "N/A"))),
        ("eval.step", lambda c: str(c.get("evaluation", {}).get("step", "N/A"))),
        ("seed", lambda c: str(c.get("seed", "N/A"))),
    ]

    cfg_rows = []
    for key_name, extractor in config_compare_keys:
        row = {"配置项": key_name}
        values = []
        for exp in experiments:
            val = extractor(exp["config"])
            row[exp["short_id"]] = val
            values.append(val)
        # 标记差异
        row["差异"] = "✅ 相同" if len(set(values)) == 1 else "⚡ 不同"
        cfg_rows.append(row)

    lines.append(tabulate(cfg_rows, headers="keys", tablefmt="pipe"))
    lines.append("")

    # ══════════════════════════════════════════
    # 4. Walk-Forward Fold 指标对比
    # ══════════════════════════════════════════
    fold_dfs_available = [exp for exp in experiments if exp["fold_df"] is not None]
    if fold_dfs_available:
        lines.append("---")
        lines.append("## 4. Walk-Forward Fold 指标对比")
        lines.append("")

        # 每个实验的 fold 统计
        for exp in fold_dfs_available:
            fold_df = exp["fold_df"]
            lines.append(f"### {exp['short_id']}")
            lines.append(f"- Folds 数量: {len(fold_df)}")

            for metric in ["accuracy", "f1_macro", "cohen_kappa"]:
                if metric in fold_df.columns:
                    vals = fold_df[metric]
                    lines.append(
                        f"- **{metric}**: mean={vals.mean():.4f}, "
                        f"std={vals.std():.4f}, "
                        f"min={vals.min():.4f}, max={vals.max():.4f}"
                    )
            lines.append("")

        # 跨实验 fold 汇总对比表
        if len(fold_dfs_available) > 1:
            lines.append("### Fold 指标统计汇总对比")
            lines.append("")

            summary_rows = []
            for exp in fold_dfs_available:
                fold_df = exp["fold_df"]
                row = {"实验": exp["short_id"], "Folds": len(fold_df)}
                for metric in ["accuracy", "f1_macro", "cohen_kappa"]:
                    if metric in fold_df.columns:
                        vals = fold_df[metric]
                        row[f"{metric} (mean±std)"] = f"{vals.mean():.4f}±{vals.std():.4f}"
                summary_rows.append(row)

            lines.append(tabulate(summary_rows, headers="keys", tablefmt="pipe"))
            lines.append("")

    # ══════════════════════════════════════════
    # 5. 特征重要性对比
    # ══════════════════════════════════════════
    fi_available = [exp for exp in experiments if exp["fi_df"] is not None]
    if fi_available:
        lines.append("---")
        lines.append("## 5. 特征重要性对比")
        lines.append("")

        # Top 20 特征对比
        TOP_N = 20
        lines.append(f"### Top {TOP_N} 特征")
        lines.append("")

        for exp in fi_available:
            fi_df = exp["fi_df"].head(TOP_N)
            lines.append(f"#### {exp['short_id']} (共 {len(exp['fi_df'])} 个特征)")
            lines.append("")
            fi_rows = []
            total_imp = exp["fi_df"]["importance"].sum()
            for idx, row in fi_df.iterrows():
                pct = row["importance"] / total_imp * 100 if total_imp > 0 else 0
                fi_rows.append({
                    "排名": idx + 1,
                    "特征": row["feature"],
                    "重要性": int(row["importance"]),
                    "占比": f"{pct:.1f}%",
                })
            lines.append(tabulate(fi_rows, headers="keys", tablefmt="pipe"))
            lines.append("")

        # 如果有 2 个实验，对比 Top 特征的交集和差集
        if len(fi_available) == 2:
            lines.append("### 特征重要性交集与差异分析")
            lines.append("")

            top1 = set(fi_available[0]["fi_df"].head(TOP_N)["feature"].tolist())
            top2 = set(fi_available[1]["fi_df"].head(TOP_N)["feature"].tolist())

            common = top1 & top2
            only_1 = top1 - top2
            only_2 = top2 - top1

            lines.append(f"- **共同 Top{TOP_N} 特征** ({len(common)} 个): {', '.join(sorted(common)) if common else '无'}")
            lines.append(f"- **仅 {fi_available[0]['short_id']} Top{TOP_N}** ({len(only_1)} 个): {', '.join(sorted(only_1)) if only_1 else '无'}")
            lines.append(f"- **仅 {fi_available[1]['short_id']} Top{TOP_N}** ({len(only_2)} 个): {', '.join(sorted(only_2)) if only_2 else '无'}")
            union_size = len(top1 | top2)
            lines.append(f"- **Jaccard 相似度**: {len(common) / union_size:.2%}" if union_size > 0 else "- **Jaccard 相似度**: N/A")
            lines.append("")

    # ══════════════════════════════════════════
    # 6. 数据与特征维度
    # ══════════════════════════════════════════
    lines.append("---")
    lines.append("## 6. 数据与特征维度")
    lines.append("")

    dim_rows = []
    for exp in experiments:
        cfg = exp["config"]
        feat_sets = cfg.get("features", {}).get("sets", [])
        n_features = len(exp["fi_df"]) if exp["fi_df"] is not None else "N/A"
        dim_rows.append({
            "实验": exp["short_id"],
            "数据区间": f"{cfg.get('data', {}).get('start', '?')} ~ {cfg.get('data', {}).get('end', '?')}",
            "特征集": ", ".join(feat_sets),
            "特征数": n_features,
            "模型类型": cfg.get("model", {}).get("type", "N/A"),
        })

    lines.append(tabulate(dim_rows, headers="keys", tablefmt="pipe"))
    lines.append("")

    # ══════════════════════════════════════════
    # 7. 结论与建议
    # ══════════════════════════════════════════
    lines.append("---")
    lines.append("## 7. 结论与建议")
    lines.append("")

    if len(experiments) >= 2:
        # 自动生成关键发现
        lines.append("### 关键发现")
        lines.append("")

        # 找最佳实验
        best_acc_exp = max(experiments, key=lambda e: e["metrics"].get("accuracy", 0))
        best_f1_exp = max(experiments, key=lambda e: e["metrics"].get("f1_macro", 0))
        best_kappa_exp = max(experiments, key=lambda e: e["metrics"].get("cohen_kappa", float("-inf")))

        lines.append(f"1. **Accuracy 最佳**: {best_acc_exp['short_id']} ({_fmt(best_acc_exp['metrics'].get('accuracy'))})")
        lines.append(f"2. **F1-Macro 最佳**: {best_f1_exp['short_id']} ({_fmt(best_f1_exp['metrics'].get('f1_macro'))})")
        lines.append(f"3. **Cohen's Kappa 最佳**: {best_kappa_exp['short_id']} ({_fmt(best_kappa_exp['metrics'].get('cohen_kappa'))})")
        lines.append("")

        # 配置差异分析
        feat_sets_list = [set(e["config"].get("features", {}).get("sets", [])) for e in experiments]
        if len(set(frozenset(s) for s in feat_sets_list)) > 1:
            lines.append("4. **特征集差异**: 各实验使用了不同的特征集组合，这可能是性能差异的主要因素")
        else:
            lines.append("4. **特征集相同**: 各实验使用了相同的特征集，性能差异可能来自其他超参数")

        n_estimators_list = [e["config"].get("model", {}).get("params", {}).get("n_estimators") for e in experiments]
        if len(set(n_estimators_list)) > 1:
            lines.append(f"5. **模型复杂度不同**: n_estimators 分别为 {n_estimators_list}")
        lines.append("")

        lines.append("### 建议后续实验")
        lines.append("")
        lines.append("- [ ] 尝试不同的特征集组合消融实验")
        lines.append("- [ ] 调优 learning_rate + n_estimators 组合")
        lines.append("- [ ] 增加更多 Walk-Forward folds 以提高评估稳定性")
        lines.append("- [ ] 分析 cohen_kappa 偏低的原因（标签分布？类别不平衡？）")
        lines.append("")

    # ══════════════════════════════════════════
    # 附录：实验产物清单
    # ══════════════════════════════════════════
    lines.append("---")
    lines.append("## 附录: 实验产物清单")
    lines.append("")

    for exp in experiments:
        exp_dir = exp["dir"]
        lines.append(f"### {exp['short_id']}")
        lines.append(f"- **目录**: `{exp_dir}`")
        if exp_dir.exists():
            files = sorted(exp_dir.iterdir())
            for f in files:
                size = f.stat().st_size
                size_str = f"{size / 1024:.1f}KB" if size > 1024 else f"{size}B"
                lines.append(f"  - `{f.name}` ({size_str})")
        lines.append("")

    # ── 保存 ──
    report = "\n".join(lines)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        logger.info(f"对比报告已保存: {output_path}")

    return report
