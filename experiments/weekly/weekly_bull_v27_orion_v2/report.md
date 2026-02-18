# weekly_bull_v27_orion_v2 实验报告

**生成时间**: 2026-02-18 17:40:00

---

## 1. 模型信息

| 项目 | 值 |
|------|-----|
| 实验名称 | weekly_bull_v27_orion_v2 |
| 模型类型 | Orion-BiX |
| 预测窗口 T | 21 天 |
| 标签阈值 X | 0.05 (5%) |
| 标签策略 | reversal |
| n_estimators | 16 |
| random_state | 42 |
| 特征数 | 148 |

## 2. 特征配置

- technical
- volume
- flow
- market_structure
- external_fgi
- regime

## 3. 数据配置

- 数据源: binance
- 交易对: BTCUSDT
- 周期: 1d
- 时间范围: 2018-01-01 ~ 2025-12-31

## 4. 文件清单

| 文件 | 说明 |
|------|------|
| model.joblib | 训练好的模型 (115MB) |
| scaler.joblib | 标准化器 |
| feature_cols.joblib | 特征列名 |
| config.yaml | 配置 |
| meta.json | 元信息 |

## 5. 推理结果

- 日期: 2026-02-17
- 价格: 67753.44 USDT
- Bull 概率: 0.052 (5.2%)

## 6. 注意事项

**信号反转问题**: 经测试，当前模型预测信号与实际收益呈反向关系。建议：
1. 使用时反转信号，或
2. 用正确标签重新训练模型
