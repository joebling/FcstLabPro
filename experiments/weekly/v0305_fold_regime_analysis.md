# v0305 Fold Regime 分析报告

## 概述

对每个实验的 fold 按市场 regime（bull/bear/sideways）分组，
分析模型在不同环境下的表现。

---

## weekly_bear_v0305_E1_decontam

### Regime 统计

| regime   |   fold_count |   kappa_mean |   kappa_std |   f1_mean |   f1_gt0_ratio |
|:---------|-------------:|-------------:|------------:|----------:|---------------:|
| bear     |           15 |        0.135 |       0.264 |     0.137 |          0.267 |
| bull     |           23 |        0.388 |       0.328 |     0.394 |          0.652 |
| sideways |           18 |        0.235 |       0.308 |     0.257 |          0.556 |

### F1=0 的 fold 分布 (27个)

| regime   |   count |
|:---------|--------:|
| bear     |      11 |
| sideways |       8 |
| bull     |       8 |

---

## weekly_bear_v0305_E3_tb_grid_a

### Regime 统计

| regime   |   fold_count |   kappa_mean |   kappa_std |   f1_mean |   f1_gt0_ratio |
|:---------|-------------:|-------------:|------------:|----------:|---------------:|
| bear     |           15 |        0.018 |       0.117 |     0.407 |          0.933 |
| bull     |           23 |        0.029 |       0.071 |     0.302 |          0.739 |
| sideways |           18 |       -0.001 |       0.14  |     0.283 |          0.833 |

### F1=0 的 fold 分布 (10个)

| regime   |   count |
|:---------|--------:|
| bull     |       6 |
| sideways |       3 |
| bear     |       1 |

---

## weekly_bear_v0305_E4_tb_grid_b

### Regime 统计

| regime   |   fold_count |   kappa_mean |   kappa_std |   f1_mean |   f1_gt0_ratio |
|:---------|-------------:|-------------:|------------:|----------:|---------------:|
| bear     |           15 |        0.047 |       0.081 |     0.39  |          1     |
| bull     |           23 |        0.067 |       0.102 |     0.404 |          0.957 |
| sideways |           18 |       -0.017 |       0.116 |     0.283 |          0.889 |

### F1=0 的 fold 分布 (3个)

| regime   |   count |
|:---------|--------:|
| sideways |       2 |
| bull     |       1 |
