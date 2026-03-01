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

共 5 组实验，分 3 个 Phase：

### Phase 1：去污染验证（核心）

| ID | 实验名 | 标签策略 | 改动 | 目的 |
|----|--------|---------|------|------|
| E1 | `directional_filtered_decontam` | directional_filtered (X=4%, RSI=45) | 从特征集中移除 rsi_*, price_vs_sma_* | 量化污染对 Kappa 的贡献 |
| E2 | `directional_pure` | directional（纯方向） | Label=1 if future_return >= 4%, 无 RSI/MA 过滤 | 对照：过滤条件到底有没有用 |

**判定逻辑：**
- 若 E1 的 Kappa ≈ E_opt（0.326），说明污染影响小，模型真的学到了 pattern → 好消息
- 若 E1 的 Kappa 大幅下降（< 0.15），说明之前的"预测能力"主要来自污染 → 标签需重新设计
- E2 作为 ablation：如果纯方向标签 Kappa ≥ E1，说明 RSI/MA 过滤无额外价值

### Phase 2：Triple Barrier 深度调参

| ID | 实验名 | 标签策略 | 参数 | 目的 |
|----|--------|---------|------|------|
| E3 | `triple_barrier_grid_a` | triple_barrier_simple | pt=4%, sl=3% | 降低阈值，增加正例率 |
| E4 | `triple_barrier_grid_b` | triple_barrier_simple | pt=3%, sl=2% | 更激进的低阈值 |

**理由：**
- Triple Barrier 是标签定义最干净的策略（纯交易逻辑，无特征污染）
- v0304 只试了 pt=6%/sl=4% 和 pt=5%/sl=3%，搜索范围太窄
- 目前 BTC 日线 21 天波动率约 8-15%，pt=6% 可能偏高

### Phase 3：Fold 稳定性诊断

| ID | 实验名 | 内容 | 目的 |
|----|--------|------|------|
| E5 | `fold_regime_analysis` | 对 E1/E3/E4 的 fold 结果做市场 regime 标注 | 理解哪些市场环境下模型失灵 |

---

## 三、实验配置

### 3.1 公共配置（不变）

```yaml
data:
  source: binance
  symbol: BTCUSDT
  interval: 1d
  start: '2018-01-01'
  end: '2025-12-31'

model:
  type: lightgbm
  params:
    n_estimators: 100
    max_depth: 6
    learning_rate: 0.05
    num_leaves: 31
    subsample: 0.8
    colsample_bytree: 0.8
    min_child_samples: 20
    reg_alpha: 0.1
    reg_lambda: 0.1
    random_state: 42
    auto_scale_pos_weight: true

evaluation:
  method: walk_forward
  init_train: 800
  oos_window: 63
  step: 21
  purge_gap: 21

seed: 42
```

### 3.2 E1: directional_filtered_decontam

```yaml
features:
  sets: [technical, volume, flow, market_structure, external_fgi]
  drop_features:           # ← 新增：显式排除污染特征
    - rsi_6
    - rsi_14
    - rsi_28
    - price_vs_sma_20
    - price_vs_sma_50
    - price_vs_sma_200
    # 以下是 rsi/sma 的滞后/滚动衍生特征（如果存在）
    - rsi_14_lag_*
    - rsi_14_roll_*

label:
  strategy: directional_filtered
  T: 21
  X: 0.04
  rsi_window: 14
  rsi_threshold: 45.0
  ma_window: 50
  require_below_ma: true
```

### 3.3 E2: directional_pure

```yaml
features:
  sets: [technical, volume, flow, market_structure, external_fgi]
  # 完整特征集，不排除任何特征（因为标签不依赖 RSI/SMA）

label:
  strategy: directional          # 纯方向标签，无过滤
  T: 21
  X: 0.04
```

### 3.4 E3: triple_barrier_grid_a

```yaml
features:
  sets: [technical, volume, flow, market_structure, external_fgi]

label:
  strategy: triple_barrier_simple
  T: 21
  pt: 0.04
  sl: 0.03
  include_today: false
```

### 3.5 E4: triple_barrier_grid_b

```yaml
features:
  sets: [technical, volume, flow, market_structure, external_fgi]

label:
  strategy: triple_barrier_simple
  T: 21
  pt: 0.03
  sl: 0.02
  include_today: false
```

---

## 四、评估标准

### 4.1 上线门槛（必须全部满足）

| 指标 | 门槛 | 说明 |
|------|------|------|
| Cohen's Kappa（均值） | ≥ 0.20 | 至少 Fair 级别 |
| F1=0 的 fold 占比 | ≤ 30% | 信号稳定性 |
| Precision | ≥ 0.30 | 信号可信度 |
| 无特征-标签污染 | ✅ | Top 特征不应是标签过滤条件的直接复现 |
| 正例率 | 5% ~ 40% | 太低学不到，太高无意义 |

### 4.2 择优标准（满足门槛后）

优先级排序：
1. **Kappa 最高**（预测能力）
2. **Fold 稳定性最好**（F1>0 的 fold 占比高、Kappa 标准差低）
3. **标签定义最干净**（无任何形式的 leakage）
4. **Precision 最高**（宁可少出信号也不误报）

---

## 五、执行计划

```
Phase 1（优先，~2h）
├── E1: directional_filtered_decontam
└── E2: directional_pure
    ↓
    根据结果决定是否继续 Phase 2
    - 如果 E1 Kappa ≥ 0.25 → 污染影响小，directional_filtered 仍可用
    - 如果 E1 Kappa < 0.15 → 放弃 directional_filtered，全力 Phase 2

Phase 2（~2h，可与 Phase 1 并行）
├── E3: triple_barrier pt=4%/sl=3%
└── E4: triple_barrier pt=3%/sl=2%

Phase 3（~1h，Phase 1+2 完成后）
└── E5: fold regime 分析
```

### 预估总耗时：3-4 小时

---

## 六、需要的代码改动

### 6.1 支持 `drop_features` 配置（E1 需要）

在特征构建流程中增加显式排除特征的能力：

```python
# 在 feature pipeline 中增加
if config.get("features", {}).get("drop_features"):
    drop_cols = resolve_glob_patterns(config["features"]["drop_features"], df.columns)
    df = df.drop(columns=drop_cols, errors="ignore")
```

### 6.2 确认 `directional` 标签策略存在（E2 需要）

检查 `src/labels/directional.py` 是否已注册 `directional` 策略（不带 filtered）。

### 6.3 Fold Regime 标注脚本（E5 需要）

新建 `scripts/analyze_fold_regimes.py`：
- 输入：实验结果目录
- 对每个 fold 的时间段标注市场 regime（bull/bear/sideways）
- 输出：regime vs. Kappa 的交叉分析表

---

## 七、风险与备选

| 风险 | 可能性 | 应对 |
|------|--------|------|
| 所有去污染后 Kappa < 0.15 | 中 | 转向回归任务（预测收益率）或增加特征维度 |
| Triple Barrier 仍然 Kappa ≈ 0 | 中 | 考虑日内数据（4h/1h）或更短 T |
| 正例率过低导致训练不稳定 | 低 | 使用 SMOTE 或调整 scale_pos_weight |

---

**创建日期**: 2026-03-01
**前置实验**: v0304_label_strategy_comparison_results.md
**负责人**: Qiu