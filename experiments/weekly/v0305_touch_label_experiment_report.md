# v0305 E8/E9 Touch Label 实验报告

> 实验日期：2026-03-05
> 实验目标：验证路径依赖标签 `touch_X_within_T` 是否优于当前生产模型的终点标签 `directional_filtered`
> 来源：`gpt_REVIEW.md` 第 2.3 节 “标签与交易目标不完全一致” 建议

---

## 一、实验动机

生产模型 `e1-conservative` 使用 `--take-profit` 止盈逻辑：窗口内触达 +X% 即平仓。
但标签 `directional_filtered` 定义是“第 T 天收盘价 >= +X%”（路径无关）。

这导致：
- 标签判负但实际路径内早已触发 TP → **漏报（False Negative）**
- 标签判正但路径中途大幅回撤 → **虚报（Bad Experience）**

新标签 `touch_filtered` 改为：“窗口 [1,T] 内任一天最高价 >= close*(1+X)”，与 TP 逻辑完全对齐。

---

## 二、实验矩阵

| ID | 实验名 | 标签 | 参数 | 对标 |
|----|--------|------|------|------|
| E8 | touch_label | touch_filtered | X=4%, RSI<45, MA50 | E1 |
| E9 | touch_low_threshold | touch_filtered | X=3%, RSI<50, MA50 | E5 |

所有实验均保留 E1 的去污染设置（drop rsi_*/price_vs_sma_*/sma_cross_*）。

---

## 三、分类指标对比

| 实验 | 标签 | Kappa | F1 | Precision | Recall | F1=0 Folds |
|------|------|-------|------|-----------|--------|------------|
| **E1** (生产) | directional_filtered | 0.343 | 0.414 | 0.396 | 0.434 | **48%** (27/56) |
| **E5** (之前最佳) | directional_filtered (low) | 0.343 | 0.441 | 0.434 | 0.449 | **41%** (23/56) |
| **E8** ⭐ | touch_filtered | **0.751** | **0.799** | **0.797** | **0.801** | **16%** (9/56) |
| **E9** | touch_filtered (low) | **0.832** | **0.881** | **0.846** | **0.918** | **14%** (8/56) |

### 关键发现：
- **Kappa 提升 2x+**：E8 从 0.343 → 0.751，E9 达 0.832
- **F1=0 折叠大幅下降**：48% → 16%/14%，模型稳定性显著提升
- 高 Kappa 的原因：touch 标签产生更多正例（路径内触达比终点判定容易得多），类别平衡更好

---

## 四、PnL 回测对比（止盈+Regime 变体）

| 指标 | E1 (生产) | E8 (touch) | E9 (touch low) |
|------|---------|------------|----------------|
| Total Return | +36.67% | **+64.29%** | -0.23% |
| CAGR | 9.81% | **16.04%** | -0.07% |
| Sharpe | 0.633 | **0.756** | 0.119 |
| MaxDD | **-12.66%** | -21.40% | -32.91% |
| Calmar | 0.775 | **0.750** | -0.002 |
| Profit Factor | 1.318 | **1.283** | 1.049 |
| Num Trades | 23 | **30** | 31 |
| Avg Trade Return | 0.233% | **0.218%** | 0.040% |
| Exposure | 13.6% | **23.3%** | 26.1% |

### 关键发现：

#### ✅ E8 是 PnL 赢家
- 总收益 **+64.29%** vs E1 的 +36.67%，提升 75%
- CAGR **16.04%** vs 9.81%，提升 63%
- Sharpe **0.756** vs 0.633，提升 19%
- 交易数 30 笔（vs 23），统计显著性更强

#### ⚠️ E8 的 MaxDD 更大
- MaxDD -21.40% vs E1 的 -12.66%，回撤控制变差
- Calmar 基本持平 (0.75 vs 0.78)，因为 CAGR 提升补偿了 MaxDD
- 这是因为暴露度从 13.6% → 23.3%，更多持仓 = 更多风险

#### ❌ E9 PnL 失败
- 尽管 Kappa 最高 (0.832)，但收益几乎为零
- 原因：X=3%/RSI=50 的低阈值产生太多信号 (382 vs E8 的 242)
- 过多的低质量信号稀释了 Alpha
- **重要教训：分类指标高 ≠ PnL 高，别被 Kappa 骗了**

---

## 五、E8 止盈变体深入分析

值得注意的是 E8 的 **纯止盈变体**（不启用 regime 开关）：

| 指标 | E1 止盈 | E8 止盈 | 变化 |
|------|---------|---------|------|
| Total Return | +68.79% | **+142.23%** | +107% |
| CAGR | 16.99% | **30.36%** | +79% |
| Sharpe | 0.766 | **1.020** | +33% |
| MaxDD | -24.68% | **-26.03%** | 略差 |
| Calmar | 0.688 | **1.166** | +70% |
| Num Trades | 14 | 20 | +43% |

这个变体的 **Sharpe > 1.0, Calmar > 1.0** 非常强劲！

---

## 六、特征重要性 (E8)

| 排名 | 特征 | 重要度 |
|------|------|--------|
| 1 | funding_rate_14 | 166 |
| 2 | high_50d_dist | 84 |
| 3 | low_50d_dist | 57 |
| 4 | return_3d | 46 |
| 5 | return_14d | 39 |

特征结构合理：
- `funding_rate_14` 仍然是第一（与 E1 一致）
- `high_50d_dist` / `low_50d_dist` 排名靠前，与 touch 标签的 high 价格逻辑相符
- 无污染特征出现（rsi/sma 已移除）

---

## 七、数据泄露审计

Kappa 0.75 较高，按 CLAUDE.md 规范需检查泄露风险：

| 检查项 | 结果 |
|--------|------|
| 标签是否使用未来数据? | ✅ 标签用 future high，但仅用于生成标签而非特征 |
| 特征是否包含标签信息? | ✅ rsi/sma 已去除（去污染） |
| 正例率是否合理? | ✅ ~21% 正例率合理（touch 比 endpoint 容易） |
| F1=0 folds 分布? | ✅ 集中在 fold 17-19, 35-36, 45-48，对应牵强牛市无标签区间 |
| Sharpe > 3.0? | ✅ 最高 Sharpe = 1.02，在合理范围 |

**结论：未发现泄露迹象。** Kappa 提升的核心原因是 touch 标签的正例率更高、类别更平衡、且与策略逻辑对齐。

---

## 八、结论与建议

### 8.1 核心结论

1. **标签对齐有效**：touch_filtered 标签显著提升了分类和 PnL 表现
2. **E8 是最佳候选**：Kappa 0.751 + CAGR 16% + Sharpe 0.76 + F1=0 仅 16%
3. **E9 警示**：分类指标高不等于 PnL 高，低阈值过度产生信号
4. **MaxDD 音差**：E8 的 -21.4% vs E1 的 -12.7%，需在生产中关注

### 8.2 下一步建议

| 优先级 | 行动 | 说明 |
|--------|------|------|
| 🟢 P0 | E8 进入 paper trading | 与 E1 并行跑，用真实数据验证 |
| 🟡 P1 | E8 regime 阈值调优 | 尝试更严的 regime 开关压制 MaxDD |
| 🟡 P1 | E8 概率校准 | Platt/Isotonic 校准后按概率分仓 |
| 🟢 P2 | 成本压力测试 | 0.1%→0.3% 单边，确认 PF 稳健 |
| 🟢 P2 | Bootstrap 显著性 | 对 E8 止盈变体做随机基线检验 |

### 8.3 生产路径建议

如果 E8 通过 paper trading 验证：
- 晒升为 `models/production/e8-touch-conservative`
- 止盈变体 Sharpe 1.02 可考虑作为第二候选

---

## 附：实验产物

| 文件 | 路径 |
|------|------|
| E8 实验 | `experiments/weekly/weekly_bear_v0305_E8_touch_label/` |
| E9 实验 | `experiments/weekly/weekly_bear_v0305_E9_touch_low_threshold/` |
| E8 配置 | `configs/experiments/weekly/exp_weekly_bear_v0305_E8_touch_label.yaml` |
| E9 配置 | `configs/experiments/weekly/exp_weekly_bear_v0305_E9_touch_low_threshold.yaml` |
| 标签策略 | `src/labels/touch_filtered.py` |
| 本报告 | `experiments/weekly/v0305_touch_label_experiment_report.md` |

---

*报告生成时间: 2026-03-05*
