"""
深入分析 weekly_bear_v0302_prod 实验结果
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# 加载数据
exp_dir = Path("experiments/weekly/weekly_bear_v0302_prod")
fold_metrics = pd.read_csv(exp_dir / "fold_metrics.csv")

print("=" * 80)
print("📊 FOLD 级分析")
print("=" * 80)

print(f"\n总 Fold 数: {len(fold_metrics)}")
print(f"\nKappa 统计:")
print(f"  均值: {fold_metrics['cohen_kappa'].mean():.4f}")
print(f"  中位数: {fold_metrics['cohen_kappa'].median():.4f}")
print(f"  标准差: {fold_metrics['cohen_kappa'].std():.4f}")
print(f"  最小值: {fold_metrics['cohen_kappa'].min():.4f} (Fold {fold_metrics['cohen_kappa'].idxmin()})")
print(f"  最大值: {fold_metrics['cohen_kappa'].max():.4f} (Fold {fold_metrics['cohen_kappa'].idxmax()})")

print(f"\nKappa 分布:")
print(f"  Kappa < 0: {(fold_metrics['cohen_kappa'] < 0).sum()} 个")
print(f"  0 ≤ Kappa < 0.2: {((fold_metrics['cohen_kappa'] >= 0) & (fold_metrics['cohen_kappa'] < 0.2)).sum()} 个")
print(f"  0.2 ≤ Kappa < 0.5: {((fold_metrics['cohen_kappa'] >= 0.2) & (fold_metrics['cohen_kappa'] < 0.5)).sum()} 个")
print(f"  Kappa ≥ 0.5: {(fold_metrics['cohen_kappa'] >= 0.5).sum()} 个")

print(f"\n最差的 10 个 Fold:")
worst = fold_metrics.nsmallest(10, 'cohen_kappa')
print(worst[['fold_id', 'cohen_kappa', 'accuracy', 'f1_binary', 'precision_binary', 'recall_binary']].to_string(index=False))

print(f"\n最好的 10 个 Fold:")
best = fold_metrics.nlargest(10, 'cohen_kappa')
print(best[['fold_id', 'cohen_kappa', 'accuracy', 'f1_binary', 'precision_binary', 'recall_binary']].to_string(index=False))

# 时间序列分析
print("\n" + "=" * 80)
print("📈 时间序列分析")
print("=" * 80)

# 计算滚动平均
fold_metrics['kappa_rolling_5'] = fold_metrics['cohen_kappa'].rolling(5, min_periods=1).mean()
fold_metrics['kappa_rolling_10'] = fold_metrics['cohen_kappa'].rolling(10, min_periods=1).mean()

print(f"\n前半段 (Fold 0-27) Kappa 均值: {fold_metrics.iloc[:28]['cohen_kappa'].mean():.4f}")
print(f"后半段 (Fold 28-55) Kappa 均值: {fold_metrics.iloc[28:]['cohen_kappa'].mean():.4f}")

# 检查 Precision=1.0 的情况
print(f"\nPrecision = 1.0 的 Fold 数量: {(fold_metrics['precision_binary'] >= 0.999).sum()}")
print(f"这些 Fold 的 Kappa: {fold_metrics[fold_metrics['precision_binary'] >= 0.999]['cohen_kappa'].tolist()}")

# 检查 Recall 突然变化
print(f"\nRecall < 0.4 的 Fold 数量: {(fold_metrics['recall_binary'] < 0.4).sum()}")
print(f"这些 Fold: {fold_metrics[fold_metrics['recall_binary'] < 0.4]['fold_id'].tolist()}")

print("\n" + "=" * 80)
print("⚠️  关键问题分析")
print("=" * 80)

print("""
1. **性能波动极大**:
   - Kappa 范围: 0.0187 ~ 0.9682 (标准差 0.29)
   - 前半段 vs 后半段有明显差异

2. **Precision 异常高**:
   - 多个 Fold 的 Precision = 1.0，这在实际金融预测中非常罕见
   - 这表明模型可能在"学"某种简单的模式，而非真正的预测能力

3. **Label 定义问题**:
   dip_recovery_v1 的逻辑:
   - 未来 T=21 天内最低点相对当前下跌 > 5%
   - 并且从最低点反弹 > 3%
   
   问题在于：这是一个**结果导向**的标签，而不是**预测导向**的标签。
   模型可能在学"什么时候会先跌后弹"，但这种模式在未来可能不重复。

4. **信息泄露风险**:
   虽然使用了 shift(-1)，但标签的定义本身就包含了未来信息的模式。
""")

# 生成可视化数据
print("\n" + "=" * 80)
print("📊 可视化建议")
print("=" * 80)
print("""
建议绘制以下图表：
1. Kappa 随时间的变化曲线
2. Precision/Recall 随时间的变化
3. 标签分布的时间变化
4. 特征重要性的稳定性分析
""")
