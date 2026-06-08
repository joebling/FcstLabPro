# 实验报告: v0601_E20f_prune_10_run1

**生成时间**: 2026-06-01 08:42:19

## 1. 实验概要

| 项目 | 值 |
|------|------|
| 实验名称 | v0601_E20f_prune_10 |
| 描述 | Phase 2.5 Wave 2: 只留 importance>=40 (约 10 特征, U 形曲线下沿) |
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
- **总特征数**: 2
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
| accuracy         | 0.8131 |
| f1_binary        | 0.435  |
| precision_binary | 0.3102 |
| recall_binary    | 0.728  |
| cohen_kappa      | 0.3441 |

## 7. Walk-Forward Fold 详情

- **方法**: walk_forward
- **初始训练集**: 800
- **OOS窗口**: 63
- **步进**: 21
- **总 Fold 数**: 62

|   fold_id |   train_size |   test_size |   accuracy |   f1_binary |   precision_binary |   recall_binary |   cohen_kappa |
|----------:|-------------:|------------:|-----------:|------------:|-------------------:|----------------:|--------------:|
|    0.0000 |     800.0000 |     63.0000 |     0.5397 |      0.0000 |             0.0000 |          0.0000 |       -0.1229 |
|    1.0000 |     821.0000 |     63.0000 |     0.6667 |      0.2222 |             0.1500 |          0.4286 |        0.0690 |
|    2.0000 |     842.0000 |     63.0000 |     0.6825 |      0.2857 |             0.2667 |          0.3077 |        0.0830 |
|    3.0000 |     863.0000 |     63.0000 |     0.7778 |      0.3636 |             0.3333 |          0.4000 |        0.2304 |
|    4.0000 |     884.0000 |     63.0000 |     0.8571 |      0.3077 |             0.4000 |          0.2500 |        0.2327 |
|    5.0000 |     905.0000 |     63.0000 |     0.8095 |      0.1429 |             0.0769 |          1.0000 |        0.1168 |
|    6.0000 |     926.0000 |     63.0000 |     0.6825 |      0.0909 |             0.0476 |          1.0000 |        0.0625 |
|    7.0000 |     947.0000 |     63.0000 |     0.6667 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|    8.0000 |     968.0000 |     63.0000 |     0.7937 |      0.1333 |             0.0769 |          0.5000 |        0.0829 |
|    9.0000 |     989.0000 |     63.0000 |     0.8571 |      0.4000 |             0.3333 |          0.5000 |        0.3226 |
|   10.0000 |    1010.0000 |     63.0000 |     0.8571 |      0.6087 |             0.5833 |          0.6364 |        0.5215 |
|   11.0000 |    1031.0000 |     63.0000 |     0.8571 |      0.5714 |             0.6667 |          0.5000 |        0.4878 |
|   12.0000 |    1052.0000 |     63.0000 |     0.9206 |      0.6667 |             0.7143 |          0.6250 |        0.6218 |
|   13.0000 |    1073.0000 |     63.0000 |     0.8730 |      0.2000 |             0.1429 |          0.3333 |        0.1429 |
|   14.0000 |    1094.0000 |     63.0000 |     0.8730 |      0.6667 |             0.5714 |          0.8000 |        0.5909 |
|   15.0000 |    1115.0000 |     63.0000 |     0.8730 |      0.6667 |             0.5714 |          0.8000 |        0.5909 |
|   16.0000 |    1136.0000 |     63.0000 |     0.9524 |      0.8421 |             0.8889 |          0.8000 |        0.8142 |
|   17.0000 |    1157.0000 |     63.0000 |     0.7302 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   18.0000 |    1178.0000 |     63.0000 |     0.6825 |      0.0909 |             0.0625 |          0.1667 |       -0.0553 |
|   19.0000 |    1199.0000 |     63.0000 |     0.6032 |      0.0741 |             0.0556 |          0.1111 |       -0.1438 |
|   20.0000 |    1220.0000 |     63.0000 |     0.7302 |      0.1053 |             0.1000 |          0.1111 |       -0.0531 |
|   21.0000 |    1241.0000 |     63.0000 |     0.6349 |      0.0000 |             0.0000 |          0.0000 |       -0.0903 |
|   22.0000 |    1262.0000 |     63.0000 |     0.4603 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   23.0000 |    1283.0000 |     63.0000 |     0.5873 |      0.1875 |             0.1034 |          1.0000 |        0.1107 |
|   24.0000 |    1304.0000 |     63.0000 |     0.7619 |      0.2857 |             0.1667 |          1.0000 |        0.2222 |
|   25.0000 |    1325.0000 |     63.0000 |     1.0000 |      1.0000 |             1.0000 |          1.0000 |        1.0000 |
|   26.0000 |    1346.0000 |     63.0000 |     1.0000 |      0.0000 |             0.0000 |          0.0000 |      nan      |
|   27.0000 |    1367.0000 |     63.0000 |     0.9841 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   28.0000 |    1388.0000 |     63.0000 |     0.9841 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   29.0000 |    1409.0000 |     63.0000 |     0.9524 |      0.8421 |             0.8000 |          0.8889 |        0.8142 |
|   30.0000 |    1430.0000 |     63.0000 |     0.9683 |      0.8889 |             0.8889 |          0.8889 |        0.8704 |
|   31.0000 |    1451.0000 |     63.0000 |     0.9683 |      0.8889 |             0.8889 |          0.8889 |        0.8704 |
|   32.0000 |    1472.0000 |     63.0000 |     0.9683 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   33.0000 |    1493.0000 |     63.0000 |     0.7619 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   34.0000 |    1514.0000 |     63.0000 |     0.7143 |      0.5263 |             0.3571 |          1.0000 |        0.3817 |
|   35.0000 |    1535.0000 |     63.0000 |     0.7778 |      0.5882 |             0.4167 |          1.0000 |        0.4693 |
|   36.0000 |    1556.0000 |     63.0000 |     0.9365 |      0.8571 |             0.8000 |          0.9231 |        0.8166 |
|   37.0000 |    1577.0000 |     63.0000 |     0.8571 |      0.7429 |             0.7647 |          0.7222 |        0.6441 |
|   38.0000 |    1598.0000 |     63.0000 |     0.8889 |      0.8372 |             0.9474 |          0.7500 |        0.7546 |
|   39.0000 |    1619.0000 |     63.0000 |     0.7937 |      0.7451 |             0.6333 |          0.9048 |        0.5806 |
|   40.0000 |    1640.0000 |     63.0000 |     0.8095 |      0.6471 |             0.5500 |          0.7857 |        0.5221 |
|   41.0000 |    1661.0000 |     63.0000 |     0.7937 |      0.5185 |             0.3889 |          0.7778 |        0.4052 |
|   42.0000 |    1682.0000 |     63.0000 |     0.8730 |      0.6667 |             0.5714 |          0.8000 |        0.5909 |
|   43.0000 |    1703.0000 |     63.0000 |     0.9206 |      0.4444 |             0.2857 |          1.0000 |        0.4156 |
|   44.0000 |    1724.0000 |     63.0000 |     0.9524 |      0.4000 |             0.2500 |          1.0000 |        0.3844 |
|   45.0000 |    1745.0000 |     63.0000 |     0.9683 |      0.8571 |             0.7500 |          1.0000 |        0.8397 |
|   46.0000 |    1766.0000 |     63.0000 |     0.9683 |      0.8889 |             0.8000 |          1.0000 |        0.8706 |
|   47.0000 |    1787.0000 |     63.0000 |     0.7778 |      0.5333 |             0.3636 |          1.0000 |        0.4265 |
|   48.0000 |    1808.0000 |     63.0000 |     0.6349 |      0.1481 |             0.0800 |          1.0000 |        0.0949 |
|   49.0000 |    1829.0000 |     63.0000 |     0.5079 |      0.0606 |             0.0312 |          1.0000 |        0.0308 |
|   50.0000 |    1850.0000 |     63.0000 |     0.6508 |      0.3889 |             0.2414 |          1.0000 |        0.2556 |
|   51.0000 |    1871.0000 |     63.0000 |     0.8571 |      0.6087 |             0.4375 |          1.0000 |        0.5371 |
|   52.0000 |    1892.0000 |     63.0000 |     1.0000 |      1.0000 |             1.0000 |          1.0000 |        1.0000 |
|   53.0000 |    1913.0000 |     63.0000 |     0.9206 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   54.0000 |    1934.0000 |     63.0000 |     0.8889 |      0.3636 |             0.2222 |          1.0000 |        0.3288 |
|   55.0000 |    1955.0000 |     63.0000 |     0.8889 |      0.3636 |             0.2222 |          1.0000 |        0.3288 |
|   56.0000 |    1976.0000 |     63.0000 |     0.9524 |      0.5714 |             0.4000 |          1.0000 |        0.5511 |
|   57.0000 |    1997.0000 |     63.0000 |     0.9206 |      0.7059 |             0.6000 |          0.8571 |        0.6617 |
|   58.0000 |    2018.0000 |     63.0000 |     0.9048 |      0.6667 |             0.5455 |          0.8571 |        0.6143 |
|   59.0000 |    2039.0000 |     63.0000 |     0.7619 |      0.4444 |             0.3000 |          0.8571 |        0.3350 |
|   60.0000 |    2060.0000 |     63.0000 |     0.7143 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   61.0000 |    2081.0000 |     63.0000 |     0.4603 |      0.1500 |             0.0811 |          1.0000 |        0.0679 |

## 8. 分类报告

```
              precision    recall  f1-score   support

       负例(0)       0.96      0.82      0.89      3520
       正例(1)       0.31      0.73      0.43       386

    accuracy                           0.81      3906
   macro avg       0.64      0.78      0.66      3906
weighted avg       0.90      0.81      0.84      3906

```

## 9. 混淆矩阵

|       |   负例(0) |   正例(1) |
|:------|--------:|--------:|
| 负例(0) |    2895 |     625 |
| 正例(1) |     105 |     281 |

## 10. Top 20 重要特征

| feature             |   importance |
|:--------------------|-------------:|
| volatility_20d      |          748 |
| price_mom_smooth_14 |          527 |

## 附录: 完整配置

```yaml
experiment:
  name: v0601_E20f_prune_10
  description: 'Phase 2.5 Wave 2: 只留 importance>=40 (约 10 特征, U 形曲线下沿)'
  tags:
  - weekly
  - bear
  - v0601
  - phase_2_5
  - wave_2
  - e20
  - prune
  category: weekly
  hypothesis: 测试 U 形曲线极限, 留 2 特征是否还能继续提升 vs E20c (0.4448).
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
  - atr_14
  - atr_21
  - atr_pct_14
  - atr_pct_21
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
  - bb_pctb_20
  - bb_upper_20
  - bb_width_20
  - buy_pressure
  - buy_pressure_ma_10
  - buy_pressure_ma_20
  - buy_pressure_ma_5
  - cvd
  - cvd_change_14
  - cvd_change_21
  - cvd_change_7
  - cvd_ma_14
  - cvd_ma_21
  - cvd_ma_7
  - down_volume_proxy
  - ema_10
  - ema_100
  - ema_20
  - ema_200
  - ema_5
  - ema_50
  - ext_fgi
  - ext_fgi_change_14d
  - ext_fgi_change_7d
  - ext_fgi_extreme_fear
  - ext_fgi_extreme_greed
  - ext_fgi_ma14
  - ext_fgi_ma30
  - ext_fgi_ma7
  - ext_fgi_price_divergence
  - ext_fgi_std_14
  - flow_change_10d
  - flow_change_1d
  - flow_change_3d
  - flow_change_5d
  - flow_momentum_10
  - flow_momentum_20
  - flow_momentum_5
  - flow_price_divergence_10
  - flow_price_divergence_20
  - high_14d_dist
  - high_21d_dist
  - high_50d_dist
  - low_14d_dist
  - low_21d_dist
  - low_50d_dist
  - macd
  - macd_hist
  - macd_signal
  - obv
  - obv_sma_10
  - obv_sma_20
  - price_mom_smooth_24
  - price_mom_smooth_7
  - price_vs_vwap_10
  - price_vs_vwap_20
  - qvol_ratio_10
  - qvol_ratio_20
  - qvol_ratio_5
  - qvol_sma_10
  - qvol_sma_20
  - qvol_sma_5
  - return_14d
  - return_1d
  - return_21d
  - return_3d
  - return_5d
  - return_7d
  - sma_10
  - sma_100
  - sma_20
  - sma_200
  - sma_5
  - sma_50
  - sma_cross_5_20
  - stoch_d_14
  - stoch_k_14
  - trades_change_1d
  - trades_change_5d
  - trades_ratio_10
  - trades_ratio_20
  - trades_ratio_5
  - trades_sma_10
  - trades_sma_20
  - trades_sma_5
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
  - vol_volatility_10
  - vol_volatility_20
  - volatility_10d
  - volatility_5d
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