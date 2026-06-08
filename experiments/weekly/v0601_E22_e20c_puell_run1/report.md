# 实验报告: v0601_E22_e20c_puell_run1

**生成时间**: 2026-06-02 05:38:02

## 1. 实验概要

| 项目 | 值 |
|------|------|
| 实验名称 | v0601_E22_e20c_puell |
| 描述 | Phase 2.5 Wave 3 #1: E20c (28 核心剪枝) + Puell Multiple (5 short-horizon 派生). 重启 add-feature 路线的第一炮, 但 baseline 改为健康的 E20c (非过参数化的 E1 129). |
| 标签 | ['weekly', 'bear', 'v0601', 'phase_2_5', 'wave_3', 'e22', 'puell', 'e20c_based'] |
| Git Commit | 05f14db |
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

- **特征集**: ['technical', 'volume', 'flow', 'market_structure', 'external_fgi', 'external_puell']
- **总特征数**: 33
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
| accuracy         | 0.8856 |
| f1_binary        | 0.5013 |
| precision_binary | 0.4528 |
| recall_binary    | 0.5614 |
| cohen_kappa      | 0.4375 |

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
|    6.0000 |     926.0000 |     63.0000 |     0.8889 |      0.4615 |             1.0000 |          0.3000 |        0.4190 |
|    7.0000 |     947.0000 |     63.0000 |     0.9048 |      0.5714 |             1.0000 |          0.4000 |        0.5287 |
|    8.0000 |     968.0000 |     63.0000 |     0.9841 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|    9.0000 |     989.0000 |     63.0000 |     0.7460 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   10.0000 |    1010.0000 |     63.0000 |     0.7302 |      0.4848 |             0.3333 |          0.8889 |        0.3497 |
|   11.0000 |    1031.0000 |     63.0000 |     0.8413 |      0.6154 |             0.4706 |          0.8889 |        0.5270 |
|   12.0000 |    1052.0000 |     63.0000 |     0.9206 |      0.6667 |             0.8333 |          0.5556 |        0.6237 |
|   13.0000 |    1073.0000 |     63.0000 |     1.0000 |      0.0000 |             0.0000 |          0.0000 |      nan      |
|   14.0000 |    1094.0000 |     63.0000 |     0.7778 |      0.3000 |             0.1765 |          1.0000 |        0.2383 |
|   15.0000 |    1115.0000 |     63.0000 |     0.7937 |      0.3158 |             0.1875 |          1.0000 |        0.2561 |
|   16.0000 |    1136.0000 |     63.0000 |     0.9048 |      0.5000 |             0.3333 |          1.0000 |        0.4615 |
|   17.0000 |    1157.0000 |     63.0000 |     1.0000 |      0.0000 |             0.0000 |          0.0000 |      nan      |
|   18.0000 |    1178.0000 |     63.0000 |     0.9841 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   19.0000 |    1199.0000 |     63.0000 |     1.0000 |      0.0000 |             0.0000 |          0.0000 |      nan      |
|   20.0000 |    1220.0000 |     63.0000 |     0.9365 |      0.5000 |             0.5000 |          0.5000 |        0.4661 |
|   21.0000 |    1241.0000 |     63.0000 |     0.9206 |      0.6667 |             0.8333 |          0.5556 |        0.6237 |
|   22.0000 |    1262.0000 |     63.0000 |     0.9206 |      0.6667 |             0.8333 |          0.5556 |        0.6237 |
|   23.0000 |    1283.0000 |     63.0000 |     0.9683 |      0.7500 |             1.0000 |          0.6000 |        0.7342 |
|   24.0000 |    1304.0000 |     63.0000 |     1.0000 |      0.0000 |             0.0000 |          0.0000 |      nan      |
|   25.0000 |    1325.0000 |     63.0000 |     0.9206 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   26.0000 |    1346.0000 |     63.0000 |     0.8730 |      0.3333 |             1.0000 |          0.2000 |        0.2961 |
|   27.0000 |    1367.0000 |     63.0000 |     0.8889 |      0.4615 |             1.0000 |          0.3000 |        0.4190 |
|   28.0000 |    1388.0000 |     63.0000 |     0.7937 |      0.4348 |             1.0000 |          0.2778 |        0.3546 |
|   29.0000 |    1409.0000 |     63.0000 |     0.8571 |      0.7273 |             0.8000 |          0.6667 |        0.6316 |
|   30.0000 |    1430.0000 |     63.0000 |     0.8254 |      0.8136 |             0.6857 |          1.0000 |        0.6598 |
|   31.0000 |    1451.0000 |     63.0000 |     0.9048 |      0.8421 |             0.7273 |          1.0000 |        0.7763 |
|   32.0000 |    1472.0000 |     63.0000 |     0.8730 |      0.7500 |             0.6667 |          0.8571 |        0.6667 |
|   33.0000 |    1493.0000 |     63.0000 |     0.9524 |      0.8421 |             0.8889 |          0.8000 |        0.8142 |
|   34.0000 |    1514.0000 |     63.0000 |     0.9524 |      0.6667 |             0.7500 |          0.6000 |        0.6414 |
|   35.0000 |    1535.0000 |     63.0000 |     0.9841 |      0.8000 |             0.6667 |          1.0000 |        0.7921 |
|   36.0000 |    1556.0000 |     63.0000 |     1.0000 |      0.0000 |             0.0000 |          0.0000 |      nan      |
|   37.0000 |    1577.0000 |     63.0000 |     0.9365 |      0.6667 |             1.0000 |          0.5000 |        0.6358 |
|   38.0000 |    1598.0000 |     63.0000 |     0.9365 |      0.6667 |             1.0000 |          0.5000 |        0.6358 |
|   39.0000 |    1619.0000 |     63.0000 |     0.7778 |      0.3636 |             0.2857 |          0.5000 |        0.2410 |
|   40.0000 |    1640.0000 |     63.0000 |     0.6825 |      0.0909 |             0.0476 |          1.0000 |        0.0625 |
|   41.0000 |    1661.0000 |     63.0000 |     0.4921 |      0.1579 |             0.0857 |          1.0000 |        0.0769 |
|   42.0000 |    1682.0000 |     63.0000 |     0.6984 |      0.4242 |             0.2692 |          1.0000 |        0.3020 |
|   43.0000 |    1703.0000 |     63.0000 |     0.9524 |      0.8000 |             0.6667 |          1.0000 |        0.7742 |
|   44.0000 |    1724.0000 |     63.0000 |     0.9683 |      0.6667 |             1.0000 |          0.5000 |        0.6519 |
|   45.0000 |    1745.0000 |     63.0000 |     0.9683 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   46.0000 |    1766.0000 |     63.0000 |     0.9365 |      0.0000 |             0.0000 |          0.0000 |       -0.0328 |
|   47.0000 |    1787.0000 |     63.0000 |     0.9365 |      0.0000 |             0.0000 |          0.0000 |       -0.0328 |
|   48.0000 |    1808.0000 |     63.0000 |     0.9683 |      0.8333 |             1.0000 |          0.7143 |        0.8163 |
|   49.0000 |    1829.0000 |     63.0000 |     0.9206 |      0.7368 |             0.5833 |          1.0000 |        0.6939 |
|   50.0000 |    1850.0000 |     63.0000 |     0.8889 |      0.6667 |             0.5000 |          1.0000 |        0.6087 |
|   51.0000 |    1871.0000 |     63.0000 |     0.9365 |      0.0000 |             0.0000 |          0.0000 |        0.0000 |
|   52.0000 |    1892.0000 |     63.0000 |     0.7143 |      0.2500 |             0.1429 |          1.0000 |        0.1818 |

## 8. 分类报告

```
              precision    recall  f1-score   support

       负例(0)       0.95      0.92      0.94      2997
       正例(1)       0.45      0.56      0.50       342

    accuracy                           0.89      3339
   macro avg       0.70      0.74      0.72      3339
weighted avg       0.90      0.89      0.89      3339

```

## 9. 混淆矩阵

|       |   负例(0) |   正例(1) |
|:------|--------:|--------:|
| 负例(0) |    2765 |     232 |
| 正例(1) |     150 |     192 |

## 10. Top 20 重要特征

| feature             |   importance |
|:--------------------|-------------:|
| price_mom_smooth_14 |          111 |
| obv                 |           80 |
| volatility_20d      |           79 |
| sma_200             |           72 |
| ext_puell_zscore_90 |           63 |
| trades_sma_20       |           63 |
| vol_volatility_10   |           60 |
| high_50d_dist       |           58 |
| low_21d_dist        |           57 |
| flow_change_10d     |           54 |
| cvd_change_21       |           51 |
| obv_sma_20          |           50 |
| atr_21              |           48 |
| buy_pressure_ma_10  |           47 |
| volatility_10d      |           47 |
| qvol_sma_10         |           47 |
| low_50d_dist        |           46 |
| cvd_change_14       |           43 |
| ext_fgi_std_14      |           42 |
| buy_pressure_ma_5   |           41 |

## 附录: 完整配置

```yaml
experiment:
  name: v0601_E22_e20c_puell
  description: 'Phase 2.5 Wave 3 #1: E20c (28 核心剪枝) + Puell Multiple (5 short-horizon
    派生). 重启 add-feature 路线的第一炮, 但 baseline 改为健康的 E20c (非过参数化的 E1 129).'
  tags:
  - weekly
  - bear
  - v0601
  - phase_2_5
  - wave_3
  - e22
  - puell
  - e20c_based
  category: weekly
  hypothesis: 'Wave 2 已证明 E1(129) 过参数化 → 任何加特征被噪声淹没 (PUELL on E1: 0.326 < 0.348).
    Wave 3 核心问题: 当 baseline 健康 (E20c 28 特征, Kappa 0.4290 4-seed mean) 时, Puell 的强单点信号
    (E1 下 ext_puell_zscore_90 importance=48) 能否真正贡献 alpha?

    门槛 (§6.2 决策树, 基于 E20c=0.4290): - 弱 alpha 达标: Kappa ≥ 0.4505 (+5%) → 继续 + 4-seed
    3σ 显著性 - 强 alpha: Kappa ≥ 0.515 (+20%) → 立即 promote 候选 - 持平 0.4290~0.4505: 视成本保留
    - < 0.4290: 拒绝, 不如纯剪枝 E20c

    '
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
  - external_puell
  drop_na_method: ffill_then_drop
  scaling: standard
  drop_features:
  - rsi_*
  - price_vs_sma_*
  - sma_cross_10_50
  - sma_cross_50_200
  - atr_14
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
  - buy_pressure_ma_20
  - cvd
  - cvd_ma_14
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
  - low_14d_dist
  - macd_hist
  - macd_signal
  - obv_sma_10
  - price_mom_smooth_7
  - price_vs_vwap_10
  - price_vs_vwap_20
  - qvol_ratio_10
  - qvol_ratio_20
  - qvol_ratio_5
  - qvol_sma_5
  - return_1d
  - return_21d
  - return_3d
  - return_5d
  - return_7d
  - sma_10
  - sma_100
  - sma_20
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
  - trades_sma_5
  - vol_change_1d
  - vol_change_3d
  - vol_change_5d
  - vol_price_corr_20
  - vol_ratio_10
  - vol_ratio_20
  - vol_ratio_5
  - vol_ratio_50
  - vol_sma_10
  - vol_sma_20
  - vol_sma_5
  - vol_sma_50
  - vol_volatility_20
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