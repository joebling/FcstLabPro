# Production Models Summary

**更新时间**: 2026-03-05
**回测区间**: 2022-09-26 ~ 2026-01-25 (1218 个交易日)
**基准**: BTC/USDT 买入持有 Return +350.8%, MaxDD -32.0%

## 0. 上线结论摘要

- **默认推荐**：生产主跑 🛡️ **E1（止盈+regime）**，原因：**MaxDD 更低（-12.7%）**，更贴合风控预算。
- **收益增强备选**：💰 **E8（止盈+regime）** 可并行 paper 观察；它在同配置下 **Return/Sharpe 更高**，但 **回撤更大（-21.4%）且暴露更高**。
- **关键结论**：E1 vs E8 的本质差异只有 **标签定义（终点 vs 路径触达）**；模型/特征/参数一致。
- **上线监控建议**：重点盯 `signals/day`、`exposure`、`rolling win-rate(30 trades)`、`live MaxDD`，以及预测概率分布漂移（均值/方差）。

---

## 一、模型概览

| | e1-conservative | e8-touch |
|---|---|---|
| **定位** | 🛡️ 风控优先 | 💰 收益优先 |
| **标签策略** | `directional_filtered` | `touch_filtered` |
| **部署变体** | conservative (止盈+regime) | conservative (止盈+regime) |
| **模型类型** | LightGBM | LightGBM |
| **特征数** | 129 | 129 |
| **上线日期** | 2026-03-01 | 2026-03-05 |
| **源实验** | weekly_bear_v0305_E1_decontam | weekly_bear_v0305_E8_touch_label |
| **模型哈希** | `4ca65e75f1df1b72` | `ef82f06646a7f79c` |

---

## 二、标签定义对比（核心差异）

### E1: `directional_filtered` — 终点判定

```
Label = 1  当且仅当同时满足:
  ① close[t+T] / close[t] - 1  ≥  X      ← 看第 T 天的收盘价
  ② RSI(14) < 45                         ← 超卖过滤
  ③ close < SMA(50)                      ← 均线下方过滤
```

**判定方式**: 只看终点。未来第 21 天的 **收盘价** 是否比今天高 4%。
中间过程完全忽略——即使第 5 天涨到 +10% 又跌回来，只要第 21 天不够 +4% 就是 Label=0。

### E8: `touch_filtered` — 路径触达

```
Label = 1  当且仅当同时满足:
  ① max(high[t+1 : t+T])  ≥  close[t] × (1+X)   ← 窗口内任意天的最高价
  ② RSI(14) < 45                                 ← 超卖过滤
  ③ close < SMA(50)                               ← 均线下方过滤
```

**判定方式**: 看整条路径。未来 21 天内任意一天的 **最高价** 曾触达过 +4% 就算。
这与生产策略的 `--take-profit` 逻辑一致：止盈单是“路径内触达即平仓”。

### 一个具体例子

假设 BTC 今天 $100，T=21，X=4%（目标 $104）：

```
Day  1: close=$101, high=$102
Day  5: close=$103, high=$106  ← high 触达 $104
Day 10: close=$99,  high=$100
Day 21: close=$102, high=$103  ← 终点只有 +2%
```

| | E1 directional | E8 touch |
|---|---|---|
| **看什么** | Day 21 close=$102 | Day 5 high=$106 |
| **收益率** | +2% < 4% | $106 ≥ $104 ✅ |
| **Label** | **0** ❌ | **1** ✅ |
| **含义** | “拿到到期不够 +4%” | “中途可以止盈 +4%” |

### 关键维度差异

| 维度 | E1 directional | E8 touch |
|------|---------------|----------|
| **时间点** | 只看终点 (Day T) | 看整条路径 [1, T] |
| **价格类型** | close (收盘价) | high (最高价) |
| **正例率** | ~10% (严格) | ~21% (宽松) |
| **类别平衡** | 1:9 (严重不平衡) | 1:4 (较平衡) |
| **与止盈对齐** | ❌ 假设持有到期 | ✅ 路径触达即平仓 |
| **哲学** | “终点收益足够好” | “过程中曾有机会” |

### 过滤条件（两者相同）

```yaml
rsi_window: 14
rsi_threshold: 45       # RSI < 45 才标记做多机会
ma_window: 50
require_below_ma: true  # 价格 < SMA(50) 才标记
```

过滤的作用：只在 **回调/弱势环境** 中寻找反弹机会，避免追高。

> ℹ️ **去污染注意**: 标签使用了 RSI 和 SMA 作为过滤条件，因此模型特征中已删除 `rsi_*`、`price_vs_sma_*`、`sma_cross_10_50`、`sma_cross_50_200`，避免数据泄漏。

---

## 三、分类指标对比

| 指标 | E1 | E8 | 说明 |
|------|-----|-----|---------|
| **Accuracy** | 87.3% | 92.3% | E8 更高（但正例率也更高） |
| **F1** | 0.414 | 0.799 | E8 大幅领先 |
| **Precision** | 0.396 | 0.797 | E8 预测“买”时更准 |
| **Recall** | 0.434 | 0.801 | E8 捕捉更多机会 |
| **Kappa** | 0.343 | 0.751 | E8 一致性更高 |

> ⚠️ E8 分类指标全面领先，但主要因为 touch 标签正例率 (~21%) 比 directional (~10%) 更高，
> 任务天然更容易。**分类指标不能直接跨标签对比，必须看 PnL。**

---

## 四、PnL 回测对比

### 回测假设（上线前需确认口径一致）

- 手续费/滑点：**未在本报告披露**（建议补充：费率、滑点模型、是否按成交量/波动率动态滑点）
- 资金费率/借贷：**未在本报告披露**（若为现货策略请注明 spot-only；若涉及永续请明确 funding 计入方式）
- 信号执行价：**未在本报告披露**（例如按日线收盘生成信号、次日开盘成交，或同日收盘成交）

### 4.1 保守变体（止盈+regime，生产部署配置）

| 指标 | E1 | E8 | 胜者 |
|------|-----|-----|------|
| **Total Return** | +36.7% | +64.3% | E8 🏆 |
| **CAGR** | 9.8% | 16.0% | E8 🏆 |
| **Sharpe** | 0.633 | 0.756 | E8 🏆 |
| **Sortino** | 0.388 | 0.577 | E8 🏆 |
| **MaxDD** | **-12.7%** | -21.4% | E1 🏆 |
| **Calmar** | **0.775** | 0.750 | E1 🏆 |
| **Profit Factor** | **1.318** | 1.283 | E1 🏆 |
| **Win Rate** | 48.5% | 53.0% | E8 🏆 |
| **Trades** | 23 | 30 | E8 更活跃 |
| **Avg Trade** | **0.233%** | 0.218% | E1 🏆 |
| **Exposure** | 13.6% | 23.3% | E8 更高 |

### 4.2 全变体对比

| 变体 | | E1 Return | E1 Sharpe | E8 Return | E8 Sharpe |
|--------|---|-----------|-----------|-----------|----------|
| 基础 (无开关) | | +109.1% | 0.931 | +79.8% | 0.661 |
| +止盈 | | +68.8% | 0.766 | +142.2% | 1.020 |
| +regime | | +61.6% | 0.774 | +21.3% | 0.343 |
| **止盈+regime** | | **+36.7%** | **0.633** | **+64.3%** | **0.756** |

> 💡 E8 在“+止盈”变体下表现最佳 (Sharpe=1.02, Return=142%)，
> 这正好印证了 touch 标签与止盈策略的对齐性。
> 但 MaxDD=-26% 较高，因此生产部署仍使用“止盈+regime”变体。

---

## 五、特征配置（两者完全相同）

```yaml
features:
  sets: [technical, volume, flow, market_structure, external_fgi]
  drop_features: [rsi_*, price_vs_sma_*, sma_cross_10_50, sma_cross_50_200]
  count: 129 (after decontamination)
```

| 特征集 | 数量 | 来源 | E8 Top 特征 |
|--------|------|------|------------|
| technical | ~49 | Binance OHLCV | high/low_50d_dist, BB, MACD |
| volume | ~28 | Binance OHLCV | OBV |
| flow | ~27 | Binance OHLCV | trades_sma |
| market_structure | ~23 | Binance OHLCV | **funding_rate_14** (Top1) |
| external_fgi | ~11 | FGI CSV | ext_fgi_ma30 |

> ℹ️ `funding_rate_14` 是 **模拟** funding rate（= 14天收益率均值 × 100），
> 本质是中期动量指标，不是真实的 Binance 永续合约资金费率。
> 实验 E10 已验证：真实资金费率反而不如这个模拟版有效。

---

## 六、模型参数（两者完全相同）

```yaml
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
    auto_scale_pos_weight: true   # 自动平衡类别权重
```

---

## 七、部署方式

两个模型都使用保守变体部署：

```bash
# E1: 风控优先
python scripts/live_signal.py \
    --model models/production/e1-conservative/model.joblib \
    --config models/production/e1-conservative/config.yaml \
    --take-profit --regime-switch

# E8: 收益优先
python scripts/live_signal.py \
    --model models/production/e8-touch/model.joblib \
    --config models/production/e8-touch/config.yaml \
    --take-profit --regime-switch

# 并行 Paper Trading
python scripts/paper_trading_e1_vs_e8.py --download --save
```

---

## 八、何时选用哪个模型

| 场景 | 推荐 | 原因 |
|------|------|------|
| 资金量大、不能承受大回撤 | 🛡️ E1 | MaxDD -12.7%，Calmar 最高 |
| 追求更高绝对收益 | 💰 E8 | Return +64%，Sharpe 更高 |
| 信号验证、开发测试 | 💰 E8 | 更多交易次数，更快积累数据 |
| 两个都跑、只做共识信号 | ❌ 不推荐 | 实验证明 AND 共识过度过滤 |

---

## 附：实验谱系

```
E1 (directional_filtered)
  └─ E8 (touch_filtered)        ← 标签改进
      ├─ E10 (+真实 FR)          ← 劣化, 已排除
      ├─ E11 (+宏观因子)        ← 劣化, 已排除
      ├─ E12 (+FR+宏观)         ← 劣化, 已排除
      ├─ E13 (特征精简 ≤ 1)     ← 劣化, 已排除
      ├─ E14 (特征精简 ≤ 3)     ← 劣化, 已排除
      └─ AND 共识 (E1×E8)       ← 劣化, 已排除
```

**结论: E1 和 E8 各有所长，当前框架内已接近天花板。它们的唯一差异是标签定义（终点 vs 路径），模型、特征、参数完全一致。**
