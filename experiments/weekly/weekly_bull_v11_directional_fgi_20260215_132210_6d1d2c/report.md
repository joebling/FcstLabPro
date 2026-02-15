# 实验报告: weekly_bull_v11_directional_fgi_20260215_132210_6d1d2c

**生成时间**: 2026-02-15 13:22:28

## 1. 实验概要

| 项目 | 值 |
|------|------|
| 实验名称 | weekly_bull_v11_directional_fgi |
| 描述 | Bull v11: directional标签 + FGI 对比 |
| 标签 | ['weekly', 'bull', 'binary', 'v11', 'directional', 'fgi'] |
| Git Commit | 64409a9 |
| Git Branch | main |
| 耗时 | Nones |
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

- **策略**: directional
- **窗口 T**: 14 天
- **阈值 X**: 0.05 (5%)

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
| accuracy         |  0.5488 |
| f1_binary        |  0.6953 |
| precision_binary |  0.6599 |
| recall_binary    |  0.7346 |
| f1_macro         |  0.4131 |
| cohen_kappa      | -0.1642 |

## 7. Walk-Forward Fold 详情

- **方法**: walk_forward
- **初始训练集**: 1500
- **OOS窗口**: 63
- **步进**: 21
- **总 Fold 数**: 14

|   fold_id |   train_size |   test_size |   accuracy |   f1_binary |   precision_binary |   recall_binary |   f1_macro |   cohen_kappa |
|----------:|-------------:|------------:|-----------:|------------:|-------------------:|----------------:|-----------:|--------------:|
|    0.0000 |    1500.0000 |     63.0000 |     0.5873 |      0.7347 |             0.6207 |          0.9000 |     0.4031 |       -0.0678 |
|    1.0000 |    1521.0000 |     63.0000 |     0.4921 |      0.6364 |             0.5283 |          0.8000 |     0.3971 |       -0.0992 |
|    2.0000 |    1542.0000 |     63.0000 |     0.5873 |      0.7347 |             0.5806 |          1.0000 |     0.4031 |        0.0421 |
|    3.0000 |    1563.0000 |     63.0000 |     0.7302 |      0.8090 |             0.8372 |          0.7826 |     0.6748 |        0.3513 |
|    4.0000 |    1584.0000 |     63.0000 |     0.2857 |      0.4304 |             0.8095 |          0.2931 |     0.2365 |       -0.1157 |
|    5.0000 |    1605.0000 |     63.0000 |     0.0635 |      0.0923 |             1.0000 |          0.0484 |     0.0625 |        0.0016 |
|    6.0000 |    1626.0000 |     63.0000 |     0.4286 |      0.5814 |             1.0000 |          0.4098 |     0.3407 |        0.0422 |
|    7.0000 |    1647.0000 |     63.0000 |     0.8889 |      0.9381 |             0.9138 |          0.9636 |     0.6998 |        0.4032 |
|    8.0000 |    1668.0000 |     63.0000 |     0.7460 |      0.8545 |             0.7460 |          1.0000 |     0.4273 |        0.0000 |
|    9.0000 |    1689.0000 |     63.0000 |     0.6349 |      0.7767 |             0.6349 |          1.0000 |     0.3883 |        0.0000 |
|   10.0000 |    1710.0000 |     63.0000 |     0.4286 |      0.6000 |             0.4286 |          1.0000 |     0.3000 |        0.0000 |
|   11.0000 |    1731.0000 |     63.0000 |     0.5079 |      0.6667 |             0.5000 |          1.0000 |     0.3636 |        0.0308 |
|   12.0000 |    1752.0000 |     63.0000 |     0.6667 |      0.7742 |             0.6545 |          0.9474 |     0.5689 |        0.2120 |
|   13.0000 |    1773.0000 |     63.0000 |     0.6349 |      0.7723 |             0.6610 |          0.9286 |     0.4261 |       -0.0299 |

## 8. 分类报告

```
              precision    recall  f1-score   support

       负例(0)       0.15      0.11      0.13       264
       正例(1)       0.66      0.73      0.70       618

    accuracy                           0.55       882
   macro avg       0.41      0.42      0.41       882
weighted avg       0.51      0.55      0.53       882

```

## 9. 混淆矩阵

|       |   负例(0) |   正例(1) |
|:------|--------:|--------:|
| 负例(0) |      30 |     234 |
| 正例(1) |     164 |     454 |

## 10. Top 20 重要特征

| feature            |   importance |
|:-------------------|-------------:|
| ext_fgi_std_14     |          223 |
| volatility_20d     |          218 |
| flow_momentum_20   |          214 |
| vol_volatility_20  |          206 |
| buy_pressure_ma_20 |          197 |
| cvd_change_21      |          191 |
| atr_pct_21         |          185 |
| vol_volatility_10  |          175 |
| buy_pressure       |          155 |
| macd_hist          |          149 |
| macd_signal        |          144 |
| sma_100            |          137 |
| sma_cross_50_200   |          135 |
| obv_sma_10         |          132 |
| price_vs_sma_50    |          131 |
| flow_momentum_10   |          130 |
| flow_momentum_5    |          129 |
| bb_width_20        |          127 |
| sma_200            |          127 |
| return_21d         |          125 |

## 附录: 完整配置

```yaml
experiment:
  name: weekly_bull_v11_directional_fgi
  description: 'Bull v11: directional标签 + FGI 对比'
  tags:
  - weekly
  - bull
  - binary
  - v11
  - directional
  - fgi
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
  strategy: directional
  T: 14
  X: 0.05
  map:
    0: 0
    1: 1
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