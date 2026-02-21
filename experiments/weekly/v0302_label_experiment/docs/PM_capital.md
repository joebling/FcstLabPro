现在我们从“策略研究员”正式升级到“PM”。

目标：

> 不再讨论单一策略好不好
> 而是 —— 如果我是资金管理人，我如何分配资本？

我会分两部分：

1️⃣ PM 级资金分配模拟
2️⃣ Regime-Switching + MR + Trend 组合结构

---

# 第一部分：PM 级资金分配模拟

我们先客观评估你当前 MR 策略（PS2_linear）。

## 已知数据

| 指标     | MR 策略 |
| ------ | ----- |
| Sharpe | 0.95  |
| 年化收益   | 3.29% |
| 年化波动   | 3.48% |
| MaxDD  | 3.75% |

这是一个：

> 低波动低收益 alpha sleeve

---

## Step 1：假设 1 亿美元 AUM

如果：

```id="x1m3z9"
100% 资金 → MR
```

预期：

* 年化收益 ≈ 3.3M
* 最大回撤 ≈ 3.7M

这非常“安全”。

但问题：

> 3.3% 年化，对 crypto fund 来说几乎不可接受。

---

## Step 2：现实 PM 会怎么做？

通常结构：

```id="r2m5k1"
Core Beta + Tactical Alpha + Vol Overlay
```

假设：

* 40% BTC Beta
* 30% Trend
* 30% MR

---

## Step 3：组合模拟（理论）

我们假设：

| 策略       | 年化收益 | 波动   | Sharpe |
| -------- | ---- | ---- | ------ |
| BTC Beta | 20%  | 60%  | 0.33   |
| Trend    | 25%  | 40%  | 0.63   |
| MR       | 3.3% | 3.5% | 0.95   |

假设相关性：

|       | Beta | Trend | MR  |
| ----- | ---- | ----- | --- |
| Beta  | 1    | 0.7   | 0.2 |
| Trend | 0.7  | 1     | 0.1 |
| MR    | 0.2  | 0.1   | 1   |

组合（40/30/30）结果近似：

* 年化收益 ≈ 17–19%
* 波动 ≈ 30–35%
* Sharpe ≈ 0.55–0.6
* MaxDD 明显低于纯 Beta

这才是 PM 逻辑。

MR 在组合中作用是：

> 压低尾部风险
> 提供负相关收益
> 平滑 equity curve

而不是主收益引擎。

---

# 第二部分：Regime-Switching + MR + Trend 结构

现在进入真正高级部分。

---

# 核心思想

dip_recovery 不是赚钱机器。

它是：

> 环境识别器

所以我们设计：

```id="z9x1c8"
Regime Detector → Strategy Switcher → Capital Allocator
```

---

# Step 1：Regime 定义

用 dip_prob：

```python
if prob > 0.75:
    regime = "HIGH_VOL_REVERSAL"
elif prob < 0.55:
    regime = "TREND"
else:
    regime = "NEUTRAL"
```

---

# Step 2：三策略结构

### 1️⃣ MR 策略（高波动反转环境）

* 等待 dip ≥5%
* TP 4%
* SL 3%
* 持仓 14 天

---

### 2️⃣ Trend 策略（趋势环境）

简单但有效：

```python
if close > MA200 and close > MA50:
    long
exit when close < MA50
```

或用 breakout 结构。

---

### 3️⃣ Neutral 策略（资金保守）

* 低仓位趋势
* 或 50% BTC Beta

---

# Step 3：动态资金分配

### 硬切换版本

```id="m8q3v7"
HIGH_VOL → 100% MR
TREND → 100% Trend
NEUTRAL → 50% Beta
```

---

### 软切换版本（更机构）

```id="a7w4l2"
w_MR = prob
w_Trend = 1 - prob
```

并加限制：

```id="k2d8s5"
0 ≤ w ≤ 0.8
```

---

# Step 4：Vol Targeting

设组合目标波动：

```id="t1n6r4"
target_vol = 20%
```

根据 realized vol 调整杠杆：

```id="p3f7y9"
leverage = target_vol / realized_vol
```

---

# Step 5：完整执行伪代码

```python
for date in OOS:

    prob = model.predict(date)

    regime = detect_regime(prob)

    if regime == "HIGH_VOL_REVERSAL":
        w_MR = min(prob, 0.8)
        w_Trend = 0

    elif regime == "TREND":
        w_MR = 0
        w_Trend = 0.8

    else:
        w_MR = 0.3
        w_Trend = 0.3

    apply_vol_targeting()

    execute_strategies(w_MR, w_Trend)
```

---

# 第三部分：必须做的 PM 级验证

## 1️⃣ 资本利用率

计算：

```id="f9g2t6"
average_gross_exposure
```

如果 < 30%，说明资本闲置严重。

---

## 2️⃣ 贡献分解

分析：

* MR 贡献多少收益？
* Trend 贡献多少？
* 是否某一个 dominate？

---

## 3️⃣ 极端行情测试

单独跑：

* 2022 熊市
* 2024 牛市

看是否 regime 切换正确。

---

## 4️⃣ 成本压力

手续费 ×2
滑点 ×2

组合 Sharpe 是否 >0.7？

---

# 第四部分：你现在的真实位置

你已经完成：

* 模型层
* 事件层
* 执行层

现在进入：

> 组合层（Portfolio Construction）

这才是真正 PM 技能。

---

# 最后一句重要判断

当前 MR 策略：

> 不是主引擎
> 是风险调节器

真正可观的 Sharpe 可能来自：

```id="h8u3m1"
Regime switching 结构
```

而不是单策略优化。

---
