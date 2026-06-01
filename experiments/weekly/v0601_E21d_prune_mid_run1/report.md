# 实验报告: v0601_E21d_prune_mid_run1

**生成时间**: 2026-06-01 08:48:12

## 1. 实验概要

| 项目 | 值 |
|------|------|
| 实验名称 | v0601_E21d_prune_mid |
| 描述 | Phase 2.5 Wave 2 (E8 系剪枝): imp<10 删 (留 44) |
| 标签 | ['weekly', 'bear', 'v0601', 'phase_2_5', 'wave_2', 'e21', 'prune', 'touch'] |
| Git Commit | c3881aa |
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
- **总特征数**: 44
- **NaN处理**: ffill_then_drop

## 4. 标签配置

- **策略**: touch_filtered
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
| accuracy         | 0.9278 |
| f1_binary        | 0.8133 |
| precision_binary | 0.7721 |
| recall_binary    | 0.8592 |
| cohen_kappa      | 0.7687 |

## 7. Walk-Forward Fold 详情

- **方法**: walk_forward
- **初始训练集**: 800
- **OOS窗口**: 63
- **步进**: 21
- **总 Fold 数**: 53

|   fold_id |   train_size |   test_size |   accuracy |   f1_binary |   precision_binary |   recall_binary |   cohen_kappa |
|----------:|-------------:|------------:|-----------:|------------:|-------------------:|----------------:|--------------:|
|    0.0000 |     800.0000 |     63.0000 |     0.8889 |      0.8444 |             0.7917 |          0.9048 |        0.7586 |
|    1.0000 |     821.0000 |     63.0000 |     0.8571 |      0.7805 |             0.7273 |          0.8421 |        0.6754 |
|    2.0000 |     842.0000 |     63.0000 |     0.8254 |      0.7556 |             0.7727 |          0.7391 |        0.6199 |
|    3.0000 |     863.0000 |     63.0000 |     0.9365 |      0.8000 |             0.8000 |          0.8000 |        0.7623 |
|    4.0000 |     884.0000 |     63.0000 |     0.9683 |      0.8571 |             1.0000 |          0.7500 |        0.8397 |
|    5.0000 |     905.0000 |     63.0000 |     0.9524 |      0.8235 |             1.0000 |          0.7000 |        0.7970 |
|    6.0000 |     926.0000 |     63.0000 |     0.9841 |      0.9474 |             1.0000 |          0.9000 |        0.9381 |
|    7.0000 |     947.0000 |     63.0000 |     1.0000 |      1.0000 |             1.0000 |          1.0000 |        1.0000 |
|    8.0000 |     968.0000 |     63.0000 |     0.9683 |      0.8000 |             0.8000 |          0.8000 |        0.7828 |
|    9.0000 |     989.0000 |     63.0000 |     0.9206 |      0.8485 |             0.7778 |          0.9333 |        0.7953 |
|   10.0000 |    1010.0000 |     63.0000 |     0.9206 |      0.8980 |             0.8800 |          0.9167 |        0.8331 |
|   11.0000 |    1031.0000 |     63.0000 |     0.9365 |      0.8889 |             0.9412 |          0.8421 |        0.8446 |
|   12.0000 |    1052.0000 |     63.0000 |     0.7937 |      0.5806 |             0.4286 |          0.9000 |        0.4658 |
|   13.0000 |    1073.0000 |     63.0000 |     0.8095 |      0.6667 |             0.5000 |          1.0000 |        0.5532 |
|   14.0000 |    1094.0000 |     63.0000 |     0.8095 |      0.7500 |             0.6000 |          1.0000 |        0.6111 |
|   15.0000 |    1115.0000 |     63.0000 |     0.9841 |      0.9714 |             0.9444 |          1.0000 |        0.9605 |
|   16.0000 |    1136.0000 |     63.0000 |     0.9841 |      0.9231 |             0.8571 |          1.0000 |        0.9143 |
|   17.0000 |    1157.0000 |     63.0000 |     0.9841 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   18.0000 |    1178.0000 |     63.0000 |     1.0000 |      0.0000 |             0.0000 |          0.0000 |      nan      |
|   19.0000 |    1199.0000 |     63.0000 |     1.0000 |      0.0000 |             0.0000 |          0.0000 |      nan      |
|   20.0000 |    1220.0000 |     63.0000 |     1.0000 |      1.0000 |             1.0000 |          1.0000 |        1.0000 |
|   21.0000 |    1241.0000 |     63.0000 |     1.0000 |      1.0000 |             1.0000 |          1.0000 |        1.0000 |
|   22.0000 |    1262.0000 |     63.0000 |     1.0000 |      1.0000 |             1.0000 |          1.0000 |        1.0000 |
|   23.0000 |    1283.0000 |     63.0000 |     1.0000 |      1.0000 |             1.0000 |          1.0000 |        1.0000 |
|   24.0000 |    1304.0000 |     63.0000 |     1.0000 |      1.0000 |             1.0000 |          1.0000 |        1.0000 |
|   25.0000 |    1325.0000 |     63.0000 |     0.9683 |      0.9000 |             0.9000 |          0.9000 |        0.8811 |
|   26.0000 |    1346.0000 |     63.0000 |     0.9365 |      0.8750 |             0.8235 |          0.9333 |        0.8327 |
|   27.0000 |    1367.0000 |     63.0000 |     0.9365 |      0.8750 |             0.7778 |          1.0000 |        0.8333 |
|   28.0000 |    1388.0000 |     63.0000 |     0.9524 |      0.9268 |             0.8636 |          1.0000 |        0.8918 |
|   29.0000 |    1409.0000 |     63.0000 |     0.9365 |      0.9048 |             0.9048 |          0.9048 |        0.8571 |
|   30.0000 |    1430.0000 |     63.0000 |     0.8571 |      0.8800 |             0.8250 |          0.9429 |        0.7055 |
|   31.0000 |    1451.0000 |     63.0000 |     0.9365 |      0.9231 |             0.9231 |          0.9231 |        0.8690 |
|   32.0000 |    1472.0000 |     63.0000 |     0.9524 |      0.9333 |             0.9130 |          0.9545 |        0.8963 |
|   33.0000 |    1493.0000 |     63.0000 |     0.9206 |      0.7619 |             0.7273 |          0.8000 |        0.7144 |
|   34.0000 |    1514.0000 |     63.0000 |     0.9841 |      0.8889 |             1.0000 |          0.8000 |        0.8805 |
|   35.0000 |    1535.0000 |     63.0000 |     0.9683 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   36.0000 |    1556.0000 |     63.0000 |     1.0000 |      0.0000 |             0.0000 |          0.0000 |      nan      |
|   37.0000 |    1577.0000 |     63.0000 |     0.9365 |      0.6667 |             1.0000 |          0.5000 |        0.6358 |
|   38.0000 |    1598.0000 |     63.0000 |     0.9524 |      0.8000 |             1.0000 |          0.6667 |        0.7742 |
|   39.0000 |    1619.0000 |     63.0000 |     0.8571 |      0.5263 |             0.5000 |          0.5556 |        0.4425 |
|   40.0000 |    1640.0000 |     63.0000 |     0.7460 |      0.5789 |             0.4231 |          0.9167 |        0.4305 |
|   41.0000 |    1661.0000 |     63.0000 |     0.6984 |      0.6122 |             0.4412 |          1.0000 |        0.4209 |
|   42.0000 |    1682.0000 |     63.0000 |     0.8730 |      0.8261 |             0.7037 |          1.0000 |        0.7308 |
|   43.0000 |    1703.0000 |     63.0000 |     0.9683 |      0.8889 |             0.8000 |          1.0000 |        0.8706 |
|   44.0000 |    1724.0000 |     63.0000 |     1.0000 |      1.0000 |             1.0000 |          1.0000 |        1.0000 |
|   45.0000 |    1745.0000 |     63.0000 |     0.9683 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   46.0000 |    1766.0000 |     63.0000 |     0.9683 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   47.0000 |    1787.0000 |     63.0000 |     0.9683 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   48.0000 |    1808.0000 |     63.0000 |     0.9048 |      0.4000 |             1.0000 |          0.2500 |        0.3679 |
|   49.0000 |    1829.0000 |     63.0000 |     0.8889 |      0.6316 |             1.0000 |          0.4615 |        0.5764 |
|   50.0000 |    1850.0000 |     63.0000 |     0.8730 |      0.6923 |             1.0000 |          0.5294 |        0.6216 |
|   51.0000 |    1871.0000 |     63.0000 |     0.9048 |      0.8000 |             1.0000 |          0.6667 |        0.7407 |
|   52.0000 |    1892.0000 |     63.0000 |     0.7937 |      0.7636 |             0.6176 |          1.0000 |        0.5979 |

## 8. 分类报告

```
              precision    recall  f1-score   support

       负例(0)       0.97      0.94      0.96      2728
       正例(1)       0.77      0.86      0.81       611

    accuracy                           0.93      3339
   macro avg       0.87      0.90      0.88      3339
weighted avg       0.93      0.93      0.93      3339

```

## 9. 混淆矩阵

|       |   负例(0) |   正例(1) |
|:------|--------:|--------:|
| 负例(0) |    2573 |     155 |
| 正例(1) |      86 |     525 |

## 10. Top 20 重要特征

| feature                  |   importance |
|:-------------------------|-------------:|
| price_mom_smooth_14      |          156 |
| high_50d_dist            |           83 |
| obv                      |           74 |
| low_50d_dist             |           66 |
| return_14d               |           62 |
| return_3d                |           61 |
| buy_pressure_ma_20       |           57 |
| bb_pctb_20               |           46 |
| sma_200                  |           40 |
| vol_volatility_10        |           37 |
| trades_sma_5             |           35 |
| macd                     |           34 |
| high_14d_dist            |           34 |
| buy_pressure_ma_5        |           33 |
| cvd_ma_7                 |           33 |
| ema_100                  |           30 |
| atr_21                   |           28 |
| down_volume_proxy        |           27 |
| obv_sma_10               |           27 |
| flow_price_divergence_10 |           25 |

## 附录: 完整配置

```yaml
experiment:
  name: v0601_E21d_prune_mid
  description: 'Phase 2.5 Wave 2 (E8 系剪枝): imp<10 删 (留 44)'
  tags:
  - weekly
  - bear
  - v0601
  - phase_2_5
  - wave_2
  - e21
  - prune
  - touch
  category: weekly
  hypothesis: '验证 E20 剪枝规律在 E8 (touch_filtered, kappa 0.757 已较高) 是否普适.

    镜像 E20d (E1 +7.1%).

    若 E21c 同样有显著提升 → "剪枝>加特征" 是 weekly 任务通用规律.

    若 E21c 持平或下降 → E8 已接近 touch 任务上限, 规律仅在 E1 系成立.'
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
  - atr_pct_14
  - avg_trade_size
  - avg_trade_size_ma_10
  - avg_trade_size_ma_20
  - avg_trade_size_ma_5
  - avg_trade_size_ratio_10
  - avg_trade_size_ratio_20
  - avg_trade_size_ratio_5
  - avg_trade_size_sma_10
  - avg_trade_size_sma_20
  - avg_trade_size_sma_5
  - bb_lower_20
  - bb_upper_20
  - buy_pressure
  - buy_pressure_ma_10
  - cvd
  - cvd_change_14
  - cvd_change_21
  - cvd_ma_14
  - cvd_ma_21
  - ema_10
  - ema_20
  - ema_200
  - ema_5
  - ema_50
  - ext_fgi
  - ext_fgi_change_14d
  - ext_fgi_extreme_fear
  - ext_fgi_extreme_greed
  - ext_fgi_ma7
  - flow_change_10d
  - flow_change_1d
  - flow_change_3d
  - flow_change_5d
  - flow_momentum_5
  - flow_price_divergence_20
  - low_14d_dist
  - low_21d_dist
  - macd_hist
  - price_mom_smooth_24
  - price_vs_vwap_10
  - qvol_ratio_10
  - qvol_ratio_20
  - qvol_ratio_5
  - qvol_sma_10
  - qvol_sma_20
  - qvol_sma_5
  - return_5d
  - return_7d
  - sma_10
  - sma_100
  - sma_20
  - sma_5
  - sma_50
  - stoch_d_14
  - trades_change_1d
  - trades_change_5d
  - trades_ratio_10
  - trades_ratio_20
  - trades_ratio_5
  - trades_sma_20
  - vol_change_1d
  - vol_change_3d
  - vol_change_5d
  - vol_price_corr_10
  - vol_price_corr_20
  - vol_ratio_10
  - vol_ratio_20
  - vol_ratio_5
  - vol_ratio_50
  - vol_sma_10
  - vol_sma_20
  - vol_sma_5
  - vol_sma_50
  - volatility_20d
  - volume_cumsum_14
  - volume_cumsum_24
  - volume_cumsum_7
  - volume_density
  - volume_density_ma_10
  - volume_density_ma_5
  - volume_density_sma_10
  - volume_density_sma_5
  - vwap_10
  - vwap_20
label:
  strategy: touch_filtered
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