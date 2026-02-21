# v0302 Alpha Validation — 代码审查 & 结果分析报告

> 审查人: sam 🐶 (Code Puppy)
> 审查日期: 2026-02-20
> 审查范围: 10 个实验脚本 + v0302_utils.py + report.md

---

## 🚨 总体判定：实验结果 **不可信**，存在多个严重代码逻辑错误

本次审查发现 **5 个 Critical Bug**、**4 个 Major Issue**、**3 个 Minor Issue**。
报告中的所有"PASS"结论都需要在修复后重新验证。

---

## 一、Critical Bugs（必须修复，直接影响结论）

### 🔴 C1: 模型不一致 — 所有实验用错了模型

**位置**: 所有 e01~e10 脚本的 `run_walk_forward()` 函数

**问题**: 实验计划 (v0302_experiment_plan.md) 明确指定：
```yaml
model:
  type: orion_bix
  params: {n_estimators: 16, random_state: 42}
```

但所有实验脚本实际使用的是：
```python
model = RandomForestClassifier(
    n_estimators=100,
    max_depth=6,
    random_state=42,
    n_jobs=-1
)
```

**影响**: 这是一个 **完全不同的模型**，导致:
- 所有实验的 IC/Sharpe/t-stat 都不是 v0301 结果的验证
- 验证实验验证的是一个从未在 v0301 中使用的模型
- 所有结论（包括 PASS 和 FAIL）都不适用于原始 alpha

**严重性**: ⛔ 致命 — 整个实验批次的前提被打破

---

### 🔴 C2: E01 真实 IC 异常低（IC=0.08），但报告判定为 PASS

**位置**: `e01_random_label.py` 结果 + `report.md` E01 结论

**问题**:
- 实验计划预期真实 IC = 0.65（v0301 结果）
- E01 实际得到真实 IC = **0.0835**，p-value = **0.4209**
- 随机标签平均 IC = -0.0487
- Empirical p-value = **0.4333**

但报告判定为：✅ **PASS** - "Random labels rarely produce IC >= real IC"

**逻辑谬误**: Real IC 本身不显著 (p=0.42)！随机标签当然不会超过一个已经等于零的值。
这好比说"我考了 10 分，作弊的人没一个超过 10 分，所以我没作弊" —— 对，但你也没学到东西 😅

**正确判定**: 应该是 ❌ **FAIL** — 模型在此配置下**没有预测能力**

**严重性**: ⛔ 致命 — E01 的 PASS 结论完全错误

---

### 🔴 C3: E02 收益对齐逻辑错误

**位置**: `e02_continuous_ic.py` 第 ~160-166 行

**问题代码**:
```python
for idx in valid_idx:
    if idx + T < len(close_prices):
        ret = (close_prices[idx+T] - close_prices[idx+T-step]) / close_prices[idx+T-step]
        aligned_returns.append(ret)
```

**错误**: 计算的是 `close[idx+T-step]` 到 `close[idx+T]` 的收益（最后 step 天），
而不是 `close[idx]` 到 `close[idx+T]` 的收益（从预测点开始的 T 天收益）。

**应该是**:
```python
ret = (close_prices[idx + T] - close_prices[idx]) / close_prices[idx]
```

**影响**: Continuous IC 的值 (0.0572) 是基于错误的收益计算的，无法判断模型是否有连续排序能力。

**严重性**: ⛔ 致命 — E02 的核心指标是错的

---

### 🔴 C4: E03 在非连续价格序列上计算 MA — 完全无意义

**位置**: `e03_no_ma.py` 的 `backtest_with_ma()` 函数

**问题代码**:
```python
# aligned_prices 是通过 valid_idx 从日线数据中挑出的点
# valid_idx 来自 walk-forward，步长=21，窗口=63
# 所以 aligned_prices 包含重叠但不连续的价格点

aligned_prices = [prices[idx] for idx in valid_idx]
ma50 = pd.Series(aligned_prices).rolling(50).mean()   # ← 在非日线数据上算 MA!!
ma150 = pd.Series(aligned_prices).rolling(150).mean()  # ← 完全无意义
ma200 = pd.Series(aligned_prices).rolling(200).mean()  # ← 完全无意义
```

**问题**: `aligned_prices` 不是连续日线价格，而是 OOS 预测日的价格子集。
在这些离散点上计算 MA50/150/200 毫无意义——你需要在原始日线数据上算好 MA，
再索引到 `valid_idx` 对应的日期。

**结果影响**: Triple MA 策略 Sharpe = -0.0474，极可能是因为 MA 信号完全错误。
报告据此得出"MA 反而降低表现"——但这只是因为 MA 是错的！

**严重性**: ⛔ 致命 — E03 的 MA 策略结论不可信

---

### 🔴 C5: E10 Regime 分析中 Non-overlapping 抽样逻辑错误

**位置**: `e10_bear_regime.py` 的 `calc_regime_ic()` 函数

**问题代码**:
```python
def calc_regime_ic(predictions, true_labels, regimes, target_regime):
    # 1. 按 regime 过滤
    regime_preds = [p for i, p in enumerate(predictions) if regimes[i] == target_regime]
    regime_labels = [l for i, l in enumerate(true_labels) if regimes[i] == target_regime]

    # 2. 在过滤后的序列上做 non-overlapping
    preds_no = np.array(regime_preds[:n_no*step:step])  # ← 错！
```

**问题**: 过滤后的列表不再保持原始时间间隔。如果 bull 和 bear 交替出现，
过滤后的 "每第 21 个样本" 在时间上可能只相隔几天，根本不是 non-overlapping。

**正确做法**: 应先标记每个样本的原始日期索引，按日期做 non-overlapping 采样（每 21 天取一个），
再按 regime 过滤。

**影响**: Bull IC = -0.145, Bear IC = 0.174 都是基于错误抽样的，不可靠。

**严重性**: ⛔ 致命 — E10 的 regime IC 不可信

---

## 二、Major Issues（需要修复，影响结果可靠性）

### 🟠 M1: E05 "月度 IC 序列" 不是真正的月度

**位置**: `e05_newey_west.py` 的 `calc_monthly_ic_series()`

**问题**: 函数将 OOS 预测按每 21 个样本分组（不是按日历月分组），
每组只有 21 个样本就算一个 IC。这不是 "月度 IC"，而是 "滚动窗口 IC"。

更重要的是，OOS 窗口 = 63 天、步长 = 21 天，所以 **OOS 预测之间有大量重叠**。
21 个连续 OOS 预测中的大部分来自同一个训练窗口，IC 估计高度自相关。

报告显示 autocorr(1) = 0.42, autocorr(2) = 0.50，印证了这一点。
但 Newey-West 修正是否足以处理这种结构性自相关值得怀疑。

**影响**: t-stat (包括 NW 调整后的 6.15) 可能仍被高估。

---

### 🟠 M2: E06 Bootstrap 在重叠预测上进行

**位置**: `e06_bootstrap_ci.py`

**问题**: Bootstrap 是在 **所有** OOS 预测 (n=~1400+) 上做的，而不是 non-overlapping 样本。
因为 oos_window=63, step=21，相邻 OOS 窗口有 42 天重叠。

- IID Bootstrap CI: [0.106, 0.168] — 这个 CI 看起来很窄很精确
- 但样本间的高度相关意味着有效样本量远小于名义样本量
- Block Bootstrap (block_size=4) 也不够大，因为自相关跨度远超 4 个样本

**影响**: CI 可能比报告的窄得多，"95% CI 排除零" 的结论不够可靠。

---

### 🟠 M3: 实验编号错位

**位置**: 实验脚本 vs 实验计划

| 计划编号 | 计划名称 | 脚本编号 | 脚本名称 |
|---------|---------|---------|----------|
| E07 | 阈值敏感性 | E08 | threshold_sensitivity |
| E08 | Horizon 敏感性 | E09 | horizon_sensitivity |
| E09 | 多资产 ETH | E07 | multi_asset |
| E10 | Bear Regime | E10 | bear_regime |

计划中的 E09 是 "多资产验证"，但代码中用 E07 编号。混乱的编号增加了审查难度。

---

### 🟠 M4: 计划中 12 个实验，只实现了 10 个

**缺失**: E11 (分年 OOS) 和 E12 (特征 Ablation) 未实现。
这两个是 P2 实验，但对于理解 alpha 来源（是否被单一年份驱动、是否依赖单一特征集）
仍然重要。

---

## 三、Minor Issues

### 🟡 m1: E01 只做了 30 次排列，计划要求 100 次
样本量偏少，empirical p-value 精度较低 (分辨率 = 1/30 = 3.3%)。

### 🟡 m2: E08 阈值只测了 3 个值 (3%, 5%, 8%)，计划要求 6 个
计划要求测 3%, 4%, 5%, 6%, 8%, 10%。少了一半的数据点。

### 🟡 m3: E09 Horizon 只测了 4 个值 (14, 21, 28, 30)，缺少 7 和 42
计划要求 7, 14, 21, 28, 42。并且 28 和 30 太接近了，应换成 7 和 42。

---

## 四、实验结果重新解读

鉴于上述代码问题，以下是对实验结果的重新分析：

### 4.1 哪些结果可以（勉强）参考？

| 实验 | 原始结论 | 重新评估 | 理由 |
|------|---------|---------|------|
| E04 init_train | ❌ UNSTABLE | ⚠️ 可参考 | IC 计算逻辑正确（vs labels），但模型不对 |
| E05 NW t-stat | ✅ ROBUST | ⚠️ 需谨慎 | NW 逻辑正确，但"月度"分组有问题 |
| E08 阈值敏感性 | ✅ ROBUST | ⚠️ 可参考 | 逻辑基本正确，但模型不对 |
| E09 Horizon | ✅ ROBUST | ⚠️ 可参考 | 逻辑基本正确，但模型不对 |

### 4.2 哪些结果完全不可信？

| 实验 | 原始结论 | 重新评估 | 理由 |
|------|---------|---------|------|
| E01 随机标签 | ✅ PASS | ❌ 无效 | Real IC≈0, PASS 是假阳性 |
| E02 连续 IC | ⚠️ MARGINAL | ❌ 无效 | 收益对齐 Bug |
| E03 去 MA | ❌ WEAK | ❌ 无效 | MA 计算在非连续数据上 |
| E06 Bootstrap | ✅ PRECISE | ❌ 可疑 | Bootstrap 在重叠数据上 |
| E07 多资产 | ⚠️ SKIPPED | — | 无 ETH 数据 |
| E10 Bear | ❌ REGIME-DEP | ❌ 无效 | Non-overlap 抽样逻辑错误 |

### 4.3 核心数字对比

| 指标 | v0301 报告值 | v0302 E01 实际值 | 差异 |
|------|-------------|-----------------|------|
| IC | 0.65 | 0.0835 | ↓ 87% |
| IC p-value | <0.01 | 0.4209 | 不显著 |

| 指标 | v0302 其他实验 | 说明 |
|------|--------------|------|
| IC (E04/E08/E09) | 0.17~0.44 | 用了不同非重叠采样 |
| NW t-stat (E05) | 6.15 | 可能仍被重叠高估 |
| Bootstrap CI (E06) | [0.08, 0.19] | 基于重叠数据 |

---

## 五、根因分析：为什么 IC 从 0.65 掉到 0.08？

最可能的原因（按可能性排序）：

1. **模型不同**: v0301 用 Orion-BiX (n_estimators=16)，
   v0302 用 RandomForest (n_estimators=100, max_depth=6)

2. **IC 计算方式不同**: v0301 的 IC=0.65 可能是 overlapping IC
   (所有日度预测 vs labels)，而 E01 用了 non-overlapping (step=21)

3. **Walk-forward 实现差异**: v0301 可能使用了 Orion Benchmark 框架，
   而 v0302 手写了 sklearn walk-forward

4. **数据预处理差异**: scaler 差异、特征选择差异等

---

## 六、DRY 违规 🐶

虽然有 `v0302_utils.py` 提供了公共函数，但 **没有一个实验脚本使用它**！

每个脚本都重新实现了:
- `run_walk_forward()` — 10 次
- `calc_non_overlap_ic()` — ~8 次
- 数据加载逻辑 — 10 次

这违反了 DRY 原则，也是导致 Bug 难以统一修复的原因。
如果用了 utils，修一处就能修全部。

---

## 七、修复建议 & 行动计划

### 优先级 P0（在得出任何结论之前必须修复）

| # | 修复项 | 预估工时 |
|---|--------|--------|
| 1 | 将所有脚本的模型替换为 Orion-BiX (或明确标注使用 RF 的理由) | 0.5 天 |
| 2 | 所有脚本统一使用 `v0302_utils.py` 的公共函数 (DRY) | 1 天 |
| 3 | 修复 E01 判定逻辑：当 Real IC 不显著时应判定为 FAIL | 0.5 小时 |
| 4 | 修复 E02 收益对齐: `close[idx+T]/close[idx] - 1` | 0.5 小时 |
| 5 | 修复 E03 MA 计算: 在日线数据上计算后再索引 | 1 小时 |
| 6 | 修复 E10 Non-overlap: 先 non-overlap 采样再按 regime 过滤 | 1 小时 |

### 优先级 P1（提高结果可靠性）

| # | 修复项 | 预估工时 |
|---|--------|--------|
| 7 | E05: 改为按日历月分组计算 IC | 1 小时 |
| 8 | E06: Bootstrap 在 non-overlapping 样本上做 | 1 小时 |
| 9 | E01: 增加到 100 次排列 | 运行时间 |
| 10 | 统一实验编号与计划一致 | 0.5 小时 |

### 优先级 P2（完善实验覆盖）

| # | 修复项 | 预估工时 |
|---|--------|--------|
| 11 | 实现 E11 (分年 OOS) | 2 小时 |
| 12 | 实现 E12 (特征 Ablation) | 3 小时 |
| 13 | E08 增加到 6 个阈值点 | 运行时间 |
| 14 | E09 增加 T=7 和 T=42 | 运行时间 |

---

## 八、最终判定

基于实验计划第八节的判定矩阵：

### P0 毁灭性测试（需 4/4 通过）

| 条件 | 通过标准 | 结果 | 状态 |
|------|---------|------|------|
| E01 随机标签 IC ≈ 0 | 100 次排列无一次 IC ≥ 真实 IC | ❌ Real IC ≈ 0, 测试无意义 | 🔴 INVALID |
| E02 连续 IC > 0.05 | 纯收益排序有预测力 | ❌ 计算 Bug | 🔴 INVALID |
| E03 纯模型 Sharpe > 0.3 | 模型有独立 alpha | ❌ MA 计算 Bug | 🔴 INVALID |
| E04 IC 在多 init_train 下稳定 | 非人为扩大样本 | ⚠️ IC 方差 0.012 但模型不对 | 🟡 CONDITIONAL |

**P0 结果**: 0/4 有效通过 → 按判定矩阵 = **"No Alpha" — 回到研究阶段**

### 但请注意！

这个判定是基于 **错误模型 (RandomForest)** 的结果。
使用正确的 Orion-BiX 模型后，结果可能完全不同。

所以正确的结论是：

> **🐶 Sam 的判定: INCONCLUSIVE — 实验设计合理，但实现有严重 Bug，
> 需修复后重新运行才能得出有效结论。**

---

*报告生成: 2026-02-20 by Code Puppy 🐶*
*审查方法: 逐行代码审查 + 逻辑推理 + 与实验计划交叉验证*