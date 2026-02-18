# 实验报告: weekly_bull_v27_orion_001

**生成时间**: 2026-02-18 12:59:59

## 1. 实验概要

| 项目 | 值 |
|------|------|
| 实验名称 | weekly_bull_v27_orion_001 |
| 描述 | Bull v27: Orion-BiX 实验001 - n_estimators=100 增加模型容量 (2026-02-18) |
| 标签 | ['weekly', 'bull', 'binary', 'v27', 'orion', 'orion-bix', 1, 'n100'] |
| 模型类型 | orion_bix |
| 随机种子 | 42 |

## 2. 数据配置

- **数据源**: binance
- **交易对**: BTCUSDT
- **周期**: 1d
- **时间范围**: 2018-01-01 ~ 2025-12-31
- **数据文件**: `data/raw/btc_binance_BTCUSDT_1d.csv`

## 3. 特征配置

- **特征集**: ['technical', 'volume', 'flow', 'market_structure', 'external_fgi', 'regime']
- **总特征数**: 148
- **NaN处理**: ffill_then_drop

## 4. 标签配置

- **策略**: reversal
- **窗口 T**: 21 天
- **阈值 X**: 0.05 (5.0%)

## 5. 模型配置

- **类型**: orion_bix
- **参数**:
  - n_estimators: 100
  - random_state: 42

## 6. 评估结果（汇总）

| 指标               |      值 |
|:-----------------|-------:|
| cohen_kappa      | 0.1125 |
| accuracy         | 0.5219 |
| f1_binary        | 0.5419 |
| 正 Kappa 比例    | 70.8% |

## 7. PnL 回测结果

| 指标               |      值 |
|:-----------------|-------:|
| 年化收益 (CAGR)   | 4.76% |
| 最大回撤           | -58.72% |
| 卡玛比率           | 0.08 |
| 夏普比率           | 0.34 |
| 交易次数           | 980 |
| 胜率               | 47.7% |

## 8. Walk-Forward Fold 详情

- **方法**: walk_forward
- **初始训练集**: 1500
- **OOS窗口**: 63
- **步进**: 21
- **总 Fold 数**: 24

|   fold_id |   train_end |   kappa |   accuracy |   f1 |
|----------:|------------:|--------:|----------:|-----:|
|    1 | 1500 | 0.3343 | 0.6508 | 0.7250 |
|    2 | 1521 | 0.0152 | 0.4127 | 0.5195 |
|    3 | 1542 | -0.0303 | 0.3492 | 0.4938 |
|    4 | 1563 | 0.0000 | 0.7619 | 0.8649 |
|    5 | 1584 | 0.0000 | 0.6984 | 0.8224 |
|    6 | 1605 | 0.0000 | 0.4286 | 0.6000 |
|    7 | 1626 | 0.0786 | 0.4444 | 0.5333 |
|    8 | 1647 | 0.0398 | 0.2698 | 0.3429 |
|    9 | 1668 | 0.1142 | 0.4921 | 0.6190 |
|    10 | 1689 | -0.0755 | 0.3968 | 0.3871 |
|    11 | 1710 | 0.0481 | 0.3016 | 0.1852 |
|    12 | 1731 | 0.0049 | 0.3810 | 0.0930 |
|    13 | 1752 | 0.0000 | 0.6032 | 0.7525 |
|    14 | 1773 | 0.5044 | 0.7460 | 0.7500 |
|    15 | 1794 | 0.0655 | 0.5397 | 0.1212 |
|    16 | 1815 | 0.1438 | 0.6190 | 0.4286 |
|    17 | 1836 | 0.2158 | 0.5714 | 0.4255 |
|    18 | 1857 | 0.1993 | 0.6032 | 0.6377 |
|    19 | 1878 | 0.3388 | 0.6667 | 0.6441 |
|    20 | 1899 | 0.1639 | 0.4603 | 0.4688 |
|    21 | 1920 | 0.0692 | 0.3492 | 0.4384 |
|    22 | 1941 | 0.2418 | 0.6349 | 0.7416 |
|    23 | 1962 | 0.2271 | 0.6034 | 0.7089 |
|    24 | 1983 | 0.0000 | 0.5405 | 0.7018 |

---

*报告生成时间: 2026-02-18 12:59:59*

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