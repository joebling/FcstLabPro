# 实验报告: weekly_bull_v27_orion_002

**生成时间**: 2026-02-18 11:17:00

## 1. 实验概要

| 项目 | 值 |
|------|------|
| 实验名称 | weekly_bull_v27_orion_002 |
| 描述 | Bull v27: Orion-BiX 实验002 - 特征剪枝到30个 (2026-02-18) |
| 标签 | ['weekly', 'bull', 'binary', 'v27', 'orion', 'orion-bix', 2, 'feature_pruning'] |
| 模型类型 | orion_bix |
| 随机种子 | 42 |

## 2. 数据配置

- **数据源**: binance
- **交易对**: BTCUSDT
- **周期**: 1d
- **时间范围**: 2018-01-01 ~ 2025-12-31
- **数据文件**: `data/raw/btc_binance_BTCUSDT_1d.csv`

## 3. 特征配置

- **特征集**: ['technical', 'external_fgi']
- **总特征数**: 59
- **NaN处理**: ffill_then_drop

## 4. 标签配置

- **策略**: reversal
- **窗口 T**: 21 天
- **阈值 X**: 0.05 (5.0%)

## 5. 模型配置

- **类型**: orion_bix
- **参数**:
  - n_estimators: 50
  - random_state: 42

## 6. 评估结果（汇总）

| 指标               |      值 |
|:-----------------|-------:|
| cohen_kappa      | 0.1121 |
| accuracy         | 0.5046 |
| f1_binary        | 0.5363 |
| 正 Kappa 比例    | 79.2% |

## 7. PnL 回测结果

| 指标               |      值 |
|:-----------------|-------:|
| 年化收益 (CAGR)   | 0.42% |
| 最大回撤           | -66.44% |
| 卡玛比率           | 0.01 |
| 夏普比率           | 0.12 |
| 交易次数           | 956 |
| 胜率               | 46.8% |

## 8. Walk-Forward Fold 详情

- **方法**: walk_forward
- **初始训练集**: 1500
- **OOS窗口**: 63
- **步进**: 21
- **总 Fold 数**: 24

|   fold_id |   train_end |   kappa |   accuracy |   f1 |
|----------:|------------:|--------:|----------:|-----:|
|    1 | 1500 | 0.0850 | 0.3492 | 0.3279 |
|    2 | 1521 | 0.0473 | 0.2698 | 0.2581 |
|    3 | 1542 | 0.0223 | 0.2063 | 0.2647 |
|    4 | 1563 | 0.0203 | 0.2698 | 0.0800 |
|    5 | 1584 | 0.3090 | 0.6349 | 0.6761 |
|    6 | 1605 | 0.4340 | 0.6984 | 0.7397 |
|    7 | 1626 | 0.2752 | 0.5873 | 0.6176 |
|    8 | 1647 | 0.1049 | 0.3810 | 0.3810 |
|    9 | 1668 | 0.0909 | 0.4762 | 0.6118 |
|    10 | 1689 | 0.2683 | 0.6825 | 0.7674 |
|    11 | 1710 | 0.1411 | 0.6349 | 0.7416 |
|    12 | 1731 | -0.2841 | 0.4762 | 0.6452 |
|    13 | 1752 | 0.0000 | 0.6032 | 0.7525 |
|    14 | 1773 | 0.4017 | 0.6825 | 0.7222 |
|    15 | 1794 | 0.0982 | 0.5556 | 0.1765 |
|    16 | 1815 | 0.1478 | 0.5556 | 0.5172 |
|    17 | 1836 | -0.0090 | 0.4921 | 0.5152 |
|    18 | 1857 | -0.0135 | 0.5079 | 0.5974 |
|    19 | 1878 | 0.0131 | 0.5079 | 0.4561 |
|    20 | 1899 | 0.1923 | 0.4921 | 0.4839 |
|    21 | 1920 | 0.0816 | 0.3651 | 0.4444 |
|    22 | 1941 | 0.1043 | 0.5714 | 0.7097 |
|    23 | 1962 | 0.1599 | 0.5690 | 0.6835 |
|    24 | 1983 | 0.0000 | 0.5405 | 0.7018 |

---

*报告生成时间: 2026-02-18 11:17:00*

## PnL 回测代码

```python
# PnL 回测核心逻辑
from src.evaluation.pnl import calculate_pnl_metrics

pred_df = pd.read_csv('predictions.csv')
prices_df = pd.read_csv('data/raw/btc_binance_BTCUSDT_1d.csv')
prices_df['date'] = pd.to_datetime(prices_df['date'])
prices_df = prices_df.sort_values('date').reset_index(drop=True)

y_true = pred_df['y_true'].values
y_pred = pred_df['y_pred'].values
prices = prices_df['close']

min_len = min(len(y_true), len(prices))
y_true = y_true[:min_len]
y_pred = y_pred[:min_len]
prices = prices.iloc[:min_len]

metrics = calculate_pnl_metrics(
    y_true=y_true,
    y_pred=y_pred,
    prices=prices,
    position_size=1.0,
    transaction_cost=0.001,
    risk_free_rate=0.0,
    periods_per_year=52.0,
)
```