# 📊 FcstLabPro 实验对比报告

> **生成时间**: 2026-02-13 00:09:17  
> **对比实验数**: 2  
> **平台**: FcstLabPro

---
## 1. 实验概览

| 实验名               | 大类       | 标签                  | 描述                         |   特征集数 | 创建时间                | 耗时   | Git     | 状态        |
|:------------------|:---------|:--------------------|:---------------------------|-------:|:--------------------|:-----|:--------|:----------|
| baseline_T14_X8   | default  | baseline, v1        | 基线实验：技术指标+成交量特征，14天窗口，8%阈值 |      2 | 2026-02-12T23:32:03 | 201s | 9c31aa3 | completed |
| baseline_v2_quick | baseline | baseline, v2, quick | 基线v2快速版：全特征但减少folds，用于调试验证 |      7 | 2026-02-12T23:59:41 | 41s  | 1c4ef2b | completed |

---
## 2. 核心指标对比

| 实验                |   accuracy |   cohen_kappa |   f1_macro |   precision_macro |   recall_macro |
|:------------------|-----------:|--------------:|-----------:|------------------:|---------------:|
| baseline_T14_X8   |     0.3745 |        0.0466 |     0.3546 |            0.3619 |         0.3713 |
| baseline_v2_quick |     0.3509 |       -0.013  |     0.3193 |            0.3238 |         0.3231 |

### 指标差异 (实验2 − 实验1)

- **accuracy**: 📉 -0.0237
- **cohen_kappa**: 📉 -0.0596
- **f1_macro**: 📉 -0.0353
- **precision_macro**: 📉 -0.0382
- **recall_macro**: 📉 -0.0482

### 🏆 各指标最佳

- **accuracy**: baseline_T14_X8 (0.3745)
- **cohen_kappa**: baseline_T14_X8 (0.0466)
- **f1_macro**: baseline_T14_X8 (0.3546)
- **precision_macro**: baseline_T14_X8 (0.3619)
- **recall_macro**: baseline_T14_X8 (0.3713)

---
## 3. 配置差异对比

| 配置项                 | baseline_T14_X8   | baseline_v2_quick                                                          | 差异   |
|:--------------------|:------------------|:---------------------------------------------------------------------------|:-----|
| features.sets       | technical, volume | technical, volume, flow, market_structure, onchain, sentiment, lag_rolling | ⚡ 不同 |
| features.sets (数量)  | 2                 | 7                                                                          | ⚡ 不同 |
| label.strategy      | reversal          | reversal                                                                   | ✅ 相同 |
| label.T             | 14                | 14                                                                         | ✅ 相同 |
| label.X             | 0.08              | 0.08                                                                       | ✅ 相同 |
| model.type          | lightgbm          | lightgbm                                                                   | ✅ 相同 |
| model.n_estimators  | 500               | 200                                                                        | ⚡ 不同 |
| model.max_depth     | 6                 | 6                                                                          | ✅ 相同 |
| model.learning_rate | 0.05              | 0.05                                                                       | ✅ 相同 |
| model.num_leaves    | 31                | 31                                                                         | ✅ 相同 |
| model.subsample     | 0.8               | 0.8                                                                        | ✅ 相同 |
| eval.init_train     | 1500              | 1500                                                                       | ✅ 相同 |
| eval.oos_window     | 63                | 63                                                                         | ✅ 相同 |
| eval.step           | 21                | 63                                                                         | ⚡ 不同 |
| seed                | 42                | 42                                                                         | ✅ 相同 |

---
## 4. Walk-Forward Fold 指标对比

### baseline_T14_X8
- Folds 数量: 57
- **accuracy**: mean=0.3745, std=0.1578, min=0.0317, max=0.6984
- **f1_macro**: mean=0.2863, std=0.1097, min=0.0333, max=0.5320
- **cohen_kappa**: mean=0.0616, std=0.1114, min=-0.1647, max=0.3206

### baseline_v2_quick
- Folds 数量: 19
- **accuracy**: mean=0.3509, std=0.1690, min=0.0476, max=0.7460
- **f1_macro**: mean=0.2626, std=0.1040, min=0.0435, max=0.5184
- **cohen_kappa**: mean=0.0163, std=0.1367, min=-0.1667, max=0.4263

### Fold 指标统计汇总对比

| 实验                |   Folds | accuracy (mean±std)   | f1_macro (mean±std)   | cohen_kappa (mean±std)   |
|:------------------|--------:|:----------------------|:----------------------|:-------------------------|
| baseline_T14_X8   |      57 | 0.3745±0.1578         | 0.2863±0.1097         | 0.0616±0.1114            |
| baseline_v2_quick |      19 | 0.3509±0.1690         | 0.2626±0.1040         | 0.0163±0.1367            |

---
## 5. 特征重要性对比

### Top 20 特征

#### baseline_T14_X8 (共 77 个特征)

|   排名 | 特征                |   重要性 | 占比   |
|-----:|:------------------|------:|:-----|
|    1 | sma_cross_50_200  |   989 | 3.0% |
|    2 | low_50d_dist      |   954 | 2.9% |
|    3 | vol_volatility_20 |   832 | 2.5% |
|    4 | price_vs_sma_200  |   808 | 2.4% |
|    5 | atr_pct_21        |   802 | 2.4% |
|    6 | vol_price_corr_20 |   791 | 2.4% |
|    7 | vol_volatility_10 |   768 | 2.3% |
|    8 | obv_sma_20        |   752 | 2.3% |
|    9 | volatility_20d    |   723 | 2.2% |
|   10 | bb_width_20       |   681 | 2.1% |
|   11 | obv               |   665 | 2.0% |
|   12 | obv_sma_10        |   661 | 2.0% |
|   13 | vol_sma_50        |   651 | 2.0% |
|   14 | vol_price_corr_10 |   648 | 2.0% |
|   15 | atr_21            |   602 | 1.8% |
|   16 | low_14d_dist      |   595 | 1.8% |
|   17 | sma_200           |   590 | 1.8% |
|   18 | high_50d_dist     |   584 | 1.8% |
|   19 | low_21d_dist      |   579 | 1.7% |
|   20 | rsi_28            |   560 | 1.7% |

#### baseline_v2_quick (共 340 个特征)

|   排名 | 特征                  |   重要性 | 占比   |
|-----:|:--------------------|------:|:-----|
|    1 | sth_sopr_std30      |   205 | 1.6% |
|    2 | rsi_14_std30        |   145 | 1.1% |
|    3 | sma_cross_50_200    |   134 | 1.0% |
|    4 | buy_pressure_std30  |   132 | 1.0% |
|    5 | lth_sopr_ma30       |   125 | 1.0% |
|    6 | macd_hist_std30     |   121 | 0.9% |
|    7 | low_50d_dist        |   121 | 0.9% |
|    8 | dist_from_low_180d  |   119 | 0.9% |
|    9 | buy_pressure_ma30   |   116 | 0.9% |
|   10 | dist_from_low_365d  |   109 | 0.8% |
|   11 | cvd_ma_21           |   108 | 0.8% |
|   12 | vol_price_corr_20   |   108 | 0.8% |
|   13 | fgi_std30           |   108 | 0.8% |
|   14 | buy_pressure_std14  |   106 | 0.8% |
|   15 | fgi_std14           |   105 | 0.8% |
|   16 | lth_sopr_std30      |   105 | 0.8% |
|   17 | rsi_14_lag14        |   102 | 0.8% |
|   18 | vol_volatility_20   |   101 | 0.8% |
|   19 | liquidity_proxy     |   100 | 0.8% |
|   20 | volume_density_ma30 |   100 | 0.8% |

### 特征重要性交集与差异分析

- **共同 Top20 特征** (4 个): low_50d_dist, sma_cross_50_200, vol_price_corr_20, vol_volatility_20
- **仅 baseline_T14_X8 Top20** (16 个): atr_21, atr_pct_21, bb_width_20, high_50d_dist, low_14d_dist, low_21d_dist, obv, obv_sma_10, obv_sma_20, price_vs_sma_200, rsi_28, sma_200, vol_price_corr_10, vol_sma_50, vol_volatility_10, volatility_20d
- **仅 baseline_v2_quick Top20** (16 个): buy_pressure_ma30, buy_pressure_std14, buy_pressure_std30, cvd_ma_21, dist_from_low_180d, dist_from_low_365d, fgi_std14, fgi_std30, liquidity_proxy, lth_sopr_ma30, lth_sopr_std30, macd_hist_std30, rsi_14_lag14, rsi_14_std30, sth_sopr_std30, volume_density_ma30
- **Jaccard 相似度**: 11.11%

---
## 6. 数据与特征维度

| 实验                | 数据区间                    | 特征集                                                                        |   特征数 | 模型类型     |
|:------------------|:------------------------|:---------------------------------------------------------------------------|------:|:---------|
| baseline_T14_X8   | 2018-01-01 ~ 2025-12-31 | technical, volume                                                          |    77 | lightgbm |
| baseline_v2_quick | 2018-01-01 ~ 2025-12-31 | technical, volume, flow, market_structure, onchain, sentiment, lag_rolling |   340 | lightgbm |

---
## 7. 结论与建议

### 关键发现

1. **Accuracy 最佳**: baseline_T14_X8 (0.3745)
2. **F1-Macro 最佳**: baseline_T14_X8 (0.3546)
3. **Cohen's Kappa 最佳**: baseline_T14_X8 (0.0466)

4. **特征集差异**: 各实验使用了不同的特征集组合，这可能是性能差异的主要因素
5. **模型复杂度不同**: n_estimators 分别为 [500, 200]

### 建议后续实验

- [ ] 尝试不同的特征集组合消融实验
- [ ] 调优 learning_rate + n_estimators 组合
- [ ] 增加更多 Walk-Forward folds 以提高评估稳定性
- [ ] 分析 cohen_kappa 偏低的原因（标签分布？类别不平衡？）

---
## 附录: 实验产物清单

### baseline_T14_X8
- **目录**: `/Users/qiubling/Desktop/projects/FcstLabPro/experiments/baseline/baseline_T14_X8_20260212_233203_9f4a23`
  - `config.yaml` (874B)
  - `feature_importance.csv` (1.2KB)
  - `fold_metrics.csv` (6.1KB)
  - `meta.json` (647B)
  - `metrics.json` (189B)
  - `model.joblib` (3767.1KB)
  - `predictions.csv` (14.0KB)
  - `report.md` (10.9KB)

### baseline_v2_quick
- **目录**: `/Users/qiubling/Desktop/projects/FcstLabPro/experiments/baseline/baseline_v2_quick_20260212_235941_760429`
  - `config.yaml` (975B)
  - `feature_importance.csv` (5.7KB)
  - `fold_metrics.csv` (2.1KB)
  - `meta.json` (684B)
  - `metrics.json` (188B)
  - `model.joblib` (1507.6KB)
  - `predictions.csv` (4.7KB)
  - `report.md` (6.6KB)
