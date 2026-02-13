#!/usr/bin/env python3
"""周预测联合实验 — 同时运行 Bull + Bear 模型并生成合并报告.

设计理念:
  - Bull 模型 (多头): 专门判断 "会不会大涨？" → label map {0:0, 1:0, 2:1}
  - Bear 模型 (空头): 专门判断 "会不会大跌？" → label map {0:1, 1:0, 2:0}
  - 两个模型独立训练、独立预测
  - 结果合并到同一份报告，附带信号矩阵分析

Usage:
    python scripts/run_weekly_prediction.py
    python scripts/run_weekly_prediction.py --bull-config configs/experiments/weekly/exp_weekly_bull_model.yaml \\
                                            --bear-config configs/experiments/weekly/exp_weekly_bear_model.yaml
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logging import setup_logging
from src.experiment.runner import run_experiment
from src.experiment.tracker import (
    get_experiment_dir, EXPERIMENTS_DIR, list_experiments,
)

logger = logging.getLogger(__name__)

# 默认配置路径
DEFAULT_BULL_CONFIG = "configs/experiments/weekly/exp_weekly_bull_model.yaml"
DEFAULT_BEAR_CONFIG = "configs/experiments/weekly/exp_weekly_bear_model.yaml"


def load_experiment_artifacts(experiment_id: str) -> dict:
    """加载实验产物."""
    exp_dir = get_experiment_dir(experiment_id)
    if exp_dir is None:
        raise FileNotFoundError(f"实验目录未找到: {experiment_id}")

    artifacts = {}

    # metrics.json
    with open(exp_dir / "metrics.json") as f:
        artifacts["metrics"] = json.load(f)

    # meta.json
    with open(exp_dir / "meta.json") as f:
        artifacts["meta"] = json.load(f)

    # config.yaml
    import yaml
    with open(exp_dir / "config.yaml") as f:
        artifacts["config"] = yaml.safe_load(f)

    # predictions.csv
    artifacts["predictions"] = pd.read_csv(exp_dir / "predictions.csv")

    # fold_metrics.csv
    artifacts["fold_metrics"] = pd.read_csv(exp_dir / "fold_metrics.csv")

    # feature_importance.csv
    artifacts["feature_importance"] = pd.read_csv(exp_dir / "feature_importance.csv")

    # report.md (单模型原始报告)
    report_path = exp_dir / "report.md"
    if report_path.exists():
        artifacts["report"] = report_path.read_text(encoding="utf-8")

    artifacts["exp_dir"] = exp_dir

    return artifacts


def build_signal_matrix(bull_preds: pd.DataFrame, bear_preds: pd.DataFrame) -> pd.DataFrame:
    """构建信号矩阵.

    组合 Bull/Bear 预测结果，生成 4 种信号状态:
      - 📈 强多头: Bull=1, Bear=0 → 预测大涨，不会大跌
      - 📉 强空头: Bull=0, Bear=1 → 预测大跌，不会大涨
      - ⚠️ 震荡:   Bull=0, Bear=0 → 预测既不涨也不跌
      - 🔥 高波动: Bull=1, Bear=1 → 预测可能大涨也可能大跌
    """
    # 对齐长度 (取较短的)
    n = min(len(bull_preds), len(bear_preds))
    bull_y_pred = bull_preds["y_pred"].values[:n]
    bear_y_pred = bear_preds["y_pred"].values[:n]

    signals = []
    for b, d in zip(bull_y_pred, bear_y_pred):
        if b == 1 and d == 0:
            signals.append("强多头")
        elif b == 0 and d == 1:
            signals.append("强空头")
        elif b == 0 and d == 0:
            signals.append("震荡")
        else:  # b == 1 and d == 1
            signals.append("高波动")

    df = pd.DataFrame({
        "bull_pred": bull_y_pred,
        "bear_pred": bear_y_pred,
        "signal": signals,
    })
    return df


def generate_combined_report(
    bull_artifacts: dict,
    bear_artifacts: dict,
    signal_df: pd.DataFrame,
    output_path: Path,
) -> str:
    """生成 Bull + Bear 合并周预测报告."""
    from tabulate import tabulate

    bull_metrics = bull_artifacts["metrics"]
    bear_metrics = bear_artifacts["metrics"]
    bull_config = bull_artifacts["config"]
    bear_config = bear_artifacts["config"]
    bull_folds = bull_artifacts["fold_metrics"]
    bear_folds = bear_artifacts["fold_metrics"]
    bull_fi = bull_artifacts["feature_importance"]
    bear_fi = bear_artifacts["feature_importance"]
    bull_preds = bull_artifacts["predictions"]
    bear_preds = bear_artifacts["predictions"]

    lines = []

    # =============== 标题 ===============
    lines.append("# 📊 周预测综合报告 — Bull & Bear 双模型")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # =============== 实验设计 ===============
    lines.append("## 1. 实验设计")
    lines.append("")
    lines.append("### 1.1 设计理念")
    lines.append("")
    lines.append("将传统的三分类（涨/平/跌）拆分为两个独立的二分类模型：")
    lines.append("")
    lines.append("| 模型 | 目标 | 正例含义 | 标签映射 |")
    lines.append("|------|------|---------|---------|")
    bull_label_map = bull_config.get("label", {}).get("map", {})
    bear_label_map = bear_config.get("label", {}).get("map", {})
    lines.append(f"| 🐂 Bull 模型 | 判断会不会大涨 | 1 = 未来大涨 | {bull_label_map} |")
    lines.append(f"| 🐻 Bear 模型 | 判断会不会大跌 | 1 = 未来大跌 | {bear_label_map} |")
    lines.append("")

    lines.append("### 1.2 公共参数")
    lines.append("")
    bull_label = bull_config.get("label", {})
    lines.append(f"- **数据**: {bull_config.get('data', {}).get('path', 'N/A')}")
    lines.append(f"- **预测窗口 T**: {bull_label.get('T', 'N/A')} 天 ({bull_label.get('T', 0)//7} 周)")
    lines.append(f"- **阈值 X**: {bull_label.get('X', 'N/A')} ({bull_label.get('X', 0)*100:.0f}%)")
    lines.append(f"- **特征集**: {bull_config.get('features', {}).get('sets', [])}")
    lines.append(f"- **模型**: {bull_config.get('model', {}).get('type', 'N/A')}")
    lines.append("")

    # =============== 信号矩阵 ===============
    lines.append("### 1.3 信号矩阵")
    lines.append("")
    lines.append("两模型组合后产生 4 种信号状态：")
    lines.append("")
    lines.append("| Bull 预测 | Bear 预测 | 信号 | 解释 |")
    lines.append("|:---------:|:---------:|:----:|------|")
    lines.append("| 1 (大涨) | 0 (不跌) | 📈 强多头 | 模型确认上涨趋势，适合做多 |")
    lines.append("| 0 (不涨) | 1 (大跌) | 📉 强空头 | 模型确认下跌趋势，适合防守/做空 |")
    lines.append("| 0 (不涨) | 0 (不跌) | ⏸️ 震荡 | 无明确方向，观望为主 |")
    lines.append("| 1 (大涨) | 1 (大跌) | ⚠️ 高波动 | 方向不确定但波动大，需谨慎 |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # =============== 核心指标对比 ===============
    lines.append("## 2. 核心指标对比")
    lines.append("")

    # 收集公共指标名
    all_metric_names = sorted(set(bull_metrics.keys()) | set(bear_metrics.keys()))
    metrics_table = []
    for m in all_metric_names:
        bull_val = bull_metrics.get(m, None)
        bear_val = bear_metrics.get(m, None)
        bull_str = f"{bull_val:.4f}" if bull_val is not None else "-"
        bear_str = f"{bear_val:.4f}" if bear_val is not None else "-"
        metrics_table.append([m, bull_str, bear_str])

    lines.append(tabulate(metrics_table, headers=["指标", "🐂 Bull", "🐻 Bear"], tablefmt="pipe"))
    lines.append("")

    # 关键指标点评
    lines.append("### 2.1 关键指标解读")
    lines.append("")

    bull_f1 = bull_metrics.get("f1_binary", bull_metrics.get("f1_macro", 0))
    bear_f1 = bear_metrics.get("f1_binary", bear_metrics.get("f1_macro", 0))
    bull_prec = bull_metrics.get("precision_binary", bull_metrics.get("precision_macro", 0))
    bear_prec = bear_metrics.get("precision_binary", bear_metrics.get("precision_macro", 0))
    bull_recall = bull_metrics.get("recall_binary", bull_metrics.get("recall_macro", 0))
    bear_recall = bear_metrics.get("recall_binary", bear_metrics.get("recall_macro", 0))
    bull_kappa = bull_metrics.get("cohen_kappa", 0)
    bear_kappa = bear_metrics.get("cohen_kappa", 0)

    lines.append(f"- **Bull 模型 F1**: {bull_f1:.4f} (精确率 {bull_prec:.4f} / 召回率 {bull_recall:.4f} / Kappa {bull_kappa:.4f})")
    lines.append(f"- **Bear 模型 F1**: {bear_f1:.4f} (精确率 {bear_prec:.4f} / 召回率 {bear_recall:.4f} / Kappa {bear_kappa:.4f})")
    lines.append("")

    # 多数类基线对比
    lines.append("### 2.2 与多数类基线对比")
    lines.append("")
    lines.append("若模型 **总是预测多数类** (即不做任何学习)，其表现为:")
    lines.append("")

    bull_y = bull_preds["y_true"].values
    bear_y = bear_preds["y_true"].values
    bull_pos_rate = bull_y.mean()
    bear_pos_rate = bear_y.mean()
    bull_majority_acc = max(bull_pos_rate, 1 - bull_pos_rate)
    bear_majority_acc = max(bear_pos_rate, 1 - bear_pos_rate)

    lines.append(f"| 项目 | 🐂 Bull | 🐻 Bear |")
    lines.append(f"|------|---------|---------|")
    lines.append(f"| 正例比例 | {bull_pos_rate:.1%} | {bear_pos_rate:.1%} |")
    lines.append(f"| 多数类基线 Acc | {bull_majority_acc:.4f} | {bear_majority_acc:.4f} |")
    lines.append(f"| 模型 Acc | {bull_metrics.get('accuracy', 0):.4f} | {bear_metrics.get('accuracy', 0):.4f} |")
    bull_acc_lift = bull_metrics.get('accuracy', 0) - bull_majority_acc
    bear_acc_lift = bear_metrics.get('accuracy', 0) - bear_majority_acc
    lines.append(f"| Acc 提升 | {bull_acc_lift:+.4f} | {bear_acc_lift:+.4f} |")
    lines.append(f"| Cohen's Kappa | {bull_kappa:.4f} | {bear_kappa:.4f} |")
    lines.append("")

    # Kappa 解读
    def kappa_level(k):
        if k < 0: return "❌ 比随机差"
        elif k < 0.2: return "❌ 几乎无一致性"
        elif k < 0.4: return "⚠️ 弱一致性"
        elif k < 0.6: return "🔶 中等一致性"
        elif k < 0.8: return "✅ 较强一致性"
        else: return "✅ 强一致性"

    lines.append(f"- Bull Kappa={bull_kappa:.4f} → **{kappa_level(bull_kappa)}**")
    lines.append(f"- Bear Kappa={bear_kappa:.4f} → **{kappa_level(bear_kappa)}**")
    lines.append("")

    if bull_prec > 0.5:
        lines.append("  - ✅ Bull 精确率 > 50%：当模型说 \"会涨\" 时，有一定可信度")
    else:
        lines.append("  - ⚠️ Bull 精确率 < 50%：当模型说 \"会涨\" 时，假信号较多")

    if bear_prec > 0.5:
        lines.append("  - ✅ Bear 精确率 > 50%：当模型说 \"会跌\" 时，有一定可信度")
    else:
        lines.append("  - ⚠️ Bear 精确率 < 50%：当模型说 \"会跌\" 时，假信号较多")
    lines.append("")

    # =============== 信号分布分析 ===============
    lines.append("## 3. 信号分布分析")
    lines.append("")

    signal_counts = signal_df["signal"].value_counts()
    total_signals = len(signal_df)
    signal_table = []
    for sig_name in ["强多头", "强空头", "震荡", "高波动"]:
        cnt = signal_counts.get(sig_name, 0)
        pct = cnt / total_signals * 100 if total_signals > 0 else 0
        emoji = {"强多头": "📈", "强空头": "📉", "震荡": "⏸️", "高波动": "⚠️"}.get(sig_name, "")
        signal_table.append([f"{emoji} {sig_name}", cnt, f"{pct:.1f}%"])

    lines.append(tabulate(signal_table, headers=["信号", "样本数", "占比"], tablefmt="pipe"))
    lines.append("")

    # 信号有效性（如果有 y_true）
    if "y_true" in bull_preds.columns and "y_true" in bear_preds.columns:
        lines.append("### 3.1 信号有效性分析")
        lines.append("")
        lines.append("| 信号 | 样本数 | Bull 实际涨比例 | Bear 实际跌比例 |")
        lines.append("|------|--------|----------------|----------------|")

        n = min(len(bull_preds), len(bear_preds))
        for sig_name in ["强多头", "强空头", "震荡", "高波动"]:
            mask = signal_df["signal"] == sig_name
            cnt = mask.sum()
            if cnt == 0:
                lines.append(f"| {sig_name} | 0 | - | - |")
                continue

            # bull 的 y_true: 1 表示实际上涨
            bull_true_in_signal = bull_preds["y_true"].values[:n][mask]
            actual_bull_rate = bull_true_in_signal.mean()

            # bear 的 y_true: 1 表示实际下跌
            bear_true_in_signal = bear_preds["y_true"].values[:n][mask]
            actual_bear_rate = bear_true_in_signal.mean()

            lines.append(f"| {sig_name} | {cnt} | {actual_bull_rate:.2%} | {actual_bear_rate:.2%} |")

        lines.append("")

    # =============== Walk-Forward 折叠详情 ===============
    lines.append("## 4. Walk-Forward Fold 详情")
    lines.append("")

    lines.append("### 4.1 🐂 Bull 模型 Fold 指标")
    lines.append("")
    lines.append(tabulate(bull_folds, headers="keys", tablefmt="pipe", floatfmt=".4f", showindex=False))
    lines.append("")

    lines.append("### 4.2 🐻 Bear 模型 Fold 指标")
    lines.append("")
    lines.append(tabulate(bear_folds, headers="keys", tablefmt="pipe", floatfmt=".4f", showindex=False))
    lines.append("")

    # Fold 稳定性对比
    lines.append("### 4.3 Fold 稳定性对比")
    lines.append("")
    # 找到公共的数值指标列
    common_cols = [c for c in bull_folds.columns if c in bear_folds.columns
                   and c not in ("fold_id", "train_size", "test_size")]

    stability_table = []
    for col in common_cols:
        bull_mean = bull_folds[col].mean()
        bull_std = bull_folds[col].std()
        bear_mean = bear_folds[col].mean()
        bear_std = bear_folds[col].std()
        stability_table.append([
            col,
            f"{bull_mean:.4f} ± {bull_std:.4f}",
            f"{bear_mean:.4f} ± {bear_std:.4f}",
        ])

    if stability_table:
        lines.append(tabulate(stability_table,
                              headers=["指标", "🐂 Bull (mean±std)", "🐻 Bear (mean±std)"],
                              tablefmt="pipe"))
        lines.append("")

    # =============== Top 特征重要性 ===============
    lines.append("## 5. Top 15 重要特征对比")
    lines.append("")

    lines.append("### 5.1 🐂 Bull 模型 Top 15 特征")
    lines.append("")
    bull_top15 = bull_fi.head(15)
    lines.append(tabulate(bull_top15, headers="keys", tablefmt="pipe", floatfmt=".4f", showindex=False))
    lines.append("")

    lines.append("### 5.2 🐻 Bear 模型 Top 15 特征")
    lines.append("")
    bear_top15 = bear_fi.head(15)
    lines.append(tabulate(bear_top15, headers="keys", tablefmt="pipe", floatfmt=".4f", showindex=False))
    lines.append("")

    # 共同重要特征
    bull_top_set = set(bull_fi.head(20)["feature"])
    bear_top_set = set(bear_fi.head(20)["feature"])
    common_features = bull_top_set & bear_top_set
    bull_unique = bull_top_set - bear_top_set
    bear_unique = bear_top_set - bull_top_set

    lines.append("### 5.3 特征重要性交集分析 (Top 20)")
    lines.append("")
    lines.append(f"- **共同重要特征** ({len(common_features)}): {sorted(common_features)}")
    lines.append(f"- **Bull 独有特征** ({len(bull_unique)}): {sorted(bull_unique)}")
    lines.append(f"- **Bear 独有特征** ({len(bear_unique)}): {sorted(bear_unique)}")
    lines.append("")

    # =============== 策略建议 ===============
    lines.append("## 6. 策略建议")
    lines.append("")

    bull_acc = bull_metrics.get("accuracy", 0)
    bear_acc = bear_metrics.get("accuracy", 0)

    lines.append("### 6.1 模型可用性评估")
    lines.append("")

    def assess_model(name, acc, f1, prec, recall):
        if f1 >= 0.5 and prec >= 0.5:
            return f"✅ {name}模型质量良好 (F1={f1:.3f}, 精确率={prec:.3f})，可用于实盘参考"
        elif f1 >= 0.3:
            return f"⚠️ {name}模型质量一般 (F1={f1:.3f}, 精确率={prec:.3f})，仅作辅助参考"
        else:
            return f"❌ {name}模型质量较差 (F1={f1:.3f}, 精确率={prec:.3f})，不建议使用"

    lines.append(f"- {assess_model('Bull', bull_acc, bull_f1, bull_prec, bull_recall)}")
    lines.append(f"- {assess_model('Bear', bear_acc, bear_f1, bear_prec, bear_recall)}")
    lines.append("")

    lines.append("### 6.2 交易策略框架")
    lines.append("")
    lines.append("```")
    lines.append("每周预测流程:")
    lines.append("1. 获取最新日线数据 → 计算特征")
    lines.append("2. Bull 模型预测 P(大涨)")
    lines.append("3. Bear 模型预测 P(大跌)")
    lines.append("4. 综合信号判断:")
    lines.append("   - 📈 强多头 (Bull=1, Bear=0): 加仓/做多")
    lines.append("   - 📉 强空头 (Bull=0, Bear=1): 减仓/做空")
    lines.append("   - ⏸️ 震荡   (Bull=0, Bear=0): 维持当前仓位")
    lines.append("   - ⚠️ 高波动 (Bull=1, Bear=1): 降低杠杆/对冲")
    lines.append("```")
    lines.append("")

    # =============== 实验信息 ===============
    lines.append("## 7. 实验信息")
    lines.append("")
    lines.append(f"| 项目 | 🐂 Bull | 🐻 Bear |")
    lines.append(f"|------|---------|---------|")
    lines.append(f"| 实验 ID | `{bull_artifacts['meta']['experiment_id']}` | `{bear_artifacts['meta']['experiment_id']}` |")
    lines.append(f"| 耗时 | {bull_artifacts['meta'].get('duration_seconds', 'N/A')}s | {bear_artifacts['meta'].get('duration_seconds', 'N/A')}s |")
    lines.append(f"| OOS 样本数 | {len(bull_preds)} | {len(bear_preds)} |")
    lines.append(f"| Fold 数 | {len(bull_folds)} | {len(bear_folds)} |")
    lines.append("")

    # =============== 下一步 ===============
    lines.append("## 8. 改进方向")
    lines.append("")

    T_val = bull_config.get("label", {}).get("T", 28)
    X_val = bull_config.get("label", {}).get("X", 0.05)

    lines.append(f"### 当前参数: T={T_val}, X={X_val*100:.0f}%")
    lines.append("")

    if bull_kappa < 0.2 or bear_kappa < 0.2:
        lines.append("⚠️ **Kappa 极低，模型判别力不足，需优先解决以下问题:**")
        lines.append("")
    
    lines.append("1. **类别不平衡处理**: 使用 scale_pos_weight / SMOTE / 过采样")
    
    if T_val >= 21:
        lines.append(f"2. **缩短预测窗口**: 当前 T={T_val}天，建议尝试 T=7/14 (更短窗口更可预测)")
    else:
        lines.append(f"2. **窗口微调**: 当前 T={T_val}天，可尝试 T±7")
    
    if X_val >= 0.05:
        lines.append(f"3. **降低阈值**: 当前 X={X_val*100:.0f}%，建议 X=3% (增加正例样本)")
    else:
        lines.append(f"3. **阈值微调**: 当前 X={X_val*100:.0f}%，可尝试 X={X_val*100-1:.0f}%~{X_val*100+2:.0f}%")
    
    lines.append("4. **特征精选**: 基于上述重要性分析，保留 Top-20~30 特征，减少噪声")
    lines.append("5. **概率校准**: 输出概率而非硬分类，实现仓位管理")
    lines.append("6. **集成策略**: 添加 XGBoost/CatBoost 做 ensemble")
    lines.append("7. **增强正则化**: 增大 reg_alpha/reg_lambda, 减小 num_leaves/max_depth")
    lines.append("")

    report = "\n".join(lines)

    # 写入文件
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    logger.info(f"合并报告已生成: {output_path}")

    return report


def main():
    parser = argparse.ArgumentParser(description="周预测联合实验 — Bull & Bear 双模型")
    parser.add_argument("--bull-config", default=DEFAULT_BULL_CONFIG,
                        help="Bull 模型配置文件")
    parser.add_argument("--bear-config", default=DEFAULT_BEAR_CONFIG,
                        help="Bear 模型配置文件")
    parser.add_argument("--output", default="reports/weekly_prediction_report.md",
                        help="合并报告输出路径")
    parser.add_argument("--version", default="v1", choices=["v1", "v2"],
                        help="使用 v1(原版) 或 v2(优化版) 配置")
    parser.add_argument("--log-level", default="INFO", help="日志级别")
    args = parser.parse_args()

    # 如果指定 v2，自动使用优化版配置
    if args.version == "v2":
        if args.bull_config == DEFAULT_BULL_CONFIG:
            args.bull_config = "configs/experiments/weekly/exp_weekly_bull_v2.yaml"
        if args.bear_config == DEFAULT_BEAR_CONFIG:
            args.bear_config = "configs/experiments/weekly/exp_weekly_bear_v2.yaml"
        if args.output == "reports/weekly_prediction_report.md":
            args.output = "reports/weekly_prediction_report_v2.md"

    setup_logging(level=args.log_level)

    print("=" * 70)
    print("🐂🐻 周预测联合实验 — Bull & Bear 双模型")
    print("=" * 70)

    # ========== 1. 运行 Bull 模型 ==========
    print("\n📌 Phase 1: 训练 Bull 模型（预测大涨）...")
    print("-" * 50)
    t0 = time.time()
    bull_id = run_experiment(config_path=args.bull_config)
    print(f"✅ Bull 模型完成: {bull_id} ({time.time()-t0:.1f}s)")

    # ========== 2. 运行 Bear 模型 ==========
    print("\n📌 Phase 2: 训练 Bear 模型（预测大跌）...")
    print("-" * 50)
    t0 = time.time()
    bear_id = run_experiment(config_path=args.bear_config)
    print(f"✅ Bear 模型完成: {bear_id} ({time.time()-t0:.1f}s)")

    # ========== 3. 加载产物 ==========
    print("\n📌 Phase 3: 生成合并报告...")
    print("-" * 50)

    bull_artifacts = load_experiment_artifacts(bull_id)
    bear_artifacts = load_experiment_artifacts(bear_id)

    # ========== 4. 构建信号矩阵 ==========
    signal_df = build_signal_matrix(
        bull_artifacts["predictions"],
        bear_artifacts["predictions"],
    )

    # ========== 5. 生成合并报告 ==========
    output_path = Path(args.output)
    report = generate_combined_report(
        bull_artifacts=bull_artifacts,
        bear_artifacts=bear_artifacts,
        signal_df=signal_df,
        output_path=output_path,
    )

    print(f"\n{'=' * 70}")
    print(f"🎉 周预测联合实验完成！")
    print(f"{'=' * 70}")
    print(f"📋 Bull 实验 ID: {bull_id}")
    print(f"📋 Bear 实验 ID: {bear_id}")
    print(f"📊 合并报告: {output_path}")
    print(f"\n📈 Bull 核心指标: {bull_artifacts['metrics']}")
    print(f"📉 Bear 核心指标: {bear_artifacts['metrics']}")

    # 信号分布快速概览
    print(f"\n📊 信号分布:")
    for sig, cnt in signal_df["signal"].value_counts().items():
        pct = cnt / len(signal_df) * 100
        print(f"   {sig}: {cnt} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
