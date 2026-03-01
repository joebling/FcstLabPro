# v0305 去污染实验计划

## 一、背景

v0304 实验推荐的 `directional_filtered` 策略存在**特征-标签污染**问题：

- 标签定义使用 `rsi < 45` 和 `close < sma_50` 作为过滤条件
- 特征集包含 `rsi_14`、`price_vs_sma_50` 等同源特征
- Top 2 重要特征恰好就是这两个，模型在逆向还原标签定义
- Kappa = 0.326 中有多少来自真实预测能力，多少来自污染，未知

**本轮实验目标：量化污染影响，找到真正干净且有效的标签策略。**

---

## 二、实验矩阵

### Phase 1：去污染验证 + Triple Barrier 深度调参

| ID | 实验名 | 标签 | 改动 | 目的 | 状态 |
|----|--------|------|------|------|------|
| E1 | decontam | directional_filtered (X=4%,RSI=45) | 移除 rsi/sma 特征 | 量化污染影响 | ✅ 完成 |
| E2 | directional_pure | directional_binary (X=4%) | 无 RSI/MA 过滤 | 对照组 | ✅ 完成 |
| E3 | tb_grid_a | triple_barrier_simple | pt=4%/sl=3% | TB 调参 | ✅ 完成 |
| E4 | tb_grid_b | triple_barrier_simple | pt=3%/sl=2% | TB 调参 | ✅ 完成 |

### Phase 2：降低阈值提高正例率

| ID | 实验名 | 标签参数 | 目的 | 状态 |
|----|--------|---------|------|------|
| E5 | low_threshold | X=3%,RSI=50,MA=50,去污染 | 提高正例率 | ✅ 完成 |
| E6 | no_ma_filter | X=3%,RSI=50,noMA,去污染 | 去掉 MA 过滤 | ✅ 完成 |
| E7 | rsi50_only | X=4%,RSI=50,MA=50,去污染 | 仅放宽 RSI | ✅ 完成 |

### Phase 3：Fold Regime 分析

| ID | 内容 | 状态 |
|----|------|------|
| Regime P1 | E1/E3/E4 的 fold regime 标注 | ✅ 完成 |
| Regime P2 | E5/E6 的 fold regime 标注 | ✅ 完成 |

---

## 三、实验结果汇总

| 实验 | 正例率 | Kappa | F1 | Prec | F1=0 | 判定 |
|------|--------|-------|------|------|------|------|
| v0304 opt (含污染) | ~7% | 0.326 | 0.401 | 0.371 | 48% | ❌ 污染 |
| **E1** 去污染 | 10.3% | **0.343** | 0.414 | 0.396 | 48% | ✅ 干净 |
| E2 纯方向 | 42.9% | -0.065 | 0.308 | 0.350 | 38% | ❌ 无效 |
| E3 TB 4/3 | ~40% | 0.006 | 0.406 | 0.469 | 18% | ❌ Kappa≈0 |
| E4 TB 3/2 | ~50% | 0.027 | 0.412 | 0.437 | 5% | ❌ Kappa≈0 |
| **E5** 低阈值 ⭐ | **14.7%** | **0.343** | **0.441** | **0.434** | **41%** | ✅ 最佳 |
| E6 无MA | 17.9% | 0.321 | 0.443 | 0.441 | 36% | ⚠️ Kappa下降 |
| E7 RSI50 | 13.7% | 0.305 | 0.403 | 0.394 | 48% | ❌ 无提升 |

---

## 四、关键发现

### 4.1 去污染结果
- ✅ 去掉 rsi/sma 特征后 Kappa 不降反升，模型预测能力真实
- ✅ 特征重要性从「标签复现」变为「真实市场信号」

### 4.2 RSI/MA 过滤的价值
- ❌ E2 证明无过滤的纯方向标签完全无效 (Kappa=-0.065)
- ✅ RSI/MA 过滤显著提升标签质量，不是“事后诸葛亮”
- ✅ 过滤本质是「只在超卖低位时关注反弹」，符合交易逻辑

### 4.3 Triple Barrier 确认无效
- ❌ 4 组参数 (pt=3-6%, sl=2-4%) 全部 Kappa≈0
- 可能原因：BTC 日线波动太大，简单止盈止损难以区分有效信号

### 4.4 正例率与稳定性的关系
- 7% → 10% → 15%，F1=0 占比 48% → 48% → 41%
- 18% (E6, 去 MA)，F1=0 降到 36%，但 Kappa 也降
- 正例率和 Kappa 存在 trade-off

### 4.5 Regime 分析
- Bull: Kappa=0.37, F1>0 占比=65% — 最有效
- Bear: E1 Kappa=0.14, F1>0=27% → E5 Kappa=0.17, F1>0=60% — 显著改善
- 熊市失灵是结构性问题，需要 regime 开关解决

---

## 五、代码改动记录

| 文件 | 改动 | Commit |
|------|------|--------|
| `src/features/builder.py` | 新增 `drop_features` 参数 + glob 匹配 | 693b7b1 |
| `src/experiment/runner.py` | 透传 `drop_features` 配置 | 693b7b1 |
| `src/labels/directional.py` | 新增 `directional_binary` 标签 | 693b7b1 |
| `tests/test_features.py` | 新增 3 个 drop_features 测试 | 693b7b1 |
| `scripts/analyze_fold_regimes.py` | Fold regime 分析脚本 | 693b7b1 |

---

## 六、最终建议

### 🏆 推荐上线策略：E5 + Regime 开关

**标签配置：**
```yaml
label:
  strategy: directional_filtered
  T: 21
  X: 0.03
  rsi_window: 14
  rsi_threshold: 50.0
  ma_window: 50
  require_below_ma: true
features:
  drop_features: [rsi_*, price_vs_sma_*, sma_cross_10_50, sma_cross_50_200]
```

**上线条件：**
- 仅在非熊市环境下启用（滚动 63 天收益率 > -10%）
- 熊市中模型静默

### 🚀 下一步工作

1. **Regime 开关集成**：在 inference pipeline 中加入 regime detection
2. **PnL 回测**：对 E5 做交易回测，加入交易成本、滑点
3. **Paper Trading**：小资金实盘验证 1-3 个月

---

## 七、实验产物索引

| 文件 | 说明 |
|------|------|
| `experiments/weekly/v0305_decontamination_experiment_plan.md` | 本文件 |
| `experiments/weekly/v0305_decontamination_results.md` | 结果报告 |
| `experiments/weekly/v0305_fold_regime_analysis.md` | Phase 1 regime 分析 |
| `experiments/weekly/v0305_fold_regime_analysis_phase2.md` | Phase 2 regime 分析 |
| `experiments/weekly/weekly_bear_v0305_E1_decontam/` | E1 实验产物 |
| `experiments/weekly/weekly_bear_v0305_E2_directional_pure/` | E2 实验产物 |
| `experiments/weekly/weekly_bear_v0305_E3_tb_grid_a/` | E3 实验产物 |
| `experiments/weekly/weekly_bear_v0305_E4_tb_grid_b/` | E4 实验产物 |
| `experiments/weekly/weekly_bear_v0305_E5_low_threshold/` | E5 实验产物 |
| `experiments/weekly/weekly_bear_v0305_E6_no_ma_filter/` | E6 实验产物 |
| `experiments/weekly/weekly_bear_v0305_E7_rsi50_only/` | E7 实验产物 |

---

**创建日期**: 2026-03-01
**更新日期**: 2026-03-01
**状态**: ✅ 全部完成
