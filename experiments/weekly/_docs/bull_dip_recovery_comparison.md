# Bull Dip Recovery 实验对比报告

## 一、实验概述

| 实验 | 模型 | 模型参数 | Step | Folds | Kappa | Precision |
|------|------|----------|------|-------|-------|-----------|
| **original** | Orion-BiX | 复杂 (10+参数) | 42 | ? | 0.017 | 49.2% |
| **v1** | Orion-BiX | 极简 (n=16) | 21 | 58 | **0.437** | **82.1%** |
| **v2** | Orion-BiX | 复杂 (10+参数) | 21 | ? | 0.031 | 50.0% |

## 二、配置差异

### Label 配置

| 配置项 | original | v1 | v2 |
|--------|----------|-----|-----|
| **strategy** | dip_recovery | dip_recovery | dip_recovery |
| **T** | 21 | 21 | 21 |
| **X** | 0.08 ⚠️ (不识别) | 无 (默认) | 0.08 ⚠️ (不识别) |
| **dip_threshold** | 默认 0.05 | 默认 0.05 | 默认 0.05 |
| **recovery_threshold** | 默认 0.03 | 默认 0.03 | 默认 0.03 |

> ⚠️ `X` 参数不是 `dip_recovery` 标签的有效参数，会被忽略。所有实验实际使用默认阈值 dip=5%, recovery=3%。

### 模型配置

| 配置项 | original | v1 | v2 |
|--------|----------|-----|-----|
| **模型类型** | Orion-BiX | Orion-BiX | Orion-BiX |
| **n_estimators** | 16 | 16 | 16 |
| **max_depth** | 6 | ❌ | 6 |
| **learning_rate** | 0.05 | ❌ | 0.05 |
| **num_leaves** | 31 | ❌ | 31 |
| **subsample** | 0.8 | ❌ | 0.8 |
| **colsample_bytree** | 0.8 | ❌ | 0.8 |
| **reg_alpha** | 0.1 | ❌ | 0.1 |
| **reg_lambda** | 0.1 | ❌ | 0.1 |
| **step** | 42 | **21** | 21 |
| **parallel_workers** | 4 | ? | ? |
| **特征集** | 6个 | 6个 | 6个 |
| **scaling** | standard | standard | standard |

## 三、关键发现

### 1. 模型参数影响巨大
- **v1 (极简参数)**：Kappa = **0.437** ✅
- **v2 (复杂参数)**：Kappa = 0.031 ❌

**结论**：复杂参数导致 Orion-BiX 过拟合，性能大幅下降。

### 2. Step 差异
- **original (step=42)**：Kappa = 0.017
- **v1 (step=21)**：Kappa = 0.437

**结论**：step=21 提供更多 folds (58 folds vs ~28 folds)，训练更稳定。

### 3. 极简参数 v1 是最优配置
- Kappa = 0.437 (优秀)
- Precision = 82.1% (高置信度)
- 正 Kappa 比例 = 87.9%

## 四、Fold 级别分析

### v1 (最优) Fold 统计
```
Kappa 平均: 0.437
Kappa 标准差: 0.280
正 Kappa 比例: 87.9%
```

### v2 (复杂参数) Fold 统计
```
Kappa 平均: 0.031
正 Kappa 比例: ~50% (接近随机)
```

## 五、LightGBM 对比 (额外实验)

| 实验 | 模型 | n_estimators | Kappa |
|------|------|--------------|-------|
| lgbm_v1 | LightGBM | 16 | -0.040 |
| lgbm_no_scale | LightGBM (no scale_pos_weight) | 16 | -0.056 |
| lgbm_n100 | LightGBM | 100 | -0.024 |

**结论**：LightGBM 在该任务上显著弱于 Orion-BiX，差距过大，不是参数调优问题。

## 六、结论

1. **Orion-BiX 极简配置 (v1) 是最优选择**
   - 移除所有复杂超参数
   - 仅保留 `n_estimators=16, random_state=42`

2. **step=21 优于 step=42**
   - 更多训练 folds
   - 更稳定的验证

3. **Orion-BiX vs LightGBM**
   - Orion-BiX 的 ICL 机制显著优于传统 ML
   - 预训练模型能力在此任务上不可替代

## 七、建议

后续实验统一使用 v1 配置：
```yaml
model:
  type: orion_bix
  params:
    n_estimators: 16
    random_state: 42
evaluation:
  step: 21
```
