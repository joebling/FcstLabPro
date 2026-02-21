好。

下面给你一个**真正 institutional 级别的完整结构**。
不是玩具回测，而是：

* 可扩展
* 无自欺
* 支持 walk-forward
* 支持 regime switching
* 支持多策略组合
* 支持成本模型
* 支持真实交易约束

我分三部分写：

1. 完整回测伪代码架构
2. Walk-forward 执行框架
3. Regime-switching 双策略系统

---

# 第一部分：完整回测伪代码结构

我们构建 7 层架构：

```
Data → Feature → Model → Signal → Trigger → Execution → Risk → PnL
```

---

## 1️⃣ 数据层

必须只允许历史可见数据。

```python
class DataHandler:

    def __init__(self, price_df):
        self.price = price_df

    def get_history(self, end_date):
        return self.price[self.price.date <= end_date]

    def get_future_window(self, start_date, horizon):
        return self.price[
            (self.price.date > start_date) &
            (self.price.date <= start_date + horizon)
        ]
```

禁止在任何地方访问未来数据。

---

## 2️⃣ Feature 层

```python
class FeatureEngine:

    def compute_features(self, hist_df):
        df = hist_df.copy()

        df["ret_1d"] = df.close.pct_change(1)
        df["ret_5d"] = df.close.pct_change(5)
        df["vol_20"] = df.ret_1d.rolling(20).std()
        df["rsi"] = compute_rsi(df.close)

        return df.dropna()
```

必须保证：

* 不使用 shift(-1)
* 不使用 center=True
* 不用未来 rolling

---

## 3️⃣ Model 层

```python
class DipRecoveryModel:

    def fit(self, X_train, y_train):
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X_train)

        self.model = LogisticRegression()
        self.model.fit(X_scaled, y_train)

    def predict_prob(self, X):
        X_scaled = self.scaler.transform(X)
        return self.model.predict_proba(X_scaled)[:, 1]
```

每个 fold 重新 fit。

---

## 4️⃣ Signal 层（环境预测）

```python
class RegimeSignal:

    def generate(self, prob, threshold=0.7):
        if prob > threshold:
            return "HIGH_V"
        else:
            return "NORMAL"
```

---

## 5️⃣ Trigger 层（路径对齐关键）

```python
class TriggerEngine:

    def check_long_trigger(self, entry_price, current_price):
        drawdown = (current_price - entry_price) / entry_price

        if drawdown <= -0.04:
            return True
        return False
```

关键思想：

> 预测环境
> 等待 dip 出现
> 再入场

---

## 6️⃣ Execution 层

```python
class ExecutionEngine:

    def execute_trade(self, side, price, size):
        slippage = price * 0.0005
        fee = price * 0.0004

        if side == "BUY":
            exec_price = price + slippage
        else:
            exec_price = price - slippage

        cost = fee
        return exec_price, cost
```

必须显式加入：

* 滑点
* 手续费
* 资金成本（如有）

---

## 7️⃣ Risk 层

```python
class RiskManager:

    def __init__(self):
        self.max_dd_cutoff = 0.3

    def position_size(self, prob):
        size = 2 * (prob - 0.5)
        return max(0, min(size, 1))

    def check_portfolio_dd(self, equity_curve):
        dd = compute_drawdown(equity_curve)
        if dd > self.max_dd_cutoff:
            return "STOP_TRADING"
        return "OK"
```

---

## 8️⃣ 主回测循环

```python
for date in backtest_dates:

    hist = data.get_history(date)
    features = feature_engine.compute_features(hist)

    prob = model.predict_prob(features.iloc[-1])

    regime = regime_signal.generate(prob)

    if regime == "HIGH_V":
        if trigger_engine.check_long_trigger(reference_price, current_price):
            size = risk_manager.position_size(prob)
            exec_price, cost = execution.execute_trade("BUY", current_price, size)
            portfolio.open_position(exec_price, size)
    
    portfolio.update_mark_to_market(current_price)
```

---

# 第二部分：Walk-Forward 执行框架

这是机构真正的结构。

---

## 参数

```
init_train = 800
oos_window = 63
step = 21
purge_gap = 21
```

---

## Walk-forward 主逻辑

```python
start = 0

while True:

    train_start = start
    train_end = start + init_train

    test_start = train_end + purge_gap
    test_end = test_start + oos_window

    if test_end > len(data):
        break

    # 切分数据
    train_data = data[train_start:train_end]
    test_data = data[test_start:test_end]

    # 构建特征
    X_train, y_train = build_dataset(train_data)
    X_test, y_test = build_dataset(test_data)

    # 训练
    model.fit(X_train, y_train)

    # 生成 OOS 预测
    for t in test_data:
        prob = model.predict_prob(X_test[t])
        store_prediction(t, prob)

    start += step
```

---

## 重要原则

* 绝不 overlap label
* 绝不 overlap purge
* 绝不 refit 用 test 数据

---

# 第三部分：Regime-Switching 双策略系统

这是核心升级。

我们构建：

```
Strategy A: Mean Reversion (dip_recovery)
Strategy B: Trend Following
```

---

## 1️⃣ Regime 判定

```python
if dip_prob > 0.7:
    regime = "MEAN_REVERSION"
else:
    regime = "TREND"
```

---

## 2️⃣ Strategy A：均值回归

```python
if regime == "MEAN_REVERSION":

    if drawdown >= 4%:
        enter_long()
    
    exit:
        take_profit = 6%
        stop_loss = -5%
        time_stop = 14 days
```

---

## 3️⃣ Strategy B：趋势策略

```python
if regime == "TREND":

    if close > MA200 and close > MA50:
        enter_long()

    exit:
        close < MA50
```

---

## 4️⃣ 组合结构

```python
if regime == "MEAN_REVERSION":
    allocate 100% capital to MR
else:
    allocate 100% capital to Trend
```

或软切换：

```python
w_mr = dip_prob
w_trend = 1 - dip_prob
```

---

# 第四部分：实验验证结构

你必须验证 5 个层面：

---

## 实验 A：单策略对比

| 策略            | Sharpe | DD |
| ------------- | ------ | -- |
| Trend only    |        |    |
| MR only       |        |    |
| Regime Switch |        |    |

---

## 实验 B：prob 分层收益

验证：

```
prob 高 → MR 收益高
prob 低 → Trend 收益高
```

否则 regime 无效。

---

## 实验 C：跨资产验证

复制到：

* ETH
* SOL

不能只在 BTC 有效。

---

## 实验 D：交易成本 stress

测试：

* 手续费 ×2
* 滑点 ×2

策略是否仍存活。

---

## 实验 E：极端行情

单独测试：

* 2022 熊市
* 2023 震荡
* 2024 牛市

---

# 最终成功标准

必须同时满足：

```
OOS Sharpe > 1.2
MaxDD < 35%
跨资产仍有效
成本翻倍仍 > 0.8 Sharpe
```

否则不部署。

---

# 最后一句非常重要

不要再优化 Kappa。

真正的优化目标是：

```
Sharpe × Stability × Cross-Asset Robustness
```

---