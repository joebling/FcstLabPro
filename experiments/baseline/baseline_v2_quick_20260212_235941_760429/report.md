# 实验报告: baseline_v2_quick_20260212_235941_760429

**生成时间**: 2026-02-13 00:00:22

## 1. 实验概要

| 项目 | 值 |
|------|------|
| 实验名称 | baseline_v2_quick |
| 描述 | 基线v2快速版：全特征但减少folds，用于调试验证 |
| 标签 | ['baseline', 'v2', 'quick'] |
| Git Commit | 1c4ef2b |
| Git Branch | master |
| 耗时 | Nones |
| 随机种子 | 42 |

## 2. 数据配置

- **数据源**: binance
- **交易对**: BTCUSDT
- **周期**: 1d
- **时间范围**: 2018-01-01 ~ 2025-12-31
- **数据文件**: `data/raw/btc_binance_BTCUSDT_1d.csv`

## 3. 特征配置

- **特征集**: ['technical', 'volume', 'flow', 'market_structure', 'onchain', 'sentiment', 'lag_rolling']
- **总特征数**: 340
- **NaN处理**: ffill_then_drop

## 4. 标签配置

- **策略**: reversal
- **窗口 T**: 14 天
- **阈值 X**: 0.08 (8%)

## 5. 模型配置

- **类型**: lightgbm
- **参数**:
  - n_estimators: 200
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

## 6. 评估结果（汇总）

| 指标              |       值 |
|:----------------|--------:|
| accuracy        |  0.3509 |
| f1_macro        |  0.3193 |
| precision_macro |  0.3238 |
| recall_macro    |  0.3231 |
| cohen_kappa     | -0.013  |

## 7. Walk-Forward Fold 详情

- **方法**: walk_forward
- **初始训练集**: 1500
- **OOS窗口**: 63
- **步进**: 63
- **总 Fold 数**: 19

|   fold_id |   train_size |   test_size |   accuracy |   f1_macro |   precision_macro |   recall_macro |   cohen_kappa |
|----------:|-------------:|------------:|-----------:|-----------:|------------------:|---------------:|--------------:|
|    0.0000 |    1500.0000 |     63.0000 |     0.2540 |     0.1629 |            0.1296 |         0.3452 |       -0.0186 |
|    1.0000 |    1563.0000 |     63.0000 |     0.2540 |     0.1581 |            0.2182 |         0.3065 |       -0.0360 |
|    2.0000 |    1626.0000 |     63.0000 |     0.2857 |     0.2096 |            0.4277 |         0.3678 |        0.0403 |
|    3.0000 |    1689.0000 |     63.0000 |     0.2381 |     0.2474 |            0.2907 |         0.3118 |       -0.0482 |
|    4.0000 |    1752.0000 |     63.0000 |     0.6667 |     0.2667 |            0.2456 |         0.2917 |       -0.1386 |
|    5.0000 |    1815.0000 |     63.0000 |     0.6032 |     0.3422 |            0.4370 |         0.6109 |        0.0019 |
|    6.0000 |    1878.0000 |     63.0000 |     0.3333 |     0.1867 |            0.2000 |         0.1750 |       -0.0393 |
|    7.0000 |    1941.0000 |     63.0000 |     0.3333 |     0.3258 |            0.2930 |         0.4912 |       -0.0925 |
|    8.0000 |    2004.0000 |     63.0000 |     0.2540 |     0.3190 |            0.5425 |         0.6007 |        0.1327 |
|    9.0000 |    2067.0000 |     63.0000 |     0.3333 |     0.2444 |            0.2200 |         0.3275 |       -0.0200 |
|   10.0000 |    2130.0000 |     63.0000 |     0.4286 |     0.4184 |            0.3862 |         0.5556 |        0.2020 |
|   11.0000 |    2193.0000 |     63.0000 |     0.3492 |     0.3340 |            0.3380 |         0.3360 |        0.0137 |
|   12.0000 |    2256.0000 |     63.0000 |     0.0476 |     0.0435 |            0.0370 |         0.0526 |       -0.0938 |
|   13.0000 |    2319.0000 |     63.0000 |     0.3175 |     0.2732 |            0.2827 |         0.2900 |       -0.1667 |
|   14.0000 |    2382.0000 |     63.0000 |     0.2857 |     0.2737 |            0.3829 |         0.4748 |        0.0825 |
|   15.0000 |    2445.0000 |     63.0000 |     0.2222 |     0.2096 |            0.2977 |         0.3142 |       -0.0175 |
|   16.0000 |    2508.0000 |     63.0000 |     0.4762 |     0.2669 |            0.2958 |         0.5481 |        0.1373 |
|   17.0000 |    2571.0000 |     63.0000 |     0.7460 |     0.5184 |            0.4570 |         0.6212 |        0.4263 |
|   18.0000 |    2634.0000 |     63.0000 |     0.2381 |     0.1889 |            0.1970 |         0.4444 |       -0.0566 |

## 8. 分类报告

```
              precision    recall  f1-score   support

        顶部反转       0.18      0.27      0.22       227
          正常       0.51      0.43      0.47       607
        底部反转       0.28      0.26      0.27       363

    accuracy                           0.35      1197
   macro avg       0.32      0.32      0.32      1197
weighted avg       0.38      0.35      0.36      1197

```

## 9. 混淆矩阵

|         |   顶部反转(0) |   正常(1) |   底部反转(2) |
|:--------|----------:|--------:|----------:|
| 顶部反转(0) |        62 |      96 |        69 |
| 正常(1)   |       171 |     262 |       174 |
| 底部反转(2) |       107 |     160 |        96 |

## 10. Top 20 重要特征

| feature             |   importance |
|:--------------------|-------------:|
| sth_sopr_std30      |          205 |
| rsi_14_std30        |          145 |
| sma_cross_50_200    |          134 |
| buy_pressure_std30  |          132 |
| lth_sopr_ma30       |          125 |
| macd_hist_std30     |          121 |
| low_50d_dist        |          121 |
| dist_from_low_180d  |          119 |
| buy_pressure_ma30   |          116 |
| dist_from_low_365d  |          109 |
| cvd_ma_21           |          108 |
| vol_price_corr_20   |          108 |
| fgi_std30           |          108 |
| buy_pressure_std14  |          106 |
| fgi_std14           |          105 |
| lth_sopr_std30      |          105 |
| rsi_14_lag14        |          102 |
| vol_volatility_20   |          101 |
| liquidity_proxy     |          100 |
| volume_density_ma30 |          100 |

## 附录: 完整配置

```yaml
experiment:
  name: baseline_v2_quick
  description: 基线v2快速版：全特征但减少folds，用于调试验证
  tags:
  - baseline
  - v2
  - quick
  category: baseline
data:
  source: binance
  symbol: BTCUSDT
  interval: 1d
  start: '2018-01-01'
  end: '2025-12-31'
  path: data/raw/btc_binance_BTCUSDT_1d.csv
features:
  sets:
  - technical
  - volume
  - flow
  - market_structure
  - onchain
  - sentiment
  - lag_rolling
  drop_na_method: ffill_then_drop
  scaling: null
label:
  strategy: reversal
  T: 14
  X: 0.08
model:
  type: lightgbm
  params:
    n_estimators: 200
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
evaluation:
  method: walk_forward
  init_train: 1500
  oos_window: 63
  step: 63
  metrics:
  - accuracy
  - f1_macro
  - precision_macro
  - recall_macro
  - cohen_kappa
seed: 42

```