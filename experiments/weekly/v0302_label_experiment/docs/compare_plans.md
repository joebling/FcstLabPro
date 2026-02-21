# ins_gpt.md vs experiment_plan.md 对比分析

**日期**: 2026-02-21

---

## 一、核心共同点 ✅

### 1. 认知重构
两个文件都强调：
> **dip_recovery 是环境检测器，不是方向预测**

### 2. 三层架构（Environment → Trigger → Execution → Exit）
两个文件都认可这个核心结构。

### 3. 关键设计元素
| 元素 | ins_gpt.md | experiment_plan.md |
|------|-------------|-------------------|
| Trigger A | ✅ 等待 dip ≥4% | ✅ 等待 dip ≥4% |
| TP/SL | ✅ +6% / -5% | ✅ +6% / -5% |
| 时间止损 | ✅ 14 天 | ✅ 14 天 |
| Position sizing | ✅ size = f(prob) | ✅ size = f(prob) |
| 风险控制 | ✅ Volatility targeting, DD cutoff | ✅ Volatility targeting, DD cutoff |

---

## 二、主要差异 ⚠️

### 差异 1: 整体架构复杂度

| 方面 | ins_gpt.md | experiment_plan.md |
|------|-------------|-------------------|
| 架构层数 | 7 层（Data → Feature → Model → Signal → Trigger → Execution → Risk → PnL） | 更简单的三层 |
| 伪代码 | ✅ 非常详细 | ❌ 没有伪代码 |
| 数据层 | ✅ DataHandler 类 | ❌ 使用现有 loader |
| Feature 层 | ✅ FeatureEngine 类 | ❌ 使用现有 builder |
| Execution 层 | ✅ 显式滑点、手续费 | ❌ 暂时不考虑 |

---

### 差异 2: Regime-Switching 双策略系统

| 方面 | ins_gpt.md | experiment_plan.md |
|------|-------------|-------------------|
| Regime Switch | ✅ 双策略（MR + Trend） | ❌ 只有单策略 |
| Strategy A | ✅ Mean Reversion | ✅ 只有这个 |
| Strategy B | ✅ Trend Following | ❌ 没有 |
| 组合结构 | ✅ 硬切换或软切换 | ❌ 没有 |

---

### 差异 3: 实验验证内容

| 实验 | ins_gpt.md | experiment_plan.md |
|------|-------------|-------------------|
| 单策略对比 | ✅ Trend only, MR only, Regime Switch | ❌ 只有 MR 相关 |
| prob 分层 | ✅ prob 高 → MR 收益高，prob 低 → Trend 收益高 | ✅ 只有 Sharpe(prob high) > Sharpe(prob low) |
| 跨资产验证 | ✅ ETH, SOL | ✅ ETH, SOL |
| 交易成本 stress | ✅ 手续费×2, 滑点×2 | ❌ 没有 |
| 极端行情 | ✅ 2022熊市, 2023震荡, 2024牛市 | ✅ 2022熊市, 2023震荡, 2024牛市 |

---

### 差异 4: 成功标准

| 标准 | ins_gpt.md | experiment_plan.md |
|------|-------------|-------------------|
| OOS Sharpe | > 1.2 | > 1.2 |
| MaxDD | < 35% | < 35% |
| 跨资产有效 | ✅ | ✅ |
| 成本翻倍仍 > 0.8 Sharpe | ✅ | ❌ 没有 |

---

## 三、对比总结

### experiment_plan.md 的优点 ✅
1. **更简单、更聚焦**：从 MVP 开始，逐步迭代
2. **5 个阶段清晰**：容易执行和跟踪
3. **与现有代码兼容**：使用现有的 loader, builder, labels
4. **先验证核心思路**：不一开始就搞复杂架构

### ins_gpt.md 的优点 ✅
1. **架构更完整**：7 层架构，机构级设计
2. **Regime-Switching**：双策略系统，更高级
3. **显式成本模型**：滑点、手续费，更真实
4. **实验验证更全面**：包含交易成本 stress

---

## 四、建议方案 🎯

### 方案 A：继续执行 experiment_plan.md（推荐）
**理由**：
1. 已经完成 exp01_mvp，有基础
2. 5 个阶段清晰，容易执行
3. 可以后续补充 ins_gpt.md 中的高级特性

**后续补充**：
- exp06: 加入 Regime-Switching
- exp07: 加入交易成本模型
- exp08: 交易成本 stress test

---

### 方案 B：重构为 ins_gpt.md 的架构
**理由**：
1. 架构更完整、更专业
2. Regime-Switching 可能带来更好的表现
3. 显式成本模型更真实

**缺点**：
1. 需要重构现有代码
2. 工作量更大
3. 可能延迟进度

---

## 五、我的建议 ✅

**继续执行 experiment_plan.md，但在后续阶段补充 ins_gpt.md 的高级特性**：

| 当前阶段 | 计划 |
|---------|------|
| exp01_mvp | ✅ 已完成 |
| exp02_prob_layered | 继续执行 |
| exp03_param_opt | 继续执行 |
| exp04_advanced | 继续执行 |
| exp05_cross_asset | 继续执行 |
| **exp06_regime_switch** | 新增：加入 Regime-Switching |
| **exp07_cost_model** | 新增：加入交易成本模型 |
| **exp08_cost_stress** | 新增：交易成本 stress test |

这样既保持了进度，又能逐步加入更高级的特性。

---
