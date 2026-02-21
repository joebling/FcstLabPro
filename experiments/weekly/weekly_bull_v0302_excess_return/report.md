# weekly_bull_v0302_excess_return

> 实验日期: 2026-02-21
> Label 策略: excess_return

---

## 一、实验配置

| 参数 | 值 |
|------|-----|
| Label 策略 | excess_return |
| 预测窗口 T | 21 |
| 初始训练集 | 800 |
| OOS 窗口 | 63 |
| Step | 21 |
| Purge Gap | 21 |
| 特征数 | 148 |
| 模型 | orion_bix |

---

## 二、评估指标

| 指标 | 值 |
|------|-----|
| Cohen's Kappa (平均) | 0.0693 |
| Cohen's Kappa (整体) | 0.0850 |
| Accuracy | 0.5516 |
| F1 Binary | 0.3182 |
| 正 Kappa 比例 | 55.2% |
| Fold 数 | 58 |

---

## 三、特征集

technical, volume, flow, market_structure, external_fgi, regime

---

*报告生成: 2026-02-21T04:59:44.885906*
