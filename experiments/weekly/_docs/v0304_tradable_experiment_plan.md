# v0304 可交易标签实验计划 (修订版)

> 基于 v0302_experiment_plan.md 和 v0302_refactor_plan.md 修订
>
> **核心问题**: 当前 dip_recovery 标签存在未来数据泄露，无法指导实际交易

---

## 一、问题总结

### v0302 原计划的问题

| 问题 | 描述 | 状态 |
|------|------|------|
| Label 未来泄露 | dip_recovery 使用未来 T 天的 low/high | ⚠️ 未解决 |
| 信号反转 | 模型预测"跌"，实际做"涨" | ⚠️ 未解决 |
| MA 后置过滤 | 43% Sharpe 来自人工规则 | ⚠️ 未解决 |
| Bear 模型失效 | 之前 Kappa = -0.07 | ✅ 已解决 (配置对齐) |

### 今日新发现

1. **dip_recovery 标签泄露**: 使用未来数据训练，预测时信息边界不一致
2. **Kappa 虚高**: 0.58 的 Kappa 可能来自泄露而非真实信号
3. **不可部署**: 当前标签无法指导 8 点交易

---

## 二、修订后的实验计划

### Phase 1: 可交易标签验证 (最高优先级)

**目标**: 验证无未来数据泄露的标签是否仍有预测能力

| 实验 | 标签定义 | 无泄露 | 模型 | 目标 Kappa |
|------|----------|--------|------|------------|
| R1-A | 明日收益 (T=1) | ✓ | Orion-BiX | > 0.15 |
| R1-B | 未来7天收益 (T=7) | ✓ | Orion-BiX | > 0.15 |
| R1-C | 未来14天收益 (T=14) | ✓ | Orion-BiX | > 0.15 |
| R1-D | 未来21天收益 (T=21) | ✓ | Orion-BiX | > 0.15 |

**验收标准**: 任一实验 Kappa > 0.15 即证明无泄露标签仍可交易

### Phase 2: IC 验证 (关键)

**目标**: 用 IC 分析验证信号真实有效性

| 实验 | 内容 | 工具 |
|------|------|------|
| R2-IC | 对 Phase 1 最优标签做 Rank IC 分析 | ic_analysis_corrected.py |
| R2-Random | 随机打乱标签，验证 IC 消失 | 100 次排列测试 |

**验收标准**:
- Rank IC > 0.02
- IC t-stat > 1.0
- 随机标签 IC ≈ 0

### Phase 3: MA 特征融合 (可选)

**目标**: 将 Triple MA 信息融入模型，减少后置过滤依赖

| 实验 | 特征集 | 后置 MA | 目标 Sharpe |
|------|--------|---------|-------------|
| R3-Baseline | 148 特征 | 无 | > 0.3 |
| R3-MA | 148 + MA交互特征 | 无 | > 0.3 |
| R3-Compare | 对比有无 MA 特征 | 有/无 | - |

---

## 三、标签定义 (无泄露版本)

### 方案 A: 简单收益方向

```python
# 预测: 未来 N 天收益方向
future_return = (close[t+N] - close[t]) / close[t]
Label = 1 if future_return > 0 else 0
```

**优点**: 完全无泄露，直接可交易
**缺点**: 类别不平衡 (BTC 长期牛市)

### 方案 B: 超额收益

```python
# 预测: 是否跑赢近期平均
rolling_mean = close.pct_change(N).rolling(63).mean()
future_return = close.pct_change(N).shift(-N)
Label = 1 if future_return > rolling_mean else 0
```

### 方案 C: 突破买入

```python
# 收盘突破过去 N 天最高点
past_high = high.rolling(N).max()
Label = 1 if close > past_high else 0
```

---

## 四、执行计划

```
Week 1:
├── Day 1: 实现标签函数 (simple_return, excess_return, breakout)
├── Day 2: 运行 R1-A ~ R1-D (并行)
├── Day 3: 分析结果，选最优标签
├── Day 4: 运行 R2-IC 验证
└── Day 5: 运行 R2-Random 确认

Week 2 (可选):
├── Day 1-2: R3 MA 特征融合
└── Day 3-5: 工程重构 + 部署
```

---

## 五、成功标准

| 阶段 | 指标 | 最低标准 | 目标 |
|------|------|----------|------|
| R1 | Kappa | > 0.10 | > 0.15 |
| R2 | Rank IC | > 0.02 | > 0.05 |
| R2 | IC t-stat | > 1.0 | > 2.0 |
| R3 | Sharpe (无MA) | > 0.3 | > 0.5 |

---

## 六、与 v0302 原计划的区别

| 方面 | v0302 原计划 | v0304 修订版 |
|------|--------------|--------------|
| 核心问题 | 验证 alpha 真实性 | **修复标签可交易性** |
| Label | dip_recovery (有泄露) | 简单收益 (无泄露) |
| MA 处理 | 后置过滤 | 融入特征 |
| 验证方法 | Kappa 为主 | **IC 分析为主** |

---

## 七、下一步行动

1. **确认方案**: 选择方案 A/B/C 中的一个
2. **实现代码**: 在 `src/labels/` 中新增标签函数
3. **运行实验**: Phase 1 基础验证
4. **IC 分析**: Phase 2 验证信号有效性

---

*计划修订: 2026-02-28*
*基于: v0302_experiment_plan.md, v0302_refactor_plan.md*
