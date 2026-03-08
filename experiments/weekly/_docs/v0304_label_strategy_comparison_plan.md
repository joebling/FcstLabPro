# v0304 Label 策略对比实验计划

## 一、实验目标

对比 3 种新设计的 Label 策略与原 dip_recovery_v1 的表现，选出最优方案用于生产。

---

## 二、参与对比的策略

| 策略 | 文件名 | 优先级 | 预期 Kappa | 特点 |
|------|--------|--------|-----------|------|
| **基准** | dip_recovery_v1 | - | 0.56 | 当前生产版本（有问题） |
| **方案 A** | triple_barrier_simple | ⭐⭐⭐⭐⭐ | 0.30-0.45 | 推荐首选，贴近真实交易 |
| **方案 B** | dip_recovery_v2 | ⭐⭐⭐⭐ | 0.35-0.50 | 保留原框架，修复问题 |
| **方案 C** | directional_filtered | ⭐⭐⭐ | 0.25-0.40 | 简单可靠，技术过滤 |

---

## 三、实验配置（保持一致）

所有实验使用相同的基础设施配置：

```yaml
features:
  sets: [technical, volume, flow, market_structure, external_fgi]
  scaling: standard
model:
  type: lightgbm
  params: {n_estimators: 100, max_depth: 6, ...}
evaluation:
  method: walk_forward
  init_train: 800
  oos_window: 63
  step: 21
  purge_gap: 21
```

---

## 四、各策略具体配置

### 4.1 基准：dip_recovery_v1（当前生产）

```yaml
label:
  strategy: dip_recovery_v1
  T: 21
  dip_threshold: 0.05
  recovery_threshold: 0.03
```

### 4.2 方案 A：triple_barrier_simple（推荐首选）

```yaml
label:
  strategy: triple_barrier_simple
  T: 21
  pt: 0.06
  sl: 0.04
  include_today: false
```

**特点**：
- ✅ 完全符合真实交易逻辑（有止盈止损）
- ✅ 风险收益比 1.5:1（合理）
- ✅ 避免事后诸葛亮问题
- ⚠️ 正例率预计 15-25%

### 4.3 方案 B：dip_recovery_v2（改进版）

```yaml
label:
  strategy: dip_recovery_v2
  T: 21
  dip_threshold: 0.07
  recovery_threshold: 0.05
  dip_window: 10
  include_today: false
```

**改进点**：
- ✅ 用未来最高点而非 T 天后收盘价计算反弹
- ✅ 增加 dip_window（下跌必须在前 10 天内）
- ✅ 提高阈值（dip: 5%→7%, recovery: 3%→5%）
- ⚠️ 正例率预计 20-30%

### 4.4 方案 C：directional_filtered（简单可靠）

```yaml
label:
  strategy: directional_filtered
  T: 21
  X: 0.05
  rsi_window: 14
  rsi_threshold: 40.0
  ma_window: 50
  require_below_ma: true
```

**特点**：
- ✅ 简单直接，易于理解
- ✅ RSI < 40 + 价格在 SMA50 之下（技术过滤）
- ✅ 与传统技术分析结合
- ⚠️ 正例率预计 10-20%

---

## 五、评估指标

### 5.1 主要指标

| 指标 | 最低可接受 | 目标 | 说明 |
|------|-----------|------|------|
| **Cohen's Kappa (平均)** | > 0.20 | > 0.35 | 核心指标 |
| **Precision** | > 0.60 | > 0.70 | 避免误报 |
| **Recall** | > 0.30 | > 0.50 | 避免漏检 |
| **正 Kappa 比例** | > 70% | > 85% | 稳定性 |
| **Kappa 标准差** | < 0.30 | < 0.20 | 稳定性 |

### 5.2 次要指标（定性分析）

- 正例率是否合理（15-30%）
- Precision 是否异常高（避免 > 0.95）
- Fold 间性能波动
- 特征重要性的可解释性

---

## 六、实验执行顺序

```
Phase 1: 基准复现（快速验证）
├── [1] 复现 dip_recovery_v1（确认环境一致）

Phase 2: 核心对比（并行执行）
├── [2] triple_barrier_simple（方案 A，首选）
├── [3] dip_recovery_v2（方案 B）
└── [4] directional_filtered（方案 C）

Phase 3: 阈值优化（仅在 Phase 2 有正结果时）
├── [5] triple_barrier_simple 参数调优
└── [6] dip_recovery_v2 参数调优
```

**预计总耗时**：~4 小时（4 个实验并行）

---

## 七、成功标准

### 7.1 单个策略合格标准

- Kappa > 0.25
- 正 Kappa 比例 > 75%
- 正例率在 15-35% 之间
- 没有 Fold 的 Precision = 1.0（异常保守）

### 7.2 胜出策略选择

如果多个策略都合格，按以下优先级选择：

1. **优先方案 A（triple_barrier_simple）**：如果 Kappa > 0.30
   - 理由：最贴近真实交易，可直接用于回测

2. **次选方案 B（dip_recovery_v2）**：如果 Kappa > 0.35 且方案 A 不合格
   - 理由：保留原策略逻辑，修复问题

3. **最后方案 C（directional_filtered）**：如果前两个都不合格
   - 理由：简单可靠，风险最低

---

## 八、下一步行动（实验完成后）

### 8.1 如果找到合格策略

1. 做 PnL 回测（加入交易成本、滑点）
2. Paper Trading 验证 1-3 个月
3. 小资金实盘测试

### 8.2 如果所有策略都不合格

1. 考虑用回归替代分类（预测未来收益率）
2. 增加更多特征（如链上数据、宏观数据）
3. 考虑多模型融合
4. 重新审视问题定义（是否应该预测"是否交易"而非"方向"）

---

## 九、快速开始

### 9.1 运行对比实验

```bash
# 方案 A：Triple Barrier 简化版
python scripts/run_experiment.py configs/experiments/weekly/exp_weekly_bear_label_comparison_triple_barrier.yaml

# 方案 B：改进版 Dip Recovery
python scripts/run_experiment.py configs/experiments/weekly/exp_weekly_bear_label_comparison_dip_recovery_v2.yaml

# 方案 C：带过滤的 Directional
python scripts/run_experiment.py configs/experiments/weekly/exp_weekly_bear_label_comparison_directional_filtered.yaml
```

### 9.2 对比结果

实验完成后，填写以下对比表格：

| 策略 | Kappa | Precision | Recall | 正例率 | 正 Kappa 比例 | 是否合格 |
|------|-------|-----------|--------|--------|--------------|---------|
| dip_recovery_v1 (基准) | 0.56 | 0.89 | 0.76 | 63% | 100% | ❌ |
| triple_barrier_simple | ? | ? | ? | ? | ? | ? |
| dip_recovery_v2 | ? | ? | ? | ? | ? | ? |
| directional_filtered | ? | ? | ? | ? | ? | ? |

---

**创建日期**: 2026-03-01
**最后更新**: 2026-03-01
