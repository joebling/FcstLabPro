# v0303 Bear 实验计划

**目标**: 定位 Bear 模型失效的根因，找到可用的 Bear 信号配置。

**方法论**: 先全对齐 Bull 成功配置 → 再逐项消融（ablation）→ 定位关键因子。

## 〇、当前状态

| 维度 | 🐂 Bull Dip Recovery (Kappa=0.44) | 🐻 Bear Dip Recovery (Kappa=-0.07) |
|------|-----------------------------------|-------------------------------------|
| 特征集 | technical, volume, flow, market_structure, external_fgi, **regime** | technical, volume, flow, market_structure, external_fgi |
| Scaling | **standard** | null |
| 模型参数 | **极简** (n_estimators=16, random_state=42) | 复杂 (10个参数) |
| T 窗口 | **21** | 28 |
| Label 阈值 | 默认 (dip=5%, recovery=3%) | dip=8%, recovery=5% |
| Step | **21** (58 folds) | 42 (28 folds) |

共 **5 个差异维度**，需要控制变量逐一验证。

---

## 一、Phase 1 — 全对齐基线（最高优先级）

> 核心问题：Bear 模型是不是 **根本不可学**？还是配置没调对？

### Exp A: `weekly_bear_v0303_dip_recovery_aligned`

**变更**: 将 Bear dip_recovery 的所有配置对齐 Bull。

```yaml
features:
  sets: [technical, volume, flow, market_structure, external_fgi, regime]  # +regime
  scaling: standard      # null → standard
label:
  strategy: dip_recovery
  T: 21                  # 28 → 21
  # 使用默认阈值 dip=5%, recovery=3%，与 Bull 对齐
model:
  type: orion_bix
  params:
    n_estimators: 16     # 移除所有复杂参数
    random_state: 42
evaluation:
  step: 21               # 42 → 21
```

**预期**:
- 如果 Kappa > 0.3 → Bear 可学，之前是配置问题
- 如果 Kappa ≈ 0  → Bear 本身就更难，需要更深的特征工程

**预计耗时**: ~10h（参考 Bull 的 38371s）

---

### Exp B: `weekly_bear_v0303_pump_dump_aligned`

**变更**: Pump dump 也全对齐 Bull 的基础设施配置。

```yaml
features:
  sets: [technical, volume, flow, market_structure, external_fgi, regime]
  scaling: standard
label:
  strategy: pump_dump
  T: 21
  # 使用默认阈值 pump=5%, dump=3%
model:
  type: orion_bix
  params:
    n_estimators: 16
    random_state: 42
evaluation:
  step: 21
```

**预期**: 验证 pump_dump 这个 label 策略在最优基础设施下能否学到信号。

**预计耗时**: ~10h

---

## 二、Phase 2 — 消融实验（中优先级）

> 仅在 Phase 1 的 Exp A Kappa > 0.2 时才有意义。
> 目标：找到哪个变量对 Bear 影响最大。

### Exp C: `weekly_bear_v0303_dip_recovery_no_regime`

**变更**: 在 Exp A 基础上 **去掉 regime** 特征。

```yaml
features:
  sets: [technical, volume, flow, market_structure, external_fgi]  # 无 regime
  scaling: standard
label:
  strategy: dip_recovery
  T: 21
model:
  params: {n_estimators: 16, random_state: 42}
evaluation:
  step: 21
```

**验证**: regime 特征是否是 Bear 模型的关键差异。

---

### Exp D: `weekly_bear_v0303_dip_recovery_no_scaling`

**变更**: 在 Exp A 基础上 **去掉 scaling**。

```yaml
features:
  sets: [technical, volume, flow, market_structure, external_fgi, regime]
  scaling: null  # 无 scaling
label:
  strategy: dip_recovery
  T: 21
model:
  params: {n_estimators: 16, random_state: 42}
evaluation:
  step: 21
```

**验证**: standard scaling 对 Orion-BiX 是否关键。

---

### Exp E: `weekly_bear_v0303_dip_recovery_T28`

**变更**: 在 Exp A 基础上 **T 改回 28**。

```yaml
features:
  sets: [technical, volume, flow, market_structure, external_fgi, regime]
  scaling: standard
label:
  strategy: dip_recovery
  T: 28  # 保持原始 28 天窗口
model:
  params: {n_estimators: 16, random_state: 42}
evaluation:
  step: 21
```

**验证**: T=28 vs T=21 对预测质量的影响。

---

### Exp F: `weekly_bear_v0303_dip_recovery_complex_params`

**变更**: 在 Exp A 基础上 **恢复复杂模型参数**。

```yaml
features:
  sets: [technical, volume, flow, market_structure, external_fgi, regime]
  scaling: standard
label:
  strategy: dip_recovery
  T: 21
model:
  params:
    n_estimators: 16
    max_depth: 6
    learning_rate: 0.05
    num_leaves: 31
    subsample: 0.8
    colsample_bytree: 0.8
    min_child_samples: 20
    reg_alpha: 0.1
    reg_lambda: 0.1
    random_state: 42
    verbose: -1
    n_jobs: 1
evaluation:
  step: 21
```

**验证**: 复杂参数是否导致过拟合。

---

## 三、Phase 3 — 阈值消融（低优先级）

> 仅在 Phase 1 有正信号时才执行。

### Exp G: `weekly_bear_v0303_dip_recovery_threshold_8_5`

**变更**: 在 Exp A 基础上使用更高阈值。

```yaml
label:
  strategy: dip_recovery
  T: 21
  dip_threshold: 0.08
  recovery_threshold: 0.05
```

**验证**: 更严格的阈值是否能提高精度（牺牲召回）。

---

## 四、实验执行顺序

```
阶段    实验    依赖        预计耗时    可并行
─────────────────────────────────────────────────
P1      Exp A   无          ~10h       ✅ A+B 可并行
P1      Exp B   无          ~10h       ✅
─────────────────────────────────────────────────
P2      Exp C   A.kappa>0.2 ~10h       ✅ C+D+E+F 可并行
P2      Exp D   A.kappa>0.2 ~10h       ✅
P2      Exp E   A.kappa>0.2 ~10h       ✅
P2      Exp F   A.kappa>0.2 ~10h       ✅
─────────────────────────────────────────────────
P3      Exp G   A.kappa>0.2 ~10h       ✅
─────────────────────────────────────────────────
```

- **最短路径**: 如果 Exp A 失败 (kappa≈0)，只需跑 A+B（~10h 并行），就可以结论: Bear 本身不可学。
- **最长路径**: A 成功 → 跑 C/D/E/F/G（~10h 并行）→ 总计 ~20h。

## 五、成功标准

| 指标 | 最低可接受 | 目标 |
|------|-----------|------|
| Cohen's Kappa (平均) | > 0.20 | > 0.35 |
| Precision | > 0.65 | > 0.75 |
| 正 Kappa 比例 | > 70% | > 85% |
| Fold 间 Kappa 标准差 | < 0.35 | < 0.25 |

## 六、消融结果分析模板

跑完 Phase 2 后，对比表格：

| 实验 | 变量 | Kappa | Acc | F1 | Precision | vs Exp A |
|------|------|-------|-----|-----|-----------|----------|
| A (基线) | 全对齐 | ? | ? | ? | ? | — |
| C | -regime | ? | ? | ? | ? | Δkappa=? |
| D | -scaling | ? | ? | ? | ? | Δkappa=? |
| E | T=28 | ? | ? | ? | ? | Δkappa=? |
| F | +复杂参数 | ? | ? | ? | ? | Δkappa=? |
| G | +高阈值 | ? | ? | ? | ? | Δkappa=? |

Δkappa 最大的那个变量 = Bear 失效的主因。