# FcstLabPro v0215 部署报告

**生成日期**: 2026-02-15

---

## 一、部署模型概述

根据 `deploy_v0215.sh` 脚本，v0215 版本部署配置如下：

| 组件 | 模型 | 预测窗口 T | 说明 |
|------|------|------------|------|
| **Bull 模型** | Orion-BiX | T=21 | 预测BTC未来21天是否大涨 |
| **Bear 模型** | LightGBM | T=28 | 预测BTC未来28天是否大跌 |

**部署信息**:
- 镜像: `fcstlabpro-0215:latest`
- 运行时间: 每天北京时间 08:00 (UTC 00:00)
- 区域: asia-east1 (台湾)
- 运行环境: Google Cloud Run Job

---

## 二、模型配置详情

### Bull 模型 (Orion-BiX v27)

配置文件: `configs/experiments/weekly/exp_weekly_bull_v27_orion.yaml`

| 配置项 | 值 |
|--------|-----|
| 模型类型 | Orion-BiX |
| 预测窗口 T | 21 天 |
| 标签策略 | reversal (反转) |
| 阈值 X | 0.05 (5%波动) |
| 特征集 | technical + volume + flow + market_structure + external_fgi + regime |
| 标准化 | StandardScaler |
| 估计器数量 | 16 |

### Bear 模型 (GBDT v13)

根据 `reports/orion_vs_gbdt_comparison.md`，Orion-BiX 无法处理 Bear 信号的极端类别不平衡问题（Kappa=0），建议回归 GBDT v13。

| 配置项 | 值 |
|--------|-----|
| 模型类型 | LightGBM |
| 预测窗口 T | 28 天 |
| Kappa | 0.0529 |
| 特征集 | technical + volume + flow + market_structure + external_fgi |

---

## 三、模型特征详情

### 3.1 特征集总览

| 特征集 | Bull 模型 | Bear 模型 | 说明 |
|--------|-----------|-----------|------|
| technical | ✓ | ✓ | 技术指标（均线、RSI、MACD、布林带等） |
| volume | ✓ | ✓ | 成交量特征（量能均线、OBV、VWAP等） |
| flow | ✓ | ✓ | 资金流特征（资金变化率、量价背离等） |
| market_structure | ✓ | ✓ | 市场结构特征（CVD、资金费率代理等） |
| external_fgi | ✓ | ✓ | 外部恐惧贪婪指数（FGI） |
| regime | ✓ | - | 市场状态特征（牛熊市区分） |

### 3.2 特征详细说明

#### 技术指标 (technical) - 约 50 个特征

| 特征类别 | 特征名模式 | 具体含义 |
|----------|-----------|----------|
| 移动平均线 | sma_5/10/20/50/100/200, ema_5/10/20/50/100/200 | 不同周期的简单/指数移动平均线 |
| 均线交叉 | sma_cross_5_20, sma_cross_10_50, sma_cross_50_200 | 短期均线上穿/下穿长期均线的信号 |
| 相对位置 | price_vs_sma_20/50/200 | 价格相对均线的偏离程度 |
| RSI | rsi_6/14/28 | 相对强弱指标，衡量超买超卖 |
| MACD | macd, macd_signal, macd_hist | 移动平均收敛发散指标及其信号线 |
| 布林带 | bb_upper_20, bb_lower_20, bb_width_20, bb_pctb_20 | 价格波动区间及在区间内位置 |
| ATR | atr_14/21, atr_pct_14/21 | 平均真实波幅，衡量波动率 |
| 收益 | return_1/3/5/7/14/21d | 不同周期的价格收益率 |
| 波动率 | volatility_5/10/20d | 不同周期的收益率标准差 |
| 高低价距离 | high_14/21/50d_dist, low_14/21/50d_dist | 当前价格距N日内最高/最低的距离 |
| 随机指标 | stoch_k_14, stoch_d_14 | KDJ 指标的 K/D 值 |

#### 成交量特征 (volume) - 约 25 个特征

| 特征类别 | 特征名模式 | 具体含义 |
|----------|-----------|----------|
| 量能均线 | vol_sma_5/10/20/50 | 成交量的移动平均 |
| 量能比率 | vol_ratio_5/10/20/50 | 当日成交量 / 均线量能 |
| 量能变化 | vol_change_1/3/5d | 成交量环比变化率 |
| 量价相关 | vol_price_corr_10/20 | 成交量与价格的滚动相关系数 |
| OBV | obv, obv_sma_10/20 | 能量潮指标及其均线 |
| VWAP | vwap_10/20, price_vs_vwap_10/20 | 成交量加权平均价及偏离度 |
| 量能波动 | vol_volatility_10/20 | 成交量变化的标准差 |

#### 资金流特征 (flow) - 约 20 个特征

| 特征类别 | 特征名模式 | 具体含义 |
|----------|-----------|----------|
| 交易笔数 | trades_sma_5/10/20, trades_ratio_5/10/20 | 交易笔数的均线和比率 |
| 交易变化 | trades_change_1/5d | 交易笔数的变化率 |
| 单笔量 | avg_trade_size, avg_trade_size_sma_5/10/20 | 平均每笔成交量及均线 |
| 资金流变化 | flow_change_1/3/5/10d | 计价货币成交额的变化率 |
| 资金流动量 | flow_momentum_5/10/20 | 资金流均线的动量 |
| 量价背离 | flow_price_divergence_10/20 | 资金流与价格变化的差值 |
| 成交密度 | volume_density, volume_density_sma_5/10 | 成交量 / 价格波动幅度 |

#### 市场结构 (market_structure) - 约 30 个特征

| 特征类别 | 特征名模式 | 具体含义 |
|----------|-----------|----------|
| 资金费率代理 | funding_rate_7/14/24 | 基于价格动量模拟的资金费率 |
| 未平仓代理 | open_interest_7/14/24 | 基于成交量累积的代理指标 |
| CVD | cvd, cvd_ma_7/14/21, cvd_change_7/14/21 | 累积成交量差量及其变化 |
| 稳定币流入 | stablecoin_inflow_proxy | 价格下跌时的成交额代理 |
| 买入压力 | buy_pressure, buy_pressure_ma_5/10/20 | (收盘价-最低价)/(最高价-最低价) |
| 交易活跃度 | trades_sma/ratio, trades_change | 同 flow 特征 |
| 单笔成交额 | avg_trade_size, avg_trade_size_ma/ratio | 同 flow 特征 |
| 资金流 | qvol_sma/ratio, flow_change, flow_price_divergence | 同 flow 特征 |

#### 外部恐惧贪婪指数 (external_fgi) - 约 11 个特征

| 特征名 | 具体含义 |
|--------|----------|
| ext_fgi | 恐惧贪婪指数原始值 (0-100) |
| ext_fgi_ma7/14/30 | 7/14/30日均线 |
| ext_fgi_change_7/14d | 7/14日变化率 |
| ext_fgi_std_14 | 14日波动率 |
| ext_fgi_extreme_fear | 极度恐慌标记 (FGI<25) |
| ext_fgi_extreme_greed | 极度贪婪标记 (FGI>75) |
| ext_fgi_price_divergence | FGI与价格变化的背离 |

#### 市场状态 (regime) - 约 13 个特征 (仅 Bull 模型)

| 特征名 | 具体含义 |
|--------|----------|
| sma_200 | 200日简单移动平均线 |
| regime_price_vs_ma200 | 价格相对200日均线的偏离比例 |
| regime_bull | 牛市标记 (价格>200日均线) |
| regime_bear | 熊市标记 (价格<200日均线) |
| regime_sideways | 震荡市标记 (价格在均线±5%内) |
| regime_trend_50/100/200 | 价格相对不同周期均线的偏离 |
| regime_ma200_rise/fall | 200日均线上升/下降标记 |
| regime_vol_high/low | 高/低波动率标记 |

### 3.3 特征数量统计

| 模型 | 特征集 | 估计特征数量 |
|------|--------|-------------|
| Bull (Orion-BiX v27) | technical + volume + flow + market_structure + external_fgi + regime | ~150 个 |
| Bear (GBDT v13) | technical + volume + flow + market_structure + external_fgi | ~130 个 |

---

## 四、模型性能对比

### 3.1 Kappa 指标

| 模型 | Bull Kappa | Bear Kappa | 状态 |
|------|------------|------------|------|
| GBDT v15 | 0.1110 | - | Bull 最优 |
| GBDT v13 | - | 0.0529 | Bear 最优 |
| **Orion-BiX v27** | **0.1122** | 0.0000 | Bull 突破，Bear 失败 |

### 3.2 PnL 回测结果

运行 `scripts/pnl_backtest.py` 得到的回测结果：

| 指标 | GBDT v15 | Orion-BiX v27 | 差异 |
|------|----------|----------------|------|
| **平均 Kappa** | 0.1756 | 0.1122 | -0.0634 |
| **正 Kappa 比例** | 92.3% | 69.6% | -22.7% |
| **年化收益** | -11.00% | **+26.63%** | +37.63% |
| **平均最大回撤** | 20.57% | **17.45%** | -3.12% |
| **卡玛比率** | -0.53 | **+1.53** | +2.06 |
| **夏普比率** | 0.03 | **+0.80** | +0.77 |

---

## 四、关键发现

### 4.1 Bull 模型 (Orion-BiX v27)
- **Kappa 略有提升**: 0.1110 → 0.1122 (+0.0012)
- **PnL 显著改善**: 年化收益从 -11% 提升至 +26.63%
- **风险控制更好**: 最大回撤从 20.57% 降至 17.45%
- **卡玛比率转正**: 从 -0.53 提升至 +1.53
- **夏普比率大幅改善**: 从 0.03 提升至 0.80

### 4.2 Bear 模型 (GBDT v13)
- **Orion-BiX 完全失败**: Kappa = 0.0000，无法处理极端类别不平衡
- **类别分布问题**: 负类 89.4%，正类 10.6%
- **建议**: 继续使用 GBDT v13 (Kappa=0.0529)

---

## 五、部署建议

基于 PnL 回测结果，建议采用以下混合策略：

| 信号 | 模型 | 理由 |
|------|------|------|
| Bull (看涨) | Orion-BiX v27 | PnL 表现优异，年化收益 +26.63%，卡玛比率 1.53 |
| Bear (看跌) | GBDT v13 | Orion-BiX 无法处理类别不平衡，GBDT Kappa=0.0529 已验证 |

---

## 六、风险提示

1. **模型 Kappa 较低**: 0.11 左右的 Kappa 预测力有限，仅作辅助参考
2. **Orion-BiX 波动性大**: Kappa 标准差 ±0.22，部分 fold 表现极好/差
3. **Bear 信号稀缺**: BTC 长期牛市，大跌信号天然稀少
4. **回测 vs 实盘**: 历史回测表现不代表未来收益

---

*报告生成时间: 2026-02-15*
