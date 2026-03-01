# v0305 去污染实验结果

## 📝 核心结论

### ✅ 好消息：directional_filtered 的预测能力是真实的

去除污染特征后，**Kappa 从 0.326 上升到 0.343**，说明：

1. 模型的预测能力**不依赖于特征-标签污染**
2. 移除污染特征反而减少了噪音，让模型学到更有意义的信号
3. Top 特征从 `rsi_14`/`price_vs_sma_50` 变为 `funding_rate_14`/`volatility_20d` — 更合理

### ⚠️ 未解决问题：Fold 稳定性仍然很差

48% 的 fold F1=0 （主要因为 7% 正例率太低）。

---

## 实验结果对比

| 实验 | 标签策略 | 改动 | Kappa | F1 | Precision | Recall | F1=0 占比 |
|------|---------|------|-------|-----|-----------|--------|--------|
| **v0304 opt** (baseline) | directional_filtered | 原始 (含污染特征) | 0.326 | 0.401 | 0.371 | 0.437 | 48% |
| **E1 decontam** ⭐ | directional_filtered | 移除 rsi/sma 特征 | **0.343** | **0.414** | **0.396** | 0.434 | 48% |
| **E2 pure** | directional_binary | 无 RSI/MA 过滤 | -0.065 | 0.308 | 0.350 | 0.276 | 38% |
| **E3 TB 4/3** | triple_barrier_simple | pt=4%/sl=3% | 0.006 | 0.406 | 0.469 | 0.359 | 18% |
| **E4 TB 3/2** | triple_barrier_simple | pt=3%/sl=2% | 0.027 | 0.412 | 0.437 | 0.390 | 5% |

---

## 详细分析

### E1: directional_filtered 去污染 ⭐

**结论：去污染有效，预测能力真实存在。**

- Kappa 0.326 → 0.343 (+5.2%)
- Precision 0.371 → 0.396 (+6.7%)
- 移除的特征：rsi_*, price_vs_sma_*, sma_cross_10_50, sma_cross_50_200

**Top 10 特征 (去污染后)**：

| Rank | Feature | Importance |
|------|---------|------------|
| 1 | funding_rate_14 | 79 |
| 2 | volatility_20d | 43 |
| 3 | obv | 33 |
| 4 | high_50d_dist | 32 |
| 5 | ext_fgi_std_14 | 29 |
| 6 | obv_sma_20 | 29 |
| 7 | vol_price_corr_10 | 26 |
| 8 | cvd_change_21 | 25 |
| 9 | sma_200 | 25 |
| 10 | qvol_sma_10 | 25 |

✅ **特征重要性合理**：资金费率、波动率、OBV 、恐慌贪婪指数——都是有实际交易意义的信号。

### E2: 纯方向标签 (无过滤)

**结论：RSI/MA 过滤对标签质量至关重要。**

- Kappa = -0.065（负值，还不如随机）
- 说明“未来 21 天涨幅 ≥4%”单独作为标签太噪，模型完全学不到
- RSI < 45 + price < SMA50 的过滤**抬高了标签质量**，是有意义的

### E3/E4: Triple Barrier 调参

**结论：Triple Barrier 在所有参数范围内都无效。**

| 参数 | Kappa | F1=0 占比 |
|--------|-------|--------|
| v0304: pt=6%/sl=4% | 0.003 | 未统计 |
| v0304 opt: pt=5%/sl=3% | ≈0 | 未统计 |
| **E3: pt=4%/sl=3%** | 0.006 | 18% |
| **E4: pt=3%/sl=2%** | 0.027 | 5% |

E4 的 F1=0 占比仅 5%（非常稳定），但 Kappa 约等于 0，实质上模型没有预测能力。

---

## Fold Regime 分析（E1 重点）

| Regime | Fold 数 | Kappa 均值 | F1>0 占比 | 解读 |
|--------|---------|------------|------------|------|
| **Bull** | 23 | **0.388** | 65% | ✅ 牛市下模型最有效 |
| **Sideways** | 18 | 0.235 | 56% | ⚠️ 震荡市一般 |
| **Bear** | 15 | 0.135 | 27% | ❌ 熊市下基本失灵 |

F1=0 的 27 个 fold 中：
- Bear: 11 个（40.7%）
- Sideways: 8 个（29.6%）
- Bull: 8 个（29.6%）

**模型在熊市中大量失灵，符合预期** — 标签定义是“跌后反弹”，熊市中真正的反弹机会本就少。

---

## 🎯 上线评估

### 对照上线门槛

| 指标 | 门槛 | E1 结果 | 判定 |
|------|------|---------|------|
| Kappa ≥ 0.20 | 0.20 | **0.343** | ✅ |
| Precision ≥ 0.30 | 0.30 | **0.396** | ✅ |
| F1=0 占比 ≤ 30% | 30% | **48%** | ❌ |
| 无特征污染 | - | **已清除** | ✅ |
| 正例率 5-40% | - | **~7%** | ⚠️ 偏低 |

### 结论：**有条件上线**

E1 在预测能力和标签纯净度上通过，但 fold 稳定性未达标。
建议以下方案之一：

#### 方案 A：直接上线 + Regime 开关
- 仅在非熊市环境下启用模型信号
- 熊市中模型静默（不出信号）
- 可用滚动 63 天收益率判断 regime

#### 方案 B：降低阈值提高正例率
- 尝试 X=3%, RSI=50 或去掉 require_below_ma
- 目标：正例率从 7% 提升到 15%+
- 预期可大幅减少 F1=0 的 fold

---

## 实验产物

| 实验 | 目录 |
|------|------|
| E1 | `experiments/weekly/weekly_bear_v0305_E1_decontam/` |
| E2 | `experiments/weekly/weekly_bear_v0305_E2_directional_pure/` |
| E3 | `experiments/weekly/weekly_bear_v0305_E3_tb_grid_a/` |
| E4 | `experiments/weekly/weekly_bear_v0305_E4_tb_grid_b/` |
| Regime 分析 | `experiments/weekly/v0305_fold_regime_analysis.md` |

---

## 🚀 下一步工作

1. **降低阈值实验**：X=3%, RSI=50，提高正例率解决 fold 稳定性
2. **Regime 开关**：集成 regime detection，熊市下自动静默
3. **交易回测**：对 E1 做 PnL 回测，加入交易成本、滑点

---

**创建日期**: 2026-03-01
**前置实验**: v0304_label_strategy_comparison_results.md
