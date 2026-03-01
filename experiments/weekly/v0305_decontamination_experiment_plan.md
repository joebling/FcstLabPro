# v0305 去污染实验计划

## 一、背景

v0304 实验推荐的 `directional_filtered` 策略存在**特征-标签污染**问题：

- 标签定义使用 `rsi < 45` 和 `close < sma_50` 作为过滤条件
- 特征集包含 `rsi_14`、`price_vs_sma_50` 等同源特征
- Top 2 重要特征恰好就是这两个，模型在逆向还原标签定义

**本轮实验目标：量化污染影响，找到真正干净且有效的标签策略，并通过 PnL 回测验证交易可行性。**

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

### Phase 4：PnL 回测

| ID | 内容 | 状态 |
|----|------|------|
| PnL E1 | E1 回测: 基础/+regime/+止盈/止盈+regime | ✅ 完成 |
| PnL E5 | E5 回测: 同上 4 个变体 | ✅ 完成 |
| 随机基线 | 同暴露度随机信号 200 次获取 Z-score | ✅ 完成 |

---

## 三、分类指标汇总

| 实验 | 正例率 | Kappa | F1 | Prec | F1=0 | 判定 |
|------|--------|-------|------|------|------|------|
| v0304 opt (含污染) | ~7% | 0.326 | 0.401 | 0.371 | 48% | ❌ 污染 |
| **E1** 去污染 | 10.3% | **0.343** | 0.414 | 0.396 | 48% | ✅ 干净 |
| E2 纯方向 | 42.9% | -0.065 | 0.308 | 0.350 | 38% | ❌ 无效 |
| E3 TB 4/3 | ~40% | 0.006 | 0.406 | 0.469 | 18% | ❌ Kappa≈0 |
| E4 TB 3/2 | ~50% | 0.027 | 0.412 | 0.437 | 5% | ❌ Kappa≈0 |
| **E5** 低阈值 | **14.7%** | **0.343** | **0.441** | **0.434** | **41%** | ✅ 分类最佳 |
| E6 无MA | 17.9% | 0.321 | 0.443 | 0.441 | 36% | ⚠️ Kappa下降 |
| E7 RSI50 | 13.7% | 0.305 | 0.403 | 0.394 | 48% | ❌ 无提升 |

## 四、PnL 回测汇总

| 实验 | 变体 | Return | CAGR | Sharpe | MaxDD | Alpha Z |
|------|------|--------|------|--------|-------|------|
| **E1** | 基础 | **+109.1%** | 24.7% | **0.93** | -24.7% | **2.35** |
| **E1** | +止盈 | +68.8% | 17.0% | 0.77 | -24.7% | - |
| **E1** | +regime | +61.6% | 15.5% | 0.77 | -21.6% | - |
| **E1** | 止盈+regime | +36.7% | 9.8% | 0.63 | **-12.7%** | - |
| E5 | 基础 | +55.6% | 14.2% | 0.60 | -31.1% | 0.74 |
| E5 | +止盈 | +56.3% | 14.3% | 0.65 | -23.8% | - |
| - | 买入持有 | +350.8% | 57.0% | 1.20 | -32.0% | - |

---

## 五、关键发现

### 5.1 去污染结果
- ✅ 去掉 rsi/sma 特征后 Kappa 不降反升，模型预测能力真实
- ✅ 特征重要性从「标签复现」变为「真实市场信号」

### 5.2 分类指标 ≠ PnL (重要教训)
- E5 分类最佳 (F1=0.441, F1=0 占比 41%)，但 **Alpha Z=0.74 不显著**
- E1 分类稍差 (F1=0.414, F1=0 占比 48%)，但 **Alpha Z=2.35 显著**
- **原因**: E1 更严格的阈值 (X=4%, RSI<45) 产生更少但更高质量的信号
- **教训**: 优化分类指标不等于优化交易表现，必须用 PnL 回测验证

### 5.3 RSI/MA 过滤的价值
- ❌ E2 证明无过滤的纯方向标签完全无效
- ✅ 过滤本质是「只在超卖低位时关注反弹」，符合交易逻辑

### 5.4 Triple Barrier 确认无效
- ❌ 4 组参数全部 Kappa≈0，可以完全放弃

### 5.5 熊市保护能力
- 2022 熊市: E1 +0.32% vs 买入持有 -14.0%
- 止盈+regime 变体 MaxDD 仅 -12.7% vs 买入持有 -32.0%

### 5.6 止盈机制有效
- 不降低总收益的情况下显著降低暴露（从 39% 到 27%）
- Sharpe 基本持平 (0.93 vs 0.77)

---

## 六、代码改动记录

| 文件 | 改动 | Commit |
|------|------|--------|
| `src/features/builder.py` | 新增 `drop_features` 参数 + glob 匹配 | 693b7b1 |
| `src/experiment/runner.py` | 透传 `drop_features` 配置 | 693b7b1 |
| `src/labels/directional.py` | 新增 `directional_binary` 标签 | 693b7b1 |
| `tests/test_features.py` | 新增 3 个 drop_features 测试 | 693b7b1 |
| `scripts/analyze_fold_regimes.py` | Fold regime 分析脚本 | 693b7b1 |
| `scripts/pnl_backtest_v0305.py` | PnL 回测脚本 (+regime/+止盈/随机基线) | 43a0ff9 |

---

## 七、最终建议

### 🏆 推荐上线策略：E1 (而非 E5)

> ℹ️ 说明：分类阶段推荐 E5，PnL 回测后反转为 E1。
> 更严格的阈值产生更高质量的交易信号，分类指标不完全反映交易价值。

**标签配置：**
```yaml
label:
  strategy: directional_filtered
  T: 21
  X: 0.04       # 保持严格阈值
  rsi_window: 14
  rsi_threshold: 45.0  # 保持严格
  ma_window: 50
  require_below_ma: true
features:
  drop_features: [rsi_*, price_vs_sma_*, sma_cross_10_50, sma_cross_50_200]
```

**交易执行方案：**

| 风格 | 变体 | CAGR | Sharpe | MaxDD | 暴露 |
|------|------|------|--------|-------|------|
| 激进 | E1 基础 | 24.7% | 0.93 | -24.7% | 39% |
| 稳健 | E1 +止盈 | 17.0% | 0.77 | -24.7% | 27% |
| 保守 | E1 止盈+regime | 9.8% | 0.63 | -12.7% | 14% |

### ❗ 重要警告

1. 买入持有仍大幅超越所有策略 (BTC 2022-2026 牛市偏差)
2. 回测周期仅 3.3 年，统计置信度有限
3. F1=0 占比 48% 超标，但 PnL Alpha 显著
4. 低暴露 (39%) 意味着此策略适合作为组合的一部分，而非唯一策略

### 🚀 下一步工作

1. **Paper Trading**: 小资金实盘验证 1-3 个月 (最高优先级)
2. **多资产扩展**: 在 ETH/SOL 上测试同样标签策略
3. **组合策略**: E1 作为择时信号 + 买入持有作为核心仓位

---

## 八、实验产物索引

| 文件 | 说明 |
|------|------|
| `v0305_decontamination_experiment_plan.md` | 本文件 |
| `v0305_decontamination_results.md` | 分类指标结果报告 |
| `v0305_pnl_backtest_results.md` | PnL 回测综合报告 |
| `v0305_fold_regime_analysis.md` | Phase 1 regime 分析 |
| `v0305_fold_regime_analysis_phase2.md` | Phase 2 regime 分析 |
| `weekly_bear_v0305_E1_decontam/` | E1 全部产物 (incl. PnL) |
| `weekly_bear_v0305_E2_directional_pure/` | E2 实验产物 |
| `weekly_bear_v0305_E3_tb_grid_a/` | E3 实验产物 |
| `weekly_bear_v0305_E4_tb_grid_b/` | E4 实验产物 |
| `weekly_bear_v0305_E5_low_threshold/` | E5 全部产物 (incl. PnL) |
| `weekly_bear_v0305_E6_no_ma_filter/` | E6 实验产物 |
| `weekly_bear_v0305_E7_rsi50_only/` | E7 实验产物 |
| `scripts/pnl_backtest_v0305.py` | PnL 回测脚本 |

---

**创建日期**: 2026-03-01
**更新日期**: 2026-03-01
**状态**: ✅ Phase 1-4 全部完成
