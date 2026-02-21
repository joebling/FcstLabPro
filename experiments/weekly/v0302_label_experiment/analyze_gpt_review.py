#!/usr/bin/env python3
"""分析 GPT review 的关键点."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import json
import yaml
from src.labels.registry import get_label_strategy
from src.data.loader import load_csv
from src.features.builder import build_features

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

print("=" * 60)
print("分析 GPT review 的关键点")
print("=" * 60)

DATA_PATH = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"
BASE_CONFIG_PATH = PROJECT_ROOT / "configs" / "experiments" / "weekly" / "exp_weekly_bull_v27_orion_v4_extended_oos.yaml"

with open(BASE_CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)

print("\n1. 加载数据...")
df = load_csv(str(DATA_PATH))
df = build_features(
    df,
    feature_sets=config['features']['sets'],
    drop_na_method=config['features'].get('drop_na_method', 'ffill_then_drop'),
)

print("\n2. 生成 dip_recovery label 并检查样本分布...")
label_func = get_label_strategy("dip_recovery")
labels = label_func(df, T=21, dip_threshold=0.05, recovery_threshold=0.03)
valid_labels = labels.dropna()

total = len(valid_labels)
pos_count = valid_labels.sum()
neg_count = total - pos_count
pos_rate = pos_count / total
neg_rate = neg_count / total

print(f"   总样本数: {total}")
print(f"   正样本: {pos_count} ({pos_rate:.1%})")
print(f"   负样本: {neg_count} ({neg_rate:.1%})")
print(f"   Baseline Accuracy (猜全部负): {neg_rate:.1%}")

print("\n3. 分析 fold metrics...")
fold_df = pd.read_csv(PROJECT_ROOT / "experiments/weekly/weekly_bull_v0302_dip_recovery/fold_metrics.csv")

print(f"   Fold 数: {len(fold_df)}")
print(f"   平均 Kappa: {fold_df['kappa'].mean():.4f}")
print(f"   整体 Kappa: 0.5082 (从报告)")
print(f"   平均 Accuracy: {fold_df['accuracy'].mean():.4f}")

print("\n   Kappa 分布:")
print(f"     最小值: {fold_df['kappa'].min():.4f}")
print(f"     25% 分位: {fold_df['kappa'].quantile(0.25):.4f}")
print(f"     中位数: {fold_df['kappa'].median():.4f}")
print(f"     75% 分位: {fold_df['kappa'].quantile(0.75):.4f}")
print(f"     最大值: {fold_df['kappa'].max():.4f}")
print(f"     正 Kappa 比例: {(fold_df['kappa'] > 0).mean():.1%}")

print("\n4. 检查之前的 Sharpe 结果...")
with open(PROJECT_ROOT / "experiments/weekly/v0302_label_experiment/results.json") as f:
    results = json.load(f)

for r in results['results']:
    print(f"   {r['strategy']}:")
    print(f"     IC: {r['ic']:.4f}")
    print(f"     t-stat: {r['t_stat']:.4f}")
    print(f"     Sharpe: {r['sharpe']:.4f}")

print("\n5. 绘制 Kappa 分布图...")
fig, axes = plt.subplots(2, 1, figsize=(12, 10))

axes[0].plot(fold_df['fold'], fold_df['kappa'], marker='o', linewidth=2, markersize=4)
axes[0].axhline(y=0, color='r', linestyle='--', alpha=0.5)
axes[0].set_title('dip_recovery: Fold Kappa 随时间变化')
axes[0].set_xlabel('Fold')
axes[0].set_ylabel('Kappa')
axes[0].grid(True, alpha=0.3)

axes[1].hist(fold_df['kappa'], bins=20, alpha=0.7, edgecolor='black')
axes[1].axvline(x=fold_df['kappa'].mean(), color='r', linestyle='--', label=f'平均: {fold_df["kappa"].mean():.4f}')
axes[1].axvline(x=0.5082, color='g', linestyle='--', label=f'整体: 0.5082')
axes[1].set_title('dip_recovery: Kappa 分布直方图')
axes[1].set_xlabel('Kappa')
axes[1].set_ylabel('频数')
axes[1].legend()
axes[1].grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(PROJECT_ROOT / "experiments/weekly/v0302_label_experiment/kappa_analysis.png", dpi=150, bbox_inches='tight')
print(f"   图表已保存到: kappa_analysis.png")

print("\n" + "=" * 60)
print("关键发现总结")
print("=" * 60)

print(f"\n✅ 正样本比例: {pos_rate:.1%}")
print(f"✅ Baseline Accuracy: {neg_rate:.1%}")
print(f"✅ 模型 Accuracy: {fold_df['accuracy'].mean():.1%}")
print(f"✅ 相对 Baseline 提升: {fold_df['accuracy'].mean() - neg_rate:+.1%}")

print(f"\n📊 Kappa 表现:")
print(f"   - 平均 Kappa: {fold_df['kappa'].mean():.4f}")
print(f"   - 整体 Kappa: 0.5082")
print(f"   - 正 Kappa 比例: {(fold_df['kappa'] > 0).mean():.1%}")

print(f"\n⚠️  Sharpe 表现 (来自 run_label_comparison.py):")
print(f"   - dip_recovery Sharpe: {results['results'][2]['sharpe']:.4f}")
print(f"   - excess_return Sharpe: {results['results'][1]['sharpe']:.4f}")
print(f"   - simple_return Sharpe: {results['results'][0]['sharpe']:.4f}")

print("\n" + "=" * 60)
