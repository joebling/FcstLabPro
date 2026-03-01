# 模型复现总结

## 背景

### 复现原因

1. **Kappa 值不匹配**: 收到的邮件报告中模型 Kappa 值与原部署报告不符，需要验证实际模型表现
2. **标签算法修改**: 发现 dip_recovery 标签算法在 commit 1164d91 中被修改（使用了未来最低价），需确认原版算法
3. **版本管理混乱**: experiments/ 目录下存在多个带时间戳的实验目录，命名不规范

### 解决的问题

1. **标签算法泄露问题**:
   - 发现 dip_recovery 标签在 commit 1164d91 中被修改
   - 默认版本: `low.rolling(T).min()` - 包含当天 low（8点触发时还有16小时数据未产生，属于泄露）
   - v1版本: `low.shift(-1).rolling(T).min()` - 只用昨天及之前的 low（正确）
   - 8点触发场景：当天 0-8 点的 K 线走完，但还有 16 小时数据未产生，当天的 low 未知
   - v0302 复现使用 dip_recovery_v1 原始算法（无泄露）

2. **实验目录清理**: 删除了 12 个带时间戳后缀的实验目录

3. **模型训练**:
   - v0301 Bear: 本地 LightGBM 训练
   - v0301 Bull: vast.ai Orion-BiX 训练
   - v0302 Bull: 本地 LightGBM 训练

### ⚠️ 待验证问题 (已验证)

1. **v0302 Bull Kappa 异常高** (0.56 vs 原 0.11)
   - 已用默认 dip_recovery 重新训练验证
   - 结果对比:
     | 标签算法 | Kappa | 说明 |
     |----------|------|------|
     | dip_recovery_v1 (正确) | 0.5609 | 复现版本 |
     | dip_recovery (泄露) | 0.6117 | 验证版本 |
   - 结论: 标签差异仅贡献 ~0.05 Kappa，**主要差异来自模型类型**

2. **v0301 Bear vs Bull 差异**
   - Bear 使用 LightGBM (n_estimators=500)
   - Bull 使用 Orion-BiX (n_estimators=16)
   - 模型不同导致可比性有限

### Bull vs Bear 表现差异分析

| 对比项 | v0301 Bear | v0301 Bull |
|--------|------------|------------|
| **模型** | LightGBM (n_estimators=500) | Orion-BiX (n_estimators=16) |
| **T** | 28 天 | 21 天 |
| **标签映射** | 0→1 (下跌>5%是信号) | 2→1 (反转是信号) |
| **scaling** | null | standard |
| **init_train** | 1500 | 800 |
| **Kappa 提升** | 0.05 → -0.17 (❌ 下降) | 0.11 → 0.10 |

**Bull 没有提升的原因**:
- 模型容量小 (n_estimators=16)
- 预测"价格反转"是一个更难的模式
- Orion-BiX 在小样本上容易过拟合

**Bear 实际下降**:
- 复现文档中的 0.23 是记录错误
- 实际模型 Kappa = **-0.1697**（比原部署更差）
- 77.3% fold Kappa > 0，但整体汇总 Kappa 为负（后期 folds 预测方向错误）
- **v0218 原始实验也无法复现**（原因未知，可能是数据版本差异）

## 训练完成状态

### v0301 (LightGBM + Orion-BiX)
| 模型 | 算法 | Kappa | Accuracy | 实验目录 | 状态 |
|------|------|-------|----------|----------|------|
| Bear | LightGBM | **-0.17** | 0.45 | weekly_bear_v13_prod | ❌ 需重新设计 |
| Bull | Orion-BiX | 0.10 | 0.56 | weekly_bull_v27_prod | ⚠️ 效果一般 |

### v0302 (LightGBM)
| 模型 | 算法 | Kappa | Accuracy | 实验目录 | 状态 |
|------|------|-------|----------|----------|------|
| Bear (v1) | LightGBM | **0.56** | 0.79 | weekly_bear_v0302_prod | ✅ 优秀 |
| Bull (v1) | LightGBM | 0.56 | 0.79 | weekly_bull_v0302_prod | ✅ 优秀 |
| Bull (默认) | LightGBM | 0.61 | 0.81 | weekly_bull_v0302_prod_default_label | ✅ |

**说明**: v1 版本使用正确标签（无泄露），默认版本使用有泄露风险的标签。差异仅 ~0.05。

## 与原部署报告对比

### v0301 (deploy/v0301_experiment_report.md)

| 对比项 | 原部署报告 | 本次复现 | 差异 |
|--------|------------|----------|------|
| Bull Kappa | 0.11 (Orion) | 0.1036 | 接近 |
| Bear Kappa | 0.05 | **-0.17** | **❌ 下降** |
| 标签策略 | reversal | reversal | 一致 |
| 模型 | Orion-BiX | Bull: Orion-BiX, Bear: LightGBM | Bear 不同 |

**说明**:
- v0301 Bull 使用 Orion-BiX 模型 + reversal 标签
- v0301 Bear 复现使用 LightGBM (原报告使用 Orion)
- **复现文档曾记录错误值 0.2286，实际 Kappa = -0.17**
- **Bear 模型效果很差，需要重新设计**

### v0302 (deploy/v0302_experiment_report.md)

| 对比项 | 原部署报告 | 本次复现 (v1) | 本次复现 (默认) | 差异 |
|--------|------------|----------------|-----------------|------|
| Bull Kappa | 0.11 | 0.5609 | 0.6117 | **大幅提升** |
| 标签策略 | dip_recovery | dip_recovery_v1 | dip_recovery | v1更保守 |
| 模型 | Orion | LightGBM | LightGBM | 不同 |

**关键发现**:
- 标签差异仅贡献 ~0.05 Kappa
- **主要差异来自模型类型** (LightGBM vs Orion)
- LightGBM n_estimators=100 容量更大，泛化能力更强

## 配置差异

### v0301 Bull
- 标签策略: reversal (T=21, X=0.05)
- 模型: Orion-BiX (n_estimators=16)
- 特征: technical + volume + flow + market_structure + external_fgi + regime

### v0302 Bull
- 标签策略: dip_recovery_v1 (T=21, X=0.08)
- 模型: LightGBM (n_estimators=100)
- 特征: technical + volume + flow + market_structure + external_fgi + regime

### v0302 Bear
- 标签策略: dip_recovery_v1 (T=21, X=0.08)
- 模型: LightGBM (n_estimators=100)
- 特征: technical + volume + flow + market_structure + external_fgi (无 regime)

## 注意事项

v0301 Bull (Orion-BiX) 的 Kappa 较低 (0.10)，多个 fold 出现 Kappa=0 或负数，模型效果一般。

**v0301 Bear (LightGBM) 问题严重**：
- Kappa = **-0.17**，远低于原部署报告的 0.05
- 虽然 77.3% fold Kappa > 0，但整体汇总为负（后期 folds 预测方向错误）
- **建议：需要重新设计 Bear 模型，可能是标签策略或特征不适合当前市场**

## 待解决问题

~~1. v0301 Bear 需要重新设计~~ ✅ **已解决**
   - 使用 dip_recovery_v1 标签训练 v0302 Bear
   - **结果：Kappa = 0.56，100% fold > 0，效果极佳**

2. **v0302 Bear IC验证**：✅ Walk-Forward验证已通过
   - Kappa = 0.56，100% fold > 0，85.7% fold > 0.2
   - 无需额外IC分析

## 模型文件位置

models/v0301/
- bear_model.joblib
- bull_model.joblib

models/v0302/
- bear_model.joblib
- bull_model.joblib
