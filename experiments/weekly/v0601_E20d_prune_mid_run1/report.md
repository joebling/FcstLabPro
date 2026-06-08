# 实验报告: v0601_E20d_prune_mid_run1

**生成时间**: 2026-06-01 08:40:43

## 1. 实验概要

| 项目 | 值 |
|------|------|
| 实验名称 | v0601_E20d_prune_mid |
| 描述 | Phase 2.5 Wave 2: 中间梯度 — 删 67 个 importance<10 (留 62) |
| 标签 | ['weekly', 'bear', 'v0601', 'phase_2_5', 'wave_2', 'e20', 'prune'] |
| Git Commit | c88d918 |
| Git Branch | feat/model-governance-overhaul |
| 耗时 | (运行中) |
| 随机种子 | 42 |

## 2. 数据配置

- **数据源**: binance
- **交易对**: BTCUSDT
- **周期**: 1d
- **时间范围**: 2020-01-01 ~ 2025-12-31
- **数据文件**: `data/raw/btc_binance_BTCUSDT_1d.csv`

## 3. 特征配置

- **特征集**: ['technical', 'volume', 'flow', 'market_structure', 'external_fgi']
- **总特征数**: 62
- **NaN处理**: ffill_then_drop

## 4. 标签配置

- **策略**: directional_filtered
- **T**: 21
- **X**: 0.04 (4.0%)
- **ma_window**: 50
- **require_below_ma**: True
- **rsi_threshold**: 45.0 (4500.0%)
- **rsi_window**: 14

## 5. 模型配置

- **类型**: lightgbm
- **参数**:
  - n_estimators: 100
  - max_depth: 6
  - learning_rate: 0.05
  - num_leaves: 31
  - subsample: 0.8
  - colsample_bytree: 0.8
  - min_child_samples: 20
  - reg_alpha: 0.1
  - reg_lambda: 0.1
  - random_state: 42
  - verbose: -1
  - auto_scale_pos_weight: True
  - n_jobs: 1

## 6. 评估结果（汇总）

| 指标               |      值 |
|:-----------------|-------:|
| accuracy         | 0.882  |
| f1_binary        | 0.4387 |
| precision_binary | 0.4278 |
| recall_binary    | 0.4503 |
| cohen_kappa      | 0.3729 |

## 7. Walk-Forward Fold 详情

- **方法**: walk_forward
- **初始训练集**: 800
- **OOS窗口**: 63
- **步进**: 21
- **总 Fold 数**: 53

|   fold_id |   train_size |   test_size |   accuracy |   f1_binary |   precision_binary |   recall_binary |   cohen_kappa |
|----------:|-------------:|------------:|-----------:|------------:|-------------------:|----------------:|--------------:|
|    0.0000 |     800.0000 |     63.0000 |     0.9048 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|    1.0000 |     821.0000 |     63.0000 |     0.9048 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|    2.0000 |     842.0000 |     63.0000 |     0.7778 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|    3.0000 |     863.0000 |     63.0000 |     0.8730 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|    4.0000 |     884.0000 |     63.0000 |     0.8730 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|    5.0000 |     905.0000 |     63.0000 |     0.8413 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|    6.0000 |     926.0000 |     63.0000 |     0.8413 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|    7.0000 |     947.0000 |     63.0000 |     0.8413 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|    8.0000 |     968.0000 |     63.0000 |     0.9683 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|    9.0000 |     989.0000 |     63.0000 |     0.8254 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   10.0000 |    1010.0000 |     63.0000 |     0.8095 |      0.5714 |             0.4211 |          0.8889 |        0.4684 |
|   11.0000 |    1031.0000 |     63.0000 |     0.8413 |      0.6154 |             0.4706 |          0.8889 |        0.5270 |
|   12.0000 |    1052.0000 |     63.0000 |     0.8889 |      0.3636 |             1.0000 |          0.2222 |        0.3288 |
|   13.0000 |    1073.0000 |     63.0000 |     1.0000 |      0.0000 |             0.0000 |          0.0000 |      nan      |
|   14.0000 |    1094.0000 |     63.0000 |     0.8095 |      0.3333 |             0.2000 |          1.0000 |        0.2759 |
|   15.0000 |    1115.0000 |     63.0000 |     0.8095 |      0.3333 |             0.2000 |          1.0000 |        0.2759 |
|   16.0000 |    1136.0000 |     63.0000 |     0.9206 |      0.5455 |             0.3750 |          1.0000 |        0.5116 |
|   17.0000 |    1157.0000 |     63.0000 |     0.9841 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   18.0000 |    1178.0000 |     63.0000 |     0.9841 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   19.0000 |    1199.0000 |     63.0000 |     1.0000 |      0.0000 |             0.0000 |          0.0000 |      nan      |
|   20.0000 |    1220.0000 |     63.0000 |     0.9365 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   21.0000 |    1241.0000 |     63.0000 |     0.8889 |      0.3636 |             1.0000 |          0.2222 |        0.3288 |
|   22.0000 |    1262.0000 |     63.0000 |     0.9048 |      0.5000 |             1.0000 |          0.3333 |        0.4615 |
|   23.0000 |    1283.0000 |     63.0000 |     0.9524 |      0.5714 |             1.0000 |          0.4000 |        0.5511 |
|   24.0000 |    1304.0000 |     63.0000 |     1.0000 |      0.0000 |             0.0000 |          0.0000 |      nan      |
|   25.0000 |    1325.0000 |     63.0000 |     0.9206 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   26.0000 |    1346.0000 |     63.0000 |     0.8413 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   27.0000 |    1367.0000 |     63.0000 |     0.8413 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   28.0000 |    1388.0000 |     63.0000 |     0.7143 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   29.0000 |    1409.0000 |     63.0000 |     0.8889 |      0.8000 |             0.8235 |          0.7778 |        0.7232 |
|   30.0000 |    1430.0000 |     63.0000 |     0.8254 |      0.7317 |             0.8824 |          0.6250 |        0.6078 |
|   31.0000 |    1451.0000 |     63.0000 |     0.9524 |      0.9143 |             0.8421 |          1.0000 |        0.8817 |
|   32.0000 |    1472.0000 |     63.0000 |     0.8730 |      0.7500 |             0.6667 |          0.8571 |        0.6667 |
|   33.0000 |    1493.0000 |     63.0000 |     0.9365 |      0.7778 |             0.8750 |          0.7000 |        0.7413 |
|   34.0000 |    1514.0000 |     63.0000 |     0.9524 |      0.6667 |             0.7500 |          0.6000 |        0.6414 |
|   35.0000 |    1535.0000 |     63.0000 |     0.9841 |      0.8000 |             0.6667 |          1.0000 |        0.7921 |
|   36.0000 |    1556.0000 |     63.0000 |     1.0000 |      0.0000 |             0.0000 |          0.0000 |      nan      |
|   37.0000 |    1577.0000 |     63.0000 |     0.9524 |      0.7692 |             1.0000 |          0.6250 |        0.7442 |
|   38.0000 |    1598.0000 |     63.0000 |     0.9365 |      0.7143 |             0.8333 |          0.6250 |        0.6794 |
|   39.0000 |    1619.0000 |     63.0000 |     0.7143 |      0.3571 |             0.2500 |          0.6250 |        0.2147 |
|   40.0000 |    1640.0000 |     63.0000 |     0.5238 |      0.0625 |             0.0323 |          1.0000 |        0.0328 |
|   41.0000 |    1661.0000 |     63.0000 |     0.4921 |      0.1579 |             0.0857 |          1.0000 |        0.0769 |
|   42.0000 |    1682.0000 |     63.0000 |     0.7460 |      0.4667 |             0.3043 |          1.0000 |        0.3571 |
|   43.0000 |    1703.0000 |     63.0000 |     0.9524 |      0.8000 |             0.6667 |          1.0000 |        0.7742 |
|   44.0000 |    1724.0000 |     63.0000 |     0.9683 |      0.6667 |             1.0000 |          0.5000 |        0.6519 |
|   45.0000 |    1745.0000 |     63.0000 |     0.9683 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   46.0000 |    1766.0000 |     63.0000 |     0.9683 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   47.0000 |    1787.0000 |     63.0000 |     0.9683 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   48.0000 |    1808.0000 |     63.0000 |     0.9365 |      0.6000 |             1.0000 |          0.4286 |        0.5714 |
|   49.0000 |    1829.0000 |     63.0000 |     0.9524 |      0.8235 |             0.7000 |          1.0000 |        0.7970 |
|   50.0000 |    1850.0000 |     63.0000 |     0.9365 |      0.7500 |             0.6667 |          0.8571 |        0.7143 |
|   51.0000 |    1871.0000 |     63.0000 |     0.9524 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   52.0000 |    1892.0000 |     63.0000 |     0.6667 |      0.0870 |             0.0500 |          0.3333 |        0.0045 |

## 8. 分类报告

```
              precision    recall  f1-score   support

       负例(0)       0.94      0.93      0.93      2997
       正例(1)       0.43      0.45      0.44       342

    accuracy                           0.88      3339
   macro avg       0.68      0.69      0.69      3339
weighted avg       0.88      0.88      0.88      3339

```

## 9. 混淆矩阵

|       |   负例(0) |   正例(1) |
|:------|--------:|--------:|
| 负例(0) |    2791 |     206 |
| 正例(1) |     188 |     154 |

## 10. Top 20 重要特征

| feature             |   importance |
|:--------------------|-------------:|
| price_mom_smooth_14 |           86 |
| volatility_20d      |           62 |
| obv                 |           52 |
| ema_100             |           43 |
| obv_sma_20          |           38 |
| cvd_change_21       |           37 |
| buy_pressure_ma_10  |           36 |
| flow_change_10d     |           36 |
| atr_14              |           35 |
| atr_pct_21          |           35 |
| vol_volatility_10   |           33 |
| sma_200             |           32 |
| trades_sma_20       |           31 |
| return_3d           |           30 |
| return_14d          |           29 |
| obv_sma_10          |           29 |
| bb_width_20         |           28 |
| return_1d           |           28 |
| low_21d_dist        |           28 |
| trades_sma_5        |           27 |

## 附录: 完整配置

```yaml
experiment:
  name: v0601_E20d_prune_mid
  description: 'Phase 2.5 Wave 2: 中间梯度 — 删 67 个 importance<10 (留 62)'
  tags:
  - weekly
  - bear
  - v0601
  - phase_2_5
  - wave_2
  - e20
  - prune
  category: weekly
  hypothesis: 测试激进剪枝单调性. 留 62 特征, 看 kappa vs E20b (留 85) 是否继续上升.
data:
  source: binance
  symbol: BTCUSDT
  interval: 1d
  start: '2020-01-01'
  end: '2025-12-31'
  path: data/raw/btc_binance_BTCUSDT_1d.csv
  expected_effective_rows: 2192
  expected_sha256: 004bf0706559e0a79a4361c9a0db27d5acb07d72556499df0e081879017c7858
features:
  sets:
  - technical
  - volume
  - flow
  - market_structure
  - external_fgi
  drop_na_method: ffill_then_drop
  scaling: standard
  drop_features:
  - rsi_*
  - price_vs_sma_*
  - sma_cross_10_50
  - sma_cross_50_200
  - avg_trade_size_ma_10
  - avg_trade_size_ma_20
  - avg_trade_size_ma_5
  - avg_trade_size_ratio_10
  - avg_trade_size_ratio_20
  - avg_trade_size_sma_20
  - avg_trade_size_sma_5
  - bb_lower_20
  - bb_upper_20
  - buy_pressure
  - buy_pressure_ma_20
  - cvd_ma_14
  - ema_10
  - ema_20
  - ema_5
  - ema_50
  - ext_fgi
  - ext_fgi_extreme_fear
  - ext_fgi_extreme_greed
  - ext_fgi_ma14
  - ext_fgi_ma30
  - ext_fgi_ma7
  - flow_change_1d
  - flow_change_3d
  - flow_change_5d
  - flow_momentum_5
  - flow_price_divergence_10
  - flow_price_divergence_20
  - high_14d_dist
  - high_21d_dist
  - macd_signal
  - price_mom_smooth_7
  - price_vs_vwap_10
  - qvol_ratio_10
  - qvol_ratio_20
  - qvol_ratio_5
  - sma_10
  - sma_100
  - sma_20
  - sma_5
  - sma_50
  - sma_cross_5_20
  - trades_change_1d
  - trades_change_5d
  - trades_ratio_10
  - trades_ratio_20
  - trades_ratio_5
  - vol_change_1d
  - vol_change_3d
  - vol_change_5d
  - vol_ratio_10
  - vol_ratio_20
  - vol_ratio_5
  - vol_ratio_50
  - vol_sma_10
  - vol_sma_20
  - vol_sma_5
  - vol_sma_50
  - volume_cumsum_14
  - volume_cumsum_24
  - volume_density
  - volume_density_ma_10
  - volume_density_ma_5
  - volume_density_sma_10
  - volume_density_sma_5
  - vwap_10
  - vwap_20
label:
  strategy: directional_filtered
  T: 21
  X: 0.04
  ma_window: 50
  require_below_ma: true
  rsi_threshold: 45.0
  rsi_window: 14
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
    verbose: -1
    auto_scale_pos_weight: true
    n_jobs: 1
evaluation:
  method: walk_forward
  init_train: 800
  oos_window: 63
  step: 21
  metrics:
  - accuracy
  - f1_binary
  - precision_binary
  - recall_binary
  - cohen_kappa
  purge_gap: 21
seed: 42

```