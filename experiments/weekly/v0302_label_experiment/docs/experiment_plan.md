# v0302 Label 策略优化实验计划

**日期**: 2026-02-21  
**目标**: 将 dip_recovery 转化为可套利的收益结构

---

## 实验整体架构

```
experiments/weekly/v0302_label_experiment/
├── exp01_mvp/                    # 阶段1: MVP 验证
├── exp02_prob_layered/               # 阶段2: 概率分层
├── exp03_param_opt/             # 阶段3: 参数优化
├── exp04_advanced/               # 阶段4: 高级特性
└── exp05_cross_asset/            # 阶段5: 跨资产验证
```

---

## 阶段 1: MVP 验证

**实验名称**: `exp01_mvp`

**目标**: 快速验证核心思路

**实验目的**:
- 验证"等待 dip 再入场"是否改善收益

**对比方案**:

| 方案 ID | 方案名称 | 描述 |
|---------|----------|------|
| S1 | baseline | 原始直接持有（参考）|
| S2 | trigger_a | Trigger 方案 A：等待 dip ≥4% |
| S3 | trigger_a_fixed | Trigger A + 固定持仓14天 |

**核心参数**:
```
prob_threshold: 0.7
dip_threshold: 0.04
tp: 0.06
sl: 0.05
time_stop: 14
monitor_days: 10
```

**输出指标**:
- Sharpe
- MaxDD
- 总收益
- WinRate
- 交易次数

**成功标准**:
```
至少一个方案 Sharpe > 0.5
MaxDD < 50%
```

**文件结构**:
```
exp01_mvp/
├── backtest_mvp.py
├── results_mvp.md
└── plots/
    └── strategy_comparison.png
```

---

## 阶段 2: 概率分层测试

**实验名称**: `exp02_prob_layered`

**目标**: 验证概率的单调性

**实验目的**:
- 验证 Sharpe 是否随 prob 上升而单调上升

**分组方案**:

| 分组 ID | 分组名称 | 描述 |
|---------|----------|------|
| P1 | top_20 | prob 最高 20% |
| P2 | top_30 | prob 最高 30% |
| P3 | top_50 | prob 最高 50% |
| P4 | all | 全部 |

**输出指标**:
- 每个分组的 Sharpe
- 每个分组的 MaxDD
- 每个分组的总收益

**成功标准**:
```
Sharpe(top_20) > Sharpe(top_30) > Sharpe(top_50)
```

**文件结构**:
```
exp02_prob_layered/
├── backtest_prob_layered.py
├── results_prob_layered.md
└── plots/
    └── prob_layered_sharpe.png
```

---

## 阶段 3: 参数优化

**实验名称**: `exp03_param_opt`

**目标**: 找到最优参数组合

**参数扫描空间**:

| 参数 | 扫描范围 |
|------|---------|
| `prob_threshold` | 0.6, 0.7, 0.8 |
| `dip_threshold` | 0.03, 0.04, 0.05 |
| `tp` | 0.04, 0.06, 0.08 |
| `sl` | 0.03, 0.05, 0.07 |
| `monitor_days` | 7, 10, 14 |

**扫描策略**:
- 网格搜索（Grid Search）
- 共 3×3×3×3×3 = 243 组合

**输出指标**:
- 每个参数组合的 Sharpe
- 每个参数组合的 MaxDD
- 每个参数组合的总收益
- 每个参数组合的 Calmar Ratio (Sharpe / MaxDD)

**成功标准**:
```
找到最优参数组合
Sharpe > 0.8
MaxDD < 40%
```

**文件结构**:
```
exp03_param_opt/
├── backtest_param_opt.py
├── param_scan_results.csv
├── results_param_opt.md
└── plots/
    ├── param_sensitivity.png
    └── optimal_strategy.png
```

---

## 阶段 4: 高级特性

**实验名称**: `exp04_advanced`

**目标**: 提升策略表现

**子实验**:

### 4.1 Position Sizing

| 方案 ID | 方案名称 | 描述 |
|---------|----------|------|
| PS1 | fixed_01 | 固定 100% |
| PS2 | linear | size = 2 * (prob - 0.5) |
| PS3 | kelly | Kelly fraction, cap 30% |

### 4.2 风险控制

| 方案 ID | 方案名称 | 描述 |
|---------|----------|------|
| RC1 | none | 无风险控制 |
| RC2 | vol_target | Volatility targeting |
| RC3 | dd_cutoff | Max DD cutoff 20% |
| RC4 | loss_pause | 连续亏损暂停 |

### 4.3 收益归因

分解收益来源:
- 入场 timing alpha
- 持仓 beta
- 波动环境贡献

**输出指标**:
- 每个方案的 Sharpe
- 每个方案的 MaxDD
- 收益归因结果

**文件结构**:
```
exp04_advanced/
├── backtest_position_sizing.py
├── backtest_risk_control.py
├── pnl_decomposition.py
├── results_advanced.md
└── plots/
    ├── position_sizing.png
    ├── risk_control.png
    └── pnl_decomposition.png
```

---

## 阶段 5: 跨资产验证

**实验名称**: `exp05_cross_asset`

**目标**: 验证策略的普适性

**测试资产**:

| 资产 | 数据路径 |
|------|---------|
| BTCUSDT | 已有 |
| ETHUSDT | 需要获取 |
| SOLUSDT | 需要获取 |

**验证内容**:
- 在每个资产上回测最优策略
- 比较跨资产的表现一致性

**成功标准**:
```
至少 2 个资产 Sharpe > 0.6
```

**文件结构**:
```
exp05_cross_asset/
├── load_cross_asset.py
├── backtest_cross_asset.py
├── results_cross_asset.md
└── plots/
    └── cross_asset_comparison.png
```

---

## 共用模块设计

### 共用模块:
```
src/
├── backtest/
│   ├── __init__.py
│   ├── engine.py          # 回测引擎
│   ├── triggers.py        # 触发逻辑
│   ├── exits.py           # 退出逻辑
│   └── metrics.py        # 指标计算
└── visualization/
    ├── __init__.py
    └── plotter.py       # 绘图
```

---

## 实验执行顺序

1. ✅ **exp01_mvp** (1-2 天)
2. ✅ **exp02_prob_layered** (1 天)
3. ✅ **exp03_param_opt** (2-3 天)
4. ✅ **exp04_advanced** (3-5 天)
5. ✅ **exp05_cross_asset** (2-3 天)

---

## 最终成功标准（严格版）

必须同时满足：

```
OOS Sharpe > 1.2
MaxDD < 35%
收益单调随 prob 上升
跨 ETH 仍有效
```

否则：
> 不进入实盘。

---

## 预期时间估算

| 阶段 | 时间 |
|------|------|
| 1 | 1-2 天 |
| 2 | 1 天 |
| 3 | 2-3 天 |
| 4 | 3-5 天 |
| 5 | 2-3 天 |
| **总计** | **9-14 天 |

---
