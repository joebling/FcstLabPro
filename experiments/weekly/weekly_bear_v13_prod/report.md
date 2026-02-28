# 实验报告: weekly_bear_v13_prod

**生成时间**: 2026-02-28 11:22:56

## 1. 实验概要

| 项目 | 值 |
|------|------|
| 实验名称 | weekly_bear_v13_prod |
| 描述 | v0301 Bear: T=28 天窗口 + FGI (生产版本) |
| 标签 | ['weekly', 'bear', 'v13', 'prod', 'v0301'] |
| Git Commit | ea4736c |
| Git Branch | main |
| 耗时 | (运行中) |
| 随机种子 | 42 |

## 2. 数据配置

- **数据源**: binance
- **交易对**: BTCUSDT
- **周期**: 1d
- **时间范围**: 2018-01-01 ~ 2025-12-31
- **数据文件**: `data/raw/btc_binance_BTCUSDT_1d.csv`

## 3. 特征配置

- **特征集**: ['technical', 'volume', 'flow', 'market_structure', 'external_fgi']
- **总特征数**: 137
- **NaN处理**: ffill_then_drop

## 4. 标签配置

- **策略**: reversal
- **T**: 28
- **X**: 0.05 (5.0%)

## 5. 模型配置

- **类型**: lightgbm
- **参数**:
  - n_estimators: 500
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

## 6. 评估结果（汇总）

| 指标               |       值 |
|:-----------------|--------:|
| accuracy         |  0.4481 |
| f1_binary        |  0.2651 |
| precision_binary |  0.2408 |
| recall_binary    |  0.2949 |
| f1_macro         |  0.4116 |
| cohen_kappa      | -0.1697 |

## 7. Walk-Forward Fold 详情

- **方法**: walk_forward
- **初始训练集**: 1500
- **OOS窗口**: 63
- **步进**: 21
- **总 Fold 数**: 22

|   fold_id |   train_size |   test_size |   accuracy |   f1_binary |   precision_binary |   recall_binary |   f1_macro |   cohen_kappa |
|----------:|-------------:|------------:|-----------:|------------:|-------------------:|----------------:|-----------:|--------------:|
|    0.0000 |    1500.0000 |     63.0000 |     0.3810 |      0.1333 |             0.0714 |          1.0000 |     0.3259 |        0.0488 |
|    1.0000 |    1521.0000 |     63.0000 |     0.2540 |      0.0784 |             0.0408 |          1.0000 |     0.2259 |        0.0186 |
|    2.0000 |    1542.0000 |     63.0000 |     0.1429 |      0.0357 |             0.0182 |          1.0000 |     0.1321 |        0.0047 |
|    3.0000 |    1563.0000 |     63.0000 |     0.1587 |      0.2535 |             0.1452 |          1.0000 |     0.1449 |        0.0054 |
|    4.0000 |    1584.0000 |     63.0000 |     0.7937 |      0.0000 |             0.0000 |          0.0000 |     0.4425 |        0.0000 |
|    5.0000 |    1605.0000 |     63.0000 |     0.4762 |      0.0000 |             0.0000 |          0.0000 |     0.3226 |        0.0000 |
|    6.0000 |    1626.0000 |     63.0000 |     0.3651 |      0.0476 |             1.0000 |          0.0244 |     0.2857 |        0.0172 |
|    7.0000 |    1647.0000 |     63.0000 |     0.2857 |      0.2105 |             1.0000 |          0.1176 |     0.2792 |        0.0483 |
|    8.0000 |    1668.0000 |     63.0000 |     0.5556 |      0.1765 |             1.0000 |          0.0968 |     0.4361 |        0.0982 |
|    9.0000 |    1689.0000 |     63.0000 |     0.4603 |      0.1500 |             0.1200 |          0.2000 |     0.3773 |       -0.2102 |
|   10.0000 |    1710.0000 |     63.0000 |     0.1429 |      0.1818 |             0.1000 |          1.0000 |     0.1409 |        0.0105 |
|   11.0000 |    1731.0000 |     63.0000 |     0.5238 |      0.4231 |             0.2683 |          1.0000 |     0.5088 |        0.2039 |
|   12.0000 |    1752.0000 |     63.0000 |     0.3651 |      0.3548 |             0.2157 |          1.0000 |     0.3649 |        0.0948 |
|   13.0000 |    1773.0000 |     63.0000 |     0.2063 |      0.3421 |             0.2063 |          1.0000 |     0.1711 |        0.0000 |
|   14.0000 |    1794.0000 |     63.0000 |     0.5079 |      0.5507 |             0.3800 |          1.0000 |     0.5034 |        0.2019 |
|   15.0000 |    1815.0000 |     63.0000 |     0.6667 |      0.5116 |             0.5500 |          0.4783 |     0.6293 |        0.2605 |
|   16.0000 |    1836.0000 |     63.0000 |     0.8095 |      0.4000 |             1.0000 |          0.2500 |     0.6434 |        0.3322 |
|   17.0000 |    1857.0000 |     63.0000 |     0.6667 |      0.0870 |             0.2000 |          0.0556 |     0.4415 |       -0.0426 |
|   18.0000 |    1878.0000 |     63.0000 |     0.6349 |      0.4651 |             1.0000 |          0.3030 |     0.5940 |        0.2928 |
|   19.0000 |    1899.0000 |     63.0000 |     0.3492 |      0.2545 |             1.0000 |          0.1458 |     0.3385 |        0.0752 |
|   20.0000 |    1920.0000 |     63.0000 |     0.3333 |      0.0870 |             1.0000 |          0.0455 |     0.2810 |        0.0279 |
|   21.0000 |    1941.0000 |     63.0000 |     0.7778 |      0.6818 |             0.8824 |          0.5556 |     0.7555 |        0.5243 |

## 8. 分类报告

```
              precision    recall  f1-score   support

       负例(0)       0.59      0.53      0.56       918
       正例(1)       0.24      0.29      0.27       468

    accuracy                           0.45      1386
   macro avg       0.42      0.41      0.41      1386
weighted avg       0.47      0.45      0.46      1386

```

## 9. 混淆矩阵

|       |   非跌(0) |   大跌(1) |
|:------|--------:|--------:|
| 非跌(0) |     483 |     435 |
| 大跌(1) |     330 |     138 |

## 10. Top 20 重要特征

| feature            |   importance |
|:-------------------|-------------:|
| trades_sma_20      |          209 |
| price_vs_sma_200   |          199 |
| low_50d_dist       |          197 |
| ext_fgi_std_14     |          183 |
| vol_volatility_20  |          181 |
| sma_cross_50_200   |          174 |
| flow_momentum_20   |          172 |
| low_21d_dist       |          167 |
| sma_100            |          160 |
| flow_momentum_5    |          158 |
| buy_pressure_ma_20 |          155 |
| rsi_28             |          144 |
| qvol_sma_20        |          140 |
| cvd_change_21      |          139 |
| high_50d_dist      |          135 |
| low_14d_dist       |          133 |
| ema_5              |          124 |
| obv                |          120 |
| flow_momentum_10   |          120 |
| vol_volatility_10  |          120 |

## 附录: 完整配置

```yaml
experiment:
  name: weekly_bear_v13_prod
  description: 'v0301 Bear: T=28 天窗口 + FGI (生产版本)'
  tags:
  - weekly
  - bear
  - v13
  - prod
  - v0301
  category: weekly
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
  - external_fgi
  drop_na_method: ffill_then_drop
  scaling: null
label:
  strategy: reversal
  T: 28
  X: 0.05
  map:
    0: 1
    1: 0
    2: 0
model:
  type: lightgbm
  params:
    n_estimators: 500
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
evaluation:
  method: walk_forward
  init_train: 1500
  oos_window: 63
  step: 21
  metrics:
  - accuracy
  - f1_binary
  - precision_binary
  - recall_binary
  - f1_macro
  - cohen_kappa
seed: 42

```