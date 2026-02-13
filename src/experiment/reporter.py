"""实验报告生成器 — 自动生成 Markdown 实验报告."""

import json
import logging
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from tabulate import tabulate

from src.evaluation.metrics import compute_classification_report, compute_confusion_matrix

logger = logging.getLogger(__name__)


def generate_experiment_report(
    experiment_id: str,
    config: dict,
    meta: dict,
    aggregate_metrics: dict[str, float],
    fold_metrics_df: pd.DataFrame,
    feature_importance_df: pd.DataFrame,
    classification_report_text: str,
    confusion_mat: np.ndarray,
    output_path: str | Path,
) -> str:
    """生成完整的 Markdown 实验报告.

    Parameters
    ----------
    experiment_id : str
        实验 ID
    config : dict
        完整配置
    meta : dict
        实验元信息
    aggregate_metrics : dict
        汇总指标
    fold_metrics_df : pd.DataFrame
        每个 fold 的指标
    feature_importance_df : pd.DataFrame
        特征重要性 (columns: feature, importance)
    classification_report_text : str
        sklearn 分类报告文本
    confusion_mat : np.ndarray
        混淆矩阵
    output_path : str | Path
        报告输出路径

    Returns
    -------
    str
        报告内容
    """
    label_cfg = config.get("label", {})
    model_cfg = config.get("model", {})
    eval_cfg = config.get("evaluation", {})
    data_cfg = config.get("data", {})
    feat_cfg = config.get("features", {})

    lines = []

    # ========== 标题 ==========
    lines.append(f"# 实验报告: {experiment_id}")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # ========== 实验概要 ==========
    lines.append("## 1. 实验概要")
    lines.append("")
    lines.append(f"| 项目 | 值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 实验名称 | {config.get('experiment', {}).get('name', '')} |")
    lines.append(f"| 描述 | {config.get('experiment', {}).get('description', '')} |")
    lines.append(f"| 标签 | {config.get('experiment', {}).get('tags', [])} |")
    lines.append(f"| Git Commit | {meta.get('git', {}).get('commit', 'N/A')} |")
    lines.append(f"| Git Branch | {meta.get('git', {}).get('branch', 'N/A')} |")
    lines.append(f"| 耗时 | {meta.get('duration_seconds', 'N/A')}s |")
    lines.append(f"| 随机种子 | {config.get('seed', 'N/A')} |")
    lines.append("")

    # ========== 数据配置 ==========
    lines.append("## 2. 数据配置")
    lines.append("")
    lines.append(f"- **数据源**: {data_cfg.get('source', 'N/A')}")
    lines.append(f"- **交易对**: {data_cfg.get('symbol', 'N/A')}")
    lines.append(f"- **周期**: {data_cfg.get('interval', 'N/A')}")
    lines.append(f"- **时间范围**: {data_cfg.get('start', 'N/A')} ~ {data_cfg.get('end', 'N/A')}")
    lines.append(f"- **数据文件**: `{data_cfg.get('path', 'N/A')}`")
    lines.append("")

    # ========== 特征配置 ==========
    lines.append("## 3. 特征配置")
    lines.append("")
    lines.append(f"- **特征集**: {feat_cfg.get('sets', [])}")
    lines.append(f"- **总特征数**: {len(feature_importance_df)}")
    lines.append(f"- **NaN处理**: {feat_cfg.get('drop_na_method', 'N/A')}")
    lines.append("")

    # ========== 标签配置 ==========
    lines.append("## 4. 标签配置")
    lines.append("")
    lines.append(f"- **策略**: {label_cfg.get('strategy', 'N/A')}")
    lines.append(f"- **窗口 T**: {label_cfg.get('T', 'N/A')} 天")
    lines.append(f"- **阈值 X**: {label_cfg.get('X', 'N/A')} ({label_cfg.get('X', 0)*100:.0f}%)")
    lines.append("")

    # ========== 模型配置 ==========
    lines.append("## 5. 模型配置")
    lines.append("")
    lines.append(f"- **类型**: {model_cfg.get('type', 'N/A')}")
    lines.append(f"- **参数**:")
    for k, v in model_cfg.get("params", {}).items():
        lines.append(f"  - {k}: {v}")
    lines.append("")

    # ========== 评估结果 ==========
    lines.append("## 6. 评估结果（汇总）")
    lines.append("")
    metrics_table = [[k, f"{v:.4f}"] for k, v in aggregate_metrics.items()]
    lines.append(tabulate(metrics_table, headers=["指标", "值"], tablefmt="pipe"))
    lines.append("")

    # ========== Walk-Forward Fold 详情 ==========
    lines.append("## 7. Walk-Forward Fold 详情")
    lines.append("")
    lines.append(f"- **方法**: {eval_cfg.get('method', 'N/A')}")
    lines.append(f"- **初始训练集**: {eval_cfg.get('init_train', 'N/A')}")
    lines.append(f"- **OOS窗口**: {eval_cfg.get('oos_window', 'N/A')}")
    lines.append(f"- **步进**: {eval_cfg.get('step', 'N/A')}")
    lines.append(f"- **总 Fold 数**: {len(fold_metrics_df)}")
    lines.append("")
    lines.append(tabulate(fold_metrics_df, headers="keys", tablefmt="pipe",
                          floatfmt=".4f", showindex=False))
    lines.append("")

    # ========== 分类报告 ==========
    lines.append("## 8. 分类报告")
    lines.append("")
    lines.append("```")
    lines.append(classification_report_text)
    lines.append("```")
    lines.append("")

    # ========== 混淆矩阵 ==========
    lines.append("## 9. 混淆矩阵")
    lines.append("")
    n_classes = confusion_mat.shape[0]
    if n_classes == 2:
        # 二分类（Bull/Bear 模型）
        label_map = label_cfg.get("map", {})
        # 检测是 Bull 还是 Bear 模型
        if label_map and label_map.get(2, label_map.get("2")) == 1:
            cm_labels = ["非涨(0)", "大涨(1)"]
        elif label_map and label_map.get(0, label_map.get("0")) == 1:
            cm_labels = ["非跌(0)", "大跌(1)"]
        else:
            cm_labels = ["负例(0)", "正例(1)"]
    else:
        cm_labels = ["顶部反转(0)", "正常(1)", "底部反转(2)"]
    cm_df = pd.DataFrame(confusion_mat, index=cm_labels[:n_classes], columns=cm_labels[:n_classes])
    lines.append(tabulate(cm_df, headers="keys", tablefmt="pipe"))
    lines.append("")

    # ========== Top 20 重要特征 ==========
    lines.append("## 10. Top 20 重要特征")
    lines.append("")
    top20 = feature_importance_df.head(20)
    lines.append(tabulate(top20, headers="keys", tablefmt="pipe",
                          floatfmt=".4f", showindex=False))
    lines.append("")

    # ========== 完整配置快照 ==========
    lines.append("## 附录: 完整配置")
    lines.append("")
    lines.append("```yaml")
    import yaml
    lines.append(yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False))
    lines.append("```")

    report = "\n".join(lines)

    # 写入文件
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    logger.info(f"实验报告已生成: {output_path}")

    return report
