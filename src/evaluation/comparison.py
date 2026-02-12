"""实验对比分析模块."""

import json
import logging
from pathlib import Path

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


def load_experiment_config(exp_dir: str | Path) -> dict:
    """加载单个实验的配置."""
    import yaml
    exp_dir = Path(exp_dir)
    config_path = exp_dir / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    with open(config_path) as f:
        return yaml.safe_load(f)


def compare_experiments(
    experiment_dirs: list[str | Path],
    output_path: str | Path | None = None,
) -> str:
    """对比多个实验，生成 Markdown 对比报告.

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
    rows = []
    configs = []

    for exp_dir in experiment_dirs:
        exp_dir = Path(exp_dir)
        exp_id = exp_dir.name

        try:
            metrics = load_experiment_metrics(exp_dir)
            config = load_experiment_config(exp_dir)
        except FileNotFoundError as e:
            logger.warning(f"跳过实验 {exp_id}: {e}")
            continue

        row = {"experiment_id": exp_id}
        row.update(metrics)
        rows.append(row)
        configs.append({"id": exp_id, "config": config})

    if not rows:
        return "没有可对比的实验数据"

    df = pd.DataFrame(rows).set_index("experiment_id")

    # ---------- 生成报告 ----------
    lines = [
        "# 实验对比报告",
        "",
        f"**生成时间**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**对比实验数**: {len(rows)}",
        "",
        "## 指标对比",
        "",
        tabulate(df, headers="keys", tablefmt="pipe", floatfmt=".4f"),
        "",
    ]

    # 高亮最佳
    if len(df) > 1:
        lines.append("## 最佳指标")
        lines.append("")
        for col in df.columns:
            best_id = df[col].idxmax()
            lines.append(f"- **{col}**: {best_id} ({df[col].max():.4f})")
        lines.append("")

    # 配置差异
    lines.append("## 配置差异")
    lines.append("")
    for cfg_info in configs:
        exp_id = cfg_info["id"]
        cfg = cfg_info["config"]
        lines.append(f"### {exp_id}")
        lines.append(f"- 特征集: `{cfg.get('features', {}).get('sets', 'N/A')}`")
        lines.append(f"- 标签: T={cfg.get('label', {}).get('T', 'N/A')}, X={cfg.get('label', {}).get('X', 'N/A')}")
        lines.append(f"- 模型: {cfg.get('model', {}).get('type', 'N/A')}")
        lines.append("")

    report = "\n".join(lines)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        logger.info(f"对比报告已保存: {output_path}")

    return report
