# exp01_mvp: MVP 验证结果

**日期**: 2026-02-21

## 回测方案

| 方案 ID | 方案名称 | 描述 |
|---------|----------|------|
| S1 | S1_baseline | 原始直接持有 |
| S2 | S2_trigger_a | Trigger 方案 A + TP/SL |
| S3 | S3_trigger_a_fixed | Trigger 方案 A + 固定持仓14天 |

## 指标汇总

| strategy | sharpe | total_return | max_dd | win_rate | annual_return | annual_vol | num_trades |
|----------|--------|--------------|--------|----------|---------------|------------|------------|
| S1_baseline | 0.4914 | 4.0773 | 0.3731 | 0.4970 | 0.1231 | 0.4972 | 1 |
| S2_trigger_a | 0.1811 | 0.2419 | 0.3686 | 0.1012 | 0.0156 | 0.1950 | 88 |
| S3_trigger_a_fixed | 0.3499 | 1.2335 | 0.3159 | 0.1381 | 0.0591 | 0.2678 | 69 |

## 结果分析

**最佳 Sharpe**: S1_baseline (0.4914)

## 成功标准

- Sharpe > 0.5
- MaxDD < 50%

- S1_baseline: ❌ 未通过
- S2_trigger_a: ❌ 未通过
- S3_trigger_a_fixed: ❌ 未通过

---
