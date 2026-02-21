# exp04_advanced: 高级特性结果

**日期**: 2026-02-21

## 使用的最佳参数

| 参数 | 值 |
|------|-----|
| prob_threshold | 0.8 |
| dip_threshold | 0.05 |
| tp | 0.04 |
| sl | 0.03 |
| monitor_days | 7 |

## Position Sizing 策略

| 策略 | 描述 |
|------|------|
| PS1_fixed | 固定 100% |
| PS2_linear | size = 2 * (prob - 0.5) |
| PS3_kelly | Kelly fraction, cap 30% |

## 风险控制策略

| 策略 | 描述 |
|------|------|
| RC1_none | 无风险控制 |
| RC2_dd_cutoff | Max DD cutoff 20% |

## 指标汇总

| strategy | sharpe | total_return | max_dd | win_rate | annual_return | annual_vol | num_trades |
|----------|--------|--------------|--------|----------|---------------|------------|------------|
| PS1_fixed_RC1_none | 0.7736 | 2.0968 | 0.1078 | 0.0383 | 0.0841 | 0.1124 | 50 |
| PS1_fixed_RC2_dd_cutoff | 0.7736 | 2.0968 | 0.1078 | 0.0383 | 0.0841 | 0.1124 | 50 |
| PS2_linear_RC1_none | 0.9472 | 0.5734 | 0.0375 | 0.0258 | 0.0329 | 0.0348 | 50 |
| PS2_linear_RC2_dd_cutoff | 0.9472 | 0.5734 | 0.0375 | 0.0258 | 0.0329 | 0.0348 | 50 |
| PS3_kelly_RC1_none | 0.8682 | 0.3095 | 0.0302 | 0.0258 | 0.0195 | 0.0225 | 50 |
| PS3_kelly_RC2_dd_cutoff | 0.8682 | 0.3095 | 0.0302 | 0.0258 | 0.0195 | 0.0225 | 50 |

## 最佳策略

**策略**: PS2_linear_RC1_none
**Sharpe**: 0.9472
**MaxDD**: 0.0375
**总收益**: 0.5734

---
