下面我给你一套 **完整的机构级 Crypto Alpha 研究框架**，包括：

1. 研究架构设计
2. 真正严格的 Walk-Forward 结构
3. 不自欺的回测规范（Hard Rules）
4. 统计验证标准
5. 常见致命陷阱清单

这套框架是按：
**“如果我要给基金 LP 看，我敢不敢拿出来？”**
这个标准设计的。

---

# 一、Institutional 级 Crypto Alpha 研究框架

整体分成 6 层：

```
Layer 0  数据层 (Data Integrity)
Layer 1  Label 层 (Return Definition)
Layer 2  Signal 层 (Raw Alpha)
Layer 3  Validation 层 (IC & Stability)
Layer 4  Portfolio 层 (Position Construction)
Layer 5  Execution 层 (Realistic Backtest)
```

绝对禁止：

> 把 Layer 2 和 Layer 5 混在一起。

---

# 二、Layer 0 — 数据完整性规范（必须）

### 0.1 所有特征必须满足：

```
feature[t] 只能使用 <= t 时刻数据
```

### 0.2 明确预测时点

统一定义：

```
t = bar close
t+1 open = 交易执行
收益从 t+1 开始计算
```

不能在 t 收盘价预测后，又用 t 收盘成交。

---

# 三、Layer 1 — 正确的 Label 设计

## 1.1 非重叠收益（Non-overlapping）

这是最重要的一条。

错误写法（常见）：

```python
ret[t] = (price[t+14] - price[t]) / price[t]
ret[t+1] = (price[t+15] - price[t+1]) / price[t+1]
```

这会导致：

* 严重自相关
* IC 被放大
* t-stat 失真

---

## 正确写法（Institutional 标准）

如果 horizon = 14 天：

```python
for i in range(0, len(price) - 14, 14):
    ret[i] = (price[i+14] - price[i]) / price[i]
```

每个样本独立。

你损失样本数量，但获得真实统计。

机构永远选真实。

---

# 四、Layer 2 — Alpha 层（只研究 signal）

此阶段：

* 不加 MA
* 不做止损
* 不做资金管理
* 不做杠杆

只看：

```
signal[t] vs future_return[t]
```

---

## 2.1 只做一件事

计算：

```
Rank IC
```

成功标准（单资产时间序列）：

| 等级  | Rank IC   |
| --- | --------- |
| 噪音  | < 0.02    |
| 可疑  | 0.02–0.05 |
| 有价值 | 0.05–0.1  |
| 极强  | >0.1      |

如果你得到 0.5：

> 100% 有问题。

---

# 五、Layer 3 — 真正 Walk-Forward 结构

这是你现在最缺的。

---

## 3.1 正确 Walk-Forward 模式

假设 weekly 数据：

```
train_window = 156 周 (3年)
test_step = 1 周
```

结构：

```
for t in range(train_window, T):

    train_data = data[t-train_window : t]
    test_point = data[t]

    model.fit(train_data)

    pred[t] = model.predict(test_point)
```

这叫：

> expanding / rolling walk-forward

模型每一步都重新训练。

---

## 3.2 严禁

```
train once
predict whole OOS
```

那是研究型验证，不是实盘结构。

---

# 六、Layer 4 — IC 稳定性验证

真正 institutional 统计必须包括：

---

## 4.1 Rolling IC 曲线

```
rolling_52w_IC
```

如果：

* IC 在某段时间完全反向
* 或某段时间归零

说明 regime dependency。

---

## 4.2 IC t-stat 正确算法

必须基于 IC time series：

```
t_stat = mean(IC_series) / (std(IC_series) / sqrt(N))
```

N = IC 时间点数量。

不是样本数量。

---

## 4.3 Regime 分解

例如：

* Bull (price > MA200)
* Bear
* Sideway

如果信号在 bull 正，在 bear 负，

必须显式建模：

```
signal_final = signal * regime_sign
```

而不是事后反转。

---

# 七、Layer 5 — 组合构建

现在才允许做：

* MA filter
* Vol targeting
* Position sizing
* Risk control

---

## 5.1 正确组合方式

建议 crypto 单资产做：

### 方法 A：连续信号

```
position[t] = clip(signal[t], -1, 1)
```

### 方法 B：分位法

```
top 30% → long
bottom 30% → short
```

---

## 5.2 Vol Targeting（强烈推荐）

```
target_vol = 20%
position *= target_vol / realized_vol
```

这比 MA filter 更科学。

---

# 八、不会骗自己的回测规范

这是最重要的部分。

---

# 🚨 回测硬性规则（Hard Rules）

### 规则 1

> 所有统计必须基于 non-overlapping return

---

### 规则 2

> IC 必须基于 walk-forward 预测

---

### 规则 3

> 不允许根据 OOS 结果决定信号方向

方向必须在研究阶段固定。

---

### 规则 4

> 不允许反复调 horizon 直到最优

horizon 必须提前设定。

---

### 规则 5

> 任何年化 > 200% 必须怀疑代码错误

Crypto 允许高收益，
但 >2000% 基本是 bug。

---

### 规则 6

必须报告：

* IC
* IC t-stat
* OOS Sharpe
* Max DD
* Turnover
* 成本后收益

不能只报年化。

---

# 九、Institutional 验证流程（真正标准）

研究流程应该是：

---

### Step 1

开发 signal（in-sample）

---

### Step 2

锁定模型结构

---

### Step 3

只做一次 OOS 测试

---

### Step 4

OOS 不允许调参

---

### Step 5

再做第二段完全 unseen 数据

---

# 十、真正 Crypto 特有增强

Crypto 不同于股票：

1. 单资产时间序列
2. 极强 regime 切换
3. 高波动
4. 永续合约结构

所以推荐：

---

## 10.1 Regime Switching Alpha

例如：

```
if realized_vol > threshold:
    use mean reversion alpha
else:
    use trend alpha
```

---

## 10.2 Funding 结构

加入：

* funding rate
* OI change
* perp-basis

这些是 crypto 特有 alpha。

---

# 十一、你现在的模型真实水平判断

基于经验推断：

修正所有统计问题后，

你的 IC 很可能落在：

```
0.05 – 0.12
```

这已经是不错的 crypto alpha。

但绝对不是 0.5。

---

# 十二、给你一个专业级研究模板结构

```
research/
    data/
    features/
    labels/
    walkforward/
    ic_analysis/
    portfolio/
    execution/
```

每层分离。

绝不混写。

---

# 十三、终极标准

问自己：

> 如果这是一个 1 亿美金基金的策略，
> 我敢不敢用现在的统计方法向 LP 汇报？

如果答案是“不太敢”，

那就继续打磨统计结构。

---

# 最后一句

真正的 professional 量化，

不是追求高收益，

而是：

> 在所有自欺可能性被消灭之后，
> 依然有正的 IC。

---
