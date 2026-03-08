# v0305 Fold Regime 分析报告

## 概述

对每个实验的 fold 按市场 regime（bull/bear/sideways）分组，
分析模型在不同环境下的表现。

---

## weekly_bear_v0305_E5_low_threshold

### Regime 统计

| regime   |   fold_count |   kappa_mean |   kappa_std |   f1_mean |   f1_gt0_ratio |
|:---------|-------------:|-------------:|------------:|----------:|---------------:|
| bear     |           15 |        0.169 |       0.232 |     0.206 |          0.6   |
| bull     |           23 |        0.371 |       0.337 |     0.391 |          0.652 |
| sideways |           18 |        0.228 |       0.305 |     0.271 |          0.5   |

### F1=0 的 fold 分布 (23个)

| regime   |   count |
|:---------|--------:|
| sideways |       9 |
| bull     |       8 |
| bear     |       6 |

---

## weekly_bear_v0305_E6_no_ma_filter

### Regime 统计

| regime   |   fold_count |   kappa_mean |   kappa_std |   f1_mean |   f1_gt0_ratio |
|:---------|-------------:|-------------:|------------:|----------:|---------------:|
| bear     |           15 |        0.076 |       0.146 |     0.134 |          0.6   |
| bull     |           23 |        0.34  |       0.293 |     0.413 |          0.652 |
| sideways |           18 |        0.237 |       0.269 |     0.302 |          0.667 |

### F1=0 的 fold 分布 (20个)

| regime   |   count |
|:---------|--------:|
| bull     |       8 |
| bear     |       6 |
| sideways |       6 |
