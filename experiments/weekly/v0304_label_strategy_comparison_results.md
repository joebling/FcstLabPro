# v0304 标签策略对比实验结果

## 📋 核心结论（先行）

### 🏆 最佳策略：directional_filtered

**推荐理由**：
- ✅ **Kappa=0.267**，表明模型有真实的预测能力
- ✅ **标签定义严谨**，没有信息泄露问题
- ✅ **结合技术指标过滤**，提高了标签质量
- ✅ **特征重要性合理**（RSI 是最重要特征）

### ⚠️ 不推荐策略：dip_recovery_v1 (baseline)

**问题原因**：
- ❌ **标签定义存在信息泄露**，使用未来数据计算反弹
- ❌ **部分 Fold Precision=1.0**，过于完美不可信
- ❌ **模型学习到未来模式**，缺乏实际预测能力

### 🔄 优化实验结果

基于对比分析，我们进行了参数优化实验：

| 策略 | 优化方向 | 优化效果 |
|------|----------|----------|
| **directional_filtered** | X=4%, RSI=45 | ✅ F1: 0.325→0.401 (+23.6%), Kappa: 0.267→0.326 (+22.2%) |
| **dip_recovery_v2** | dip=5%, recovery=3% | ✅ F1: 0.118→0.208 (+75.9%), Kappa: 0.002→0.050 (+2829%) |
| **triple_barrier_simple** | pt=5%, sl=3% | ⚠️ 效果有限，Kappa 仍接近 0 |

---

## 实验概览

本实验对比了 4 种不同的标签策略在同一特征集和模型配置下的表现：

1. **baseline (dip_recovery_v1)**: 原始策略，来自 weekly_bear_v0302_prod
2. **triple_barrier_simple**: 方案 A - Triple Barrier 简化版
3. **dip_recovery_v2**: 方案 B - 改进版 Dip Recovery
4. **directional_filtered**: 方案 C - 带技术指标过滤的 Directional

所有实验使用相同配置：
- 初始训练集: 800
- OOS 窗口: 63
- 步进: 21
- 特征集: technical, volume, flow, market_structure, external_fgi
- 模型: LightGBM (相同参数)

---

## 📋 标签定义详解

### 1. baseline (dip_recovery_v1) - 原始策略

**标签逻辑**：
```python
# 从明天开始 T 天的最低点（不包含当天）
future_low = low.shift(-1).rolling(T).min()

# 计算跌幅和反弹
dip = (future_low - close) / close  # 相对当前价格的跌幅
recovery = (future_close - future_low) / future_low  # 从最低点到 T 天后收盘价的反弹

# 标签条件
Label = 1 if (dip < -dip_threshold) and (recovery > recovery_threshold)
```

**参数配置**：
- T = 21 天
- dip_threshold = 5%
- recovery_threshold = 3%

**问题分析**：
- ❌ **信息泄露风险**：使用 T 天后收盘价计算反弹，可能包含未来信息
- ❌ **反弹计算不准确**：应该用未来最高点而非收盘价计算反弹

### 2. triple_barrier_simple - Triple Barrier 简化版

**标签逻辑**：
```python
# 设置止盈止损屏障
upper_barrier = entry_price * (1 + pt)  # 止盈线
lower_barrier = entry_price * (1 - sl)  # 止损线

# 遍历未来 T 天，检查是否触及屏障
for j in range(i+1, min(i+T+1, n)):
    if low[j] <= lower_barrier:  # 先触及止损
        hit_sl = True
        break
    if high[j] >= upper_barrier:  # 先触及止盈
        hit_pt = True
        break

# 标签条件
Label = 1 if (hit_pt and not hit_sl)  # 先触及止盈且未触及止损
```

**参数配置**：
- T = 21 天
- pt = 6% (止盈阈值)
- sl = 4% (止损阈值)
- include_today = False (从明天开始计算)

**优势**：
- ✅ **真实交易逻辑**：模拟真实止盈止损交易
- ✅ **无信息泄露**：只使用未来价格数据，不涉及未来计算
- ✅ **风险可控**：明确的止盈止损比例

### 3. dip_recovery_v2 - 改进版 Dip Recovery

**标签逻辑**：
```python
# 找到未来 T 天内的最低点
min_pos_in_window = future_low_window.argmin()
min_val = future_low_window.iloc[min_pos_in_window]

# 检查下跌是否在前 dip_window 天内发生
days_to_min = min_pos_in_window  # 从窗口开始到最低点的天数
dip_in_window = days_to_min <= dip_window

# 计算从最低点到未来最高点的反弹
high_after_dip = future_high_window.iloc[min_pos_in_window:]
max_after_dip = high_after_dip.max()
recovery = (max_after_dip - min_val) / min_val

# 标签条件
Label = 1 if (dip < -dip_threshold) and dip_in_window and (recovery > recovery_threshold)
```

**参数配置**：
- T = 21 天
- dip_threshold = 7%
- recovery_threshold = 5%
- dip_window = 10 天
- include_today = False

**改进点**：
- ✅ **修复反弹计算**：使用未来最高点而非收盘价
- ✅ **避免先涨后跌**：要求下跌在前 dip_window 天内发生
- ✅ **提高阈值**：降低正例率，提高信号质量

### 4. directional_filtered - 带技术过滤的 Directional

**标签逻辑**：
```python
# 计算技术指标
rsi = calculate_rsi(close, rsi_window)
sma = calculate_sma(close, ma_window)

# 未来 T 天收益率
future_return = close.pct_change(T).shift(-T)

# 技术过滤条件
rsi_filter = rsi < rsi_threshold  # RSI 超卖条件
ma_filter = close < sma  # 价格在移动平均线下方

# 标签条件
Label = 1 if (future_return >= X) and rsi_filter and ma_filter
```

**参数配置**：
- T = 21 天
- X = 5% (收益率阈值)
- rsi_window = 14
- rsi_threshold = 40
- ma_window = 50
- require_below_ma = True

**优势**：
- ✅ **技术指标过滤**：结合传统技术分析
- ✅ **逻辑清晰**：条件简单明确
- ✅ **可解释性强**：易于理解和监控

### 5. 优化版本标签定义

#### directional_filtered_opt (优化版)
- **参数调整**：X = 4%, RSI = 45
- **目标**：提高正例率，改善模型性能

#### dip_recovery_v2_opt (优化版)  
- **参数调整**：dip = 5%, recovery = 3%
- **目标**：降低阈值，增加正例样本

#### triple_barrier_simple_opt (优化版)
- **参数调整**：pt = 5%, sl = 3%
- **目标**：调整止盈止损比例，提高策略敏感性

---

## 结果对比表

| 标签策略 | 正例率 | 准确率 | F1 | Precision | Recall | Cohen's Kappa |
|---------|-------|-------|----|-----------|--------|--------------|
| **dip_recovery_v1 (baseline)** | ~33% | **0.796** | **0.671** | **0.710** | **0.636** | **0.560** |
| triple_barrier_simple | ~44% | 0.524 | 0.351 | 0.450 | 0.288 | 0.003 |
| dip_recovery_v2 | ~23% | 0.767 | 0.118 | 0.180 | 0.088 | 0.002 |
| **directional_filtered** | ~7% | 0.891 | 0.325 | 0.287 | 0.374 | **0.267** |

---

## 详细分析

### 1. baseline (dip_recovery_v1) - 原始策略

**特点**:
- 正例率最高 (~33%)
- 各项指标都很好
- Kappa = 0.56，表明模型有很强的预测能力

**问题**:
- 之前分析发现标签定义存在"事后诸葛亮"的问题
- 用未来 T 天后的收盘价计算反弹，而不是从最低点的反弹
- 部分 Fold 的 Precision=1.0，过于完美

**建议**: 不推荐使用，因为标签定义不够严谨。

---

### 2. triple_barrier_simple - 方案 A

**特点**:
- 正例率 44%，是所有策略中最高的
- 整体表现最差
- Kappa ≈ 0，几乎没有预测能力
- Precision=0.45，Recall=0.29，F1=0.35

**问题**:
- 止盈止损设置可能不合理（pt=6%, sl=4%）
- 标签定义过于严格或过于宽松
- 需要调整参数

---

### 3. dip_recovery_v2 - 方案 B

**特点**:
- 正例率 23%
- 准确率看似不错 (76.7%)，但这是因为负例多
- Kappa ≈ 0，几乎没有预测能力
- Precision=0.18，Recall=0.09，F1=0.12，表现很差

**问题**:
- 阈值设置过高 (dip=7%, recovery=5%)
- 正例太少，模型难以学习
- 需要降低阈值

---

### 4. directional_filtered - 方案 C ⭐

**特点**:
- 正例率最低 (~7%)
- 准确率最高 (89.1%)
- Kappa=0.267，是所有新策略中最高的
- Recall=0.374，Precision=0.287，F1=0.325

**优点**:
- 标签定义清晰：未来 21 天涨 >5% + RSI<40 + 价格在 SMA50 下方
- 结合技术指标过滤，提高了标签质量
- 避免了"事后诸葛亮"问题
- 模型学到了有意义的模式（Top 特征是 rsi_14）

**Top 20 重要特征**:
1. rsi_14 (76)
2. low_21d_dist (42)
3. low_50d_dist (36)
4. volatility_20d (35)
5. price_vs_sma_50 (32)

---

## 结论与建议

### 最佳选择: directional_filtered

虽然 directional_filtered 的指标不如原始的 dip_recovery_v1 那么"完美"，但它：
1. ✅ 标签定义更严谨，没有信息泄露
2. ✅ 结合了技术指标过滤，提高了标签质量
3. ✅ Kappa=0.267，表明模型有真实的预测能力
4. ✅ 特征重要性合理（RSI 是最重要特征）

## 🔄 优化实验结果

基于上述优化方向，我们已完成了参数优化实验：

### ✅ directional_filtered 优化结果 (X=4%, RSI=45)
- **F1**: 0.325 → 0.401 (+23.6%)
- **Precision**: 0.287 → 0.371 (+29.3%)
- **Recall**: 0.374 → 0.437 (+16.8%)
- **Kappa**: 0.267 → 0.326 (+22.2%)
- **结论**: 参数优化显著提升了模型性能

### ✅ dip_recovery_v2 优化结果 (dip=5%, recovery=3%)
- **F1**: 0.118 → 0.208 (+75.9%)
- **Precision**: 0.180 → 0.321 (+78.6%)
- **Recall**: 0.088 → 0.153 (+74.5%)
- **Kappa**: 0.002 → 0.050 (+2829%)
- **结论**: 降低阈值显著改善了模型表现

### ⚠️ triple_barrier_simple 优化结果 (pt=5%, sl=3%)
- 各项指标变化不大，Kappa 值仍然接近 0
- **结论**: 该策略在当前参数范围内难以获得显著改善

## 🎯 最终建议

### 推荐策略：directional_filtered (优化版)
- **配置**: X=4%, RSI=45, MA=50
- **优势**: 性能最佳，标签定义严谨，可解释性强
- **Kappa**: 0.326，表明模型有真实的预测能力

### 备选策略：dip_recovery_v2 (优化版)
- **配置**: dip=5%, recovery=3%
- **优势**: 改善幅度巨大，仍有优化空间
- **Kappa**: 0.050，预测能力较弱但持续改善

### 不推荐策略：dip_recovery_v1 (baseline)
- **原因**: 标签定义存在信息泄露，模型学习到未来模式

---

## 实验产物

所有实验结果已保存在：
- baseline: `experiments/weekly/weekly_bear_v0302_prod/`
- triple_barrier_simple: `experiments/weekly/weekly_bear_v0304_triple_barrier/`
- dip_recovery_v2: `experiments/weekly/weekly_bear_v0304_dip_recovery_v2/`
- directional_filtered: `experiments/weekly/weekly_bear_v0304_directional_filtered/`
- **优化实验**:
  - directional_filtered_opt: `experiments/weekly/weekly_bear_v0304_directional_filtered_opt/`
  - triple_barrier_opt: `experiments/weekly/weekly_bear_v0304_triple_barrier_opt/`
  - dip_recovery_v2_opt: `experiments/weekly/weekly_bear_v0304_dip_recovery_v2_opt/`

## 📈 下一步工作

1. **继续优化 directional_filtered**: 尝试 X=3%, RSI=50 的组合
2. **探索模型参数调优**: 在最佳标签策略基础上进行超参数优化
3. **验证策略稳定性**: 在不同市场周期下的表现
4. **考虑多策略组合**: 结合不同标签策略的优势
