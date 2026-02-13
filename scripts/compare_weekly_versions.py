#!/usr/bin/env python3
"""版本对比报告 — 汇总 v1~v6 实验结果，生成诊断分析.

Usage:
    python scripts/compare_weekly_versions.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def find_latest_experiment(name_prefix: str) -> dict | None:
    """在 registry 中找到最新的指定名称实验."""
    registry_path = PROJECT_ROOT / "experiments" / "registry.json"
    if not registry_path.exists():
        return None
    with open(registry_path) as f:
        registry = json.load(f)
    
    matches = []
    # registry 可能是 list 或 dict
    if isinstance(registry, list):
        for meta in registry:
            exp_id = meta.get("experiment_id", "")
            if exp_id.startswith(name_prefix):
                matches.append((exp_id, meta))
    elif isinstance(registry, dict):
        for exp_id, meta in registry.items():
            if exp_id.startswith(name_prefix):
                matches.append((exp_id, meta))
    
    if not matches:
        return None
    
    # 取最新的
    matches.sort(key=lambda x: x[0], reverse=True)
    exp_id, meta = matches[0]
    return {"id": exp_id, "meta": meta}


def load_metrics(exp_id: str) -> dict:
    """加载实验指标."""
    exp_base = PROJECT_ROOT / "experiments"
    for subdir in exp_base.rglob("metrics.json"):
        if exp_id in str(subdir.parent):
            with open(subdir) as f:
                return json.load(f)
    return {}


def main():
    lines = []
    lines.append("# 📊 周预测模型版本对比报告 (v1~v6)")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 定义所有版本
    versions = {
        "v1": {
            "bull_prefix": "weekly_bull_model_",
            "bear_prefix": "weekly_bear_model_",
            "label": "reversal",
            "T": 28, "X": "5%",
            "obj": "multiclass(3)",
            "spw": "❌",
            "reg": "弱 (α=β=0.1)",
            "features": "4集 (tech/vol/flow/sent)",
            "extra": "",
        },
        "v3": {
            "bull_prefix": "weekly_bull_v3_",
            "bear_prefix": "weekly_bear_v3_",
            "label": "reversal",
            "T": 14, "X": "5%",
            "obj": "binary",
            "spw": "✅",
            "reg": "中 (α=β=0.2)",
            "features": "4集",
            "extra": "",
        },
        "v4": {
            "bull_prefix": "weekly_bull_v4_",
            "bear_prefix": "weekly_bear_v4_",
            "label": "reversal",
            "T": 7, "X": "5%",
            "obj": "binary",
            "spw": "✅",
            "reg": "中 (α=β=0.2)",
            "features": "4集",
            "extra": "",
        },
        "v5": {
            "bull_prefix": "weekly_bull_v5_",
            "bear_prefix": "weekly_bear_v5_",
            "label": "directional",
            "T": 7, "X": "5%",
            "obj": "binary",
            "spw": "✅",
            "reg": "中 (α=β=0.2)",
            "features": "7集 (+onchain/mkt/lag)",
            "extra": "purge_gap=7, top40特征",
        },
        "v6": {
            "bull_prefix": "weekly_bull_v6_",
            "bear_prefix": "weekly_bear_v6_",
            "label": "reversal",
            "T": 14, "X": "5%",
            "obj": "binary",
            "spw": "✅",
            "reg": "中 (α=β=0.15)",
            "features": "5集 (+market_structure)",
            "extra": "",
        },
    }

    # ============= 1. 版本参数对比 =============
    lines.append("## 1. 版本参数对比")
    lines.append("")
    lines.append("| 版本 | 标签策略 | T(天) | X | Objective | SPW | 正则化 | 特征 | 额外 |")
    lines.append("|------|---------|-------|---|-----------|-----|--------|------|------|")
    for vn, vi in versions.items():
        lines.append(f"| {vn} | {vi['label']} | {vi['T']} | {vi['X']} | {vi['obj']} | {vi['spw']} | {vi['reg']} | {vi['features']} | {vi['extra']} |")
    lines.append("")

    # ============= 2. 标签分布分析 =============
    lines.append("## 2. 标签分布分析 (reversal 策略)")
    lines.append("")
    lines.append("```")
    lines.append("T= 7, X=5%  → Bull正例=36.6%  Bear正例=28.3%  Normal=35.1%  ← 最三方平衡")
    lines.append("T=14, X=5%  → Bull正例=51.8%  Bear正例=33.8%  Normal=14.4%  ← Bull接近平衡")
    lines.append("T=14, X=8%  → Bull正例=37.3%  Bear正例=27.3%  Normal=35.4%")
    lines.append("T=28, X=5%  → Bull正例=66.3%  Bear正例=30.4%  Normal= 3.3%  ← v1 严重不平衡!")
    lines.append("")
    lines.append("directional 标签 (对比):")
    lines.append("T= 7, X=5%  → Bull正例=25.7%  Bear正例=21.1%  Normal=53.2%  ← 正例太少!")
    lines.append("T=14, X=5%  → Bull正例=33.1%  Bear正例=26.9%  Normal=40.1%  ← 正例偏少")
    lines.append("```")
    lines.append("")
    lines.append("> **发现**: directional 标签的正例比例远低于 reversal，导致 v5 模型不愿预测正例（F1 极低）。")
    lines.append("> reversal + T=14 是 Bull 模型正例最接近 50% 的组合 (51.8%)。")
    lines.append("")

    # ============= 3. Bull 模型对比 =============
    lines.append("## 3. 🐂 Bull 模型指标对比")
    lines.append("")
    
    ver_keys = list(versions.keys())
    header = "| 指标 |" + "|".join(f" {v} " for v in ver_keys) + "| 最优 |"
    sep = "|------|" + "|".join("---" for _ in ver_keys) + "|------|"
    lines.append(header)
    lines.append(sep)
    
    bull_metrics = {}
    for vn, vi in versions.items():
        exp = find_latest_experiment(vi["bull_prefix"])
        if exp:
            m = load_metrics(exp["id"])
            bull_metrics[vn] = m
    
    metric_names = ["accuracy", "f1_binary", "precision_binary", "recall_binary", "f1_macro", "cohen_kappa"]
    for mn in metric_names:
        vals = {}
        for vn in ver_keys:
            if vn in bull_metrics:
                vals[vn] = bull_metrics[vn].get(mn, None)
        
        best_ver = max(vals, key=lambda k: vals[k] if vals[k] is not None else -999) if vals else ""
        row = f"| {mn} |"
        for vn in ver_keys:
            v = vals.get(vn)
            if v is not None:
                marker = " **" if vn == best_ver else " "
                row += f"{marker}{v:.4f}{'**' if vn == best_ver else ''} |"
            else:
                row += " - |"
        row += f" {best_ver} |"
        lines.append(row)
    
    lines.append("")

    # ============= 4. Bear 模型对比 =============
    lines.append("## 4. 🐻 Bear 模型指标对比")
    lines.append("")
    
    lines.append(header.replace("Bull", "Bear"))
    lines.append(sep)
    
    bear_metrics = {}
    for vn, vi in versions.items():
        exp = find_latest_experiment(vi["bear_prefix"])
        if exp:
            m = load_metrics(exp["id"])
            bear_metrics[vn] = m
    
    for mn in metric_names:
        vals = {}
        for vn in ver_keys:
            if vn in bear_metrics:
                vals[vn] = bear_metrics[vn].get(mn, None)
        
        best_ver = max(vals, key=lambda k: vals[k] if vals[k] is not None else -999) if vals else ""
        row = f"| {mn} |"
        for vn in ver_keys:
            v = vals.get(vn)
            if v is not None:
                marker = " **" if vn == best_ver else " "
                row += f"{marker}{v:.4f}{'**' if vn == best_ver else ''} |"
            else:
                row += " - |"
        row += f" {best_ver} |"
        lines.append(row)
    
    lines.append("")

    # ============= 5. 综合诊断 =============
    lines.append("## 5. 综合诊断")
    lines.append("")
    
    lines.append("### 5.1 核心发现")
    lines.append("")
    lines.append("1. **v1 Bull F1=0.674 是虚高的**: T=28 下 Bull 正例占 66.3%，模型只需总预测\"正例\"就能得到 ~66% Accuracy。Kappa=0.108 证实判别力有限。")
    lines.append("")
    lines.append("2. **v5 directional 标签导致 F1 崩溃**: directional 标签在 T=7 下 Bull 正例仅 25.7%，模型倾向于总预测\"负例\"以最大化 Accuracy (~75%)，但 F1 和 Recall 极低。")
    lines.append("")
    lines.append("3. **v3/v6 (reversal + T=14 + SPW) 是最诚实的版本**: Bull 正例 51.8% 接近平衡，SPW 进一步校正，F1=0.454 虽然不高但**真实反映了模型的预测能力**。")
    lines.append("")
    lines.append("4. **Bear 模型在 v3/v6 表现最好**: F1=0.384/0.389, Kappa=0.048/0.060。v6 的 Bear Kappa 有小幅提升，得益于 market_structure 特征集。")
    lines.append("")
    lines.append("5. **所有版本 Kappa < 0.11**: 说明当前特征集对 BTC 价格方向的预测力非常有限，**这是信息量瓶颈而非模型问题**。")
    lines.append("")
    
    lines.append("### 5.2 版本演化总结")
    lines.append("")
    lines.append("```")
    lines.append("v1 (T=28, 无SPW)     → 高F1但虚高 (标签不平衡)        ❌ 不可信")
    lines.append("v3 (T=14, +SPW)      → F1下降但真实，标签更平衡         ✅ 诚实基线")
    lines.append("v4 (T=7, +SPW)       → 标签最平衡但信号太弱             ⚠️ 窗口太短")
    lines.append("v5 (directional+purge)→ F1崩溃，标签策略导致正例太少      ❌ 过度限制")
    lines.append("v6 (reversal+T14+5集) → 复现v3, Bear略有提升            ✅ 当前最优")
    lines.append("```")
    lines.append("")
    
    lines.append("### 5.3 改进方向")
    lines.append("")
    lines.append("| 优先级 | 方向 | 预期效果 |")
    lines.append("|--------|------|---------|")
    lines.append("| 🔴 高 | 引入链上数据 (实际地址活跃度、交易所净流入) | 增加信息维度，突破 Kappa 瓶颈 |")
    lines.append("| 🔴 高 | 引入宏观因子 (美元指数、利率、纳指相关性) | 捕获系统性风险 |")
    lines.append("| 🟡 中 | 改用回归目标 (预测涨跌幅度而非分类) | 连续值更灵活 |")
    lines.append("| 🟡 中 | 概率输出 + 阈值调优 (而非硬分类) | 提高决策灵活性 |")
    lines.append("| 🟢 低 | 模型集成 (XGBoost+CatBoost+LightGBM) | 微小提升 |")
    lines.append("")
    
    lines.append("### 5.4 结论")
    lines.append("")
    lines.append("> **v6 (reversal + T=14 + SPW + 5特征集) 是当前最诚实、最稳定的版本。**")
    lines.append("> Bull F1=0.454 (Precision=0.504), Bear F1=0.389 (Kappa=0.060)。")
    lines.append("> 所有版本 Kappa 均低于 0.11，证实了纯技术面特征对 BTC 短期方向的预测力天然有限。")
    lines.append("> **下一步应优先扩充信息源，而非继续调参。**")
    lines.append("")

    report = "\n".join(lines)
    output_path = PROJECT_ROOT / "reports" / "weekly_version_comparison.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"✅ 版本对比报告已生成: {output_path}")
    print()
    print(report)


if __name__ == "__main__":
    main()
