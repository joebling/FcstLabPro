# v0302 Label 策略对比实验报告

> 实验日期: 2026-02-21
> 实验类型: weekly bull

---

## 一、实验概述

对比三种 Label 策略在 weekly bull 场景下的预测能力，筛选最佳部署方案。

---

## 二、实验配置

| 参数 | 值 |
|------|-----|
| 预测窗口 T | 21 |
| 初始训练集 | 800 |
| OOS 窗口 | 63 |
| Step | 21 |
| Purge Gap | 21 |
| 特征数 | 148 |
| 模型 | orion_bix |

---

## 三、Label 策略

| 策略 | 目录 | 描述 |
|------|------|------|
| simple_return | weekly_bull_v0302_simple_return | 预测未来 T 天是否上涨 (future_return > 0) |
| excess_return | weekly_bull_v0302_excess_return | 预测未来 T 天是否跑赢滚动平均 |
| dip_recovery | weekly_bull_v0302_dip_recovery | 预测未来 T 天内是否从当前低点反弹 (dip > 5% 且 recovery > 3%) |

---

## 四、结果对比

| 指标 | simple_return | excess_return | **dip_recovery** |
|------|---------------|---------------|------------------|
| Cohen's Kappa (平均) | 0.0910 | 0.0693 | **0.4366** |
| Cohen's Kappa (整体) | 0.0093 | 0.0850 | **0.5082** |
| Accuracy | 0.4930 | 0.5516 | **0.7563** |
| F1 Binary | 0.4178 | 0.3182 | **0.7280** |
| Precision Binary | 0.6030 | 0.4928 | **0.8210** |
| Recall Binary | 0.4849 | 0.3934 | **0.7448** |
| 正 Kappa 比例 | 65.5% | 55.2% | **87.9%** |
| Fold 数 | 58 | 58 | 58 |

---

## 五、各策略分析

### simple_return
- **表现**: Kappa 接近 0，几乎没有预测能力
- **准确率**: 49.3%（接近随机猜测）
- **结论**: ❌ 不适合部署

### excess_return
- **表现**: Kappa 较低，预测能力有限
- **准确率**: 55.2%（略高于随机）
- **结论**: ❌ 不适合部署

### dip_recovery
- **表现**: Cohen's Kappa (整体) = 0.5082，表现优异
- **准确率**: 75.6%，显著高于其他策略
- **稳定性**: 87.9% 的 fold 具有正 Kappa
- **Precision**: 82.1%（预测为正的样本中 82.1% 正确）
- **结论**: ✅ **推荐部署**

---

## 六、输出目录

```
experiments/weekly/
├── weekly_bull_v0302_simple_return/
│   ├── model.joblib
│   ├── scaler.joblib
│   ├── feature_cols.joblib
│   ├── config.yaml
│   ├── metrics.json
│   ├── fold_metrics.csv
│   └── report.md
├── weekly_bull_v0302_excess_return/
│   ├── model.joblib
│   ├── scaler.joblib
│   ├── feature_cols.joblib
│   ├── config.yaml
│   ├── metrics.json
│   ├── fold_metrics.csv
│   └── report.md
└── weekly_bull_v0302_dip_recovery/  # 推荐部署
    ├── model.joblib
    ├── scaler.joblib
    ├── feature_cols.joblib
    ├── config.yaml
    ├── metrics.json
    ├── fold_metrics.csv
    └── report.md
```

---

## 七、最终建议

**部署 dip_recovery 策略**，原因：
1. 预测能力最强（Kappa = 0.5082）
2. 准确率最高（75.6%）
3. 稳定性最好（87.9% 的 fold 正 Kappa）
4. Label 语义与实际交易场景高度相关（寻找抄底反弹机会）

---
**** double check

非常好 👍

你现在这一步，比任何“Sharpe 提升”都重要。

我给你一个**机构级 double check 清单**，你按这个逐条验证。
不要凭感觉，要用脚本打出来。

---

# ✅ 第一组：数据与泄露检查（必须 100% 确认）

### 1️⃣ Purge Gap 是否真的生效？

你配置写的是：

```
Purge Gap = 21
Step = 21
```

请确认：

* train 的最后一天 ≤ test 起点 - 21
* label 计算窗口没有与 train 重叠
* 特征 rolling window 没跨越 purge 区间

打印：

```
train_end
test_start
label_start
label_end
```

逐 fold 检查 3 个例子。

---

### 2️⃣ scaler 是否每 fold 重新 fit？

确认代码里是：

```python
scaler = StandardScaler()
scaler.fit(train_X)
X_train = scaler.transform(train_X)
X_test = scaler.transform(test_X)
```

而不是：

```python
scaler.fit(full_X)
```

这个是最常见伪 alpha 来源。

---

### 3️⃣ 是否存在未来特征？

重点查：

* rolling mean 是否使用 center=True
* 是否有 shift(-1)
* 是否用到 future high/low

尤其 dip_recovery 这种 label，

你必须确保 feature 没用到未来 low。

---

# ✅ 第二组：统计 sanity check

### 4️⃣ 正样本比例是多少？

打印：

```
y.mean()
```

如果正样本 = 25%，
baseline accuracy = 75%。

那你 75.6% 没意义。

---

### 5️⃣ 混淆矩阵

输出：

```
confusion_matrix
```

看：

* 是否模型只是在极端波动区间预测正
* 是否存在严重 class imbalance

---

### 6️⃣ Fold Kappa 分布图

画：

```
hist(fold_kappa)
```

如果：

* 10 个 fold > 0.8
* 其余接近 0

那说明是某段行情驱动。

---

# ✅ 第三组：结构攻击测试（最关键）

### 7️⃣ 随机标签测试

```python
y_shuffled = np.random.permutation(y)
```

重新跑 5 次。

Kappa 应该接近 0。

如果 >0.05，pipeline 仍有问题。

---

### 8️⃣ 阈值敏感性测试

把：

```
dip > 5%
```

改成：

* 4%
* 6%
* 7%

如果 Kappa 崩塌，

说明过拟合 5% 结构。

真正 alpha 不应该对阈值这么敏感。

---

### 9️⃣ Horizon 平移测试

把 T=21 改成：

* 18
* 25
* 30

真实 alpha 应该平滑下降，
而不是断崖式消失。

---

# ✅ 第四组：经济验证（最重要）

现在你全是 classification 指标。

必须做：

```
probability → position sizing → PnL
```

测试：

* 成本后 Sharpe
* Max DD
* Turnover
* 盈亏分布

如果 Kappa=0.5，
Sharpe 却只有 1.2，

说明：

> 分类好 ≠ 赚钱强

---

# ✅ 第五组：跨资产验证（终极测试）

把模型直接复制到：

* ETHUSDT
* SOLUSDT

如果 IC 仍 >0.1，

那才是真 alpha。

如果直接归零，

那说明是 BTC 特定结构。

---

# ⚠️ 你现在最重要的心理状态

不要去“证明它对”。

要去：

> 试图摧毁它。

如果它 survive，

那才值得部署。

---

# 🎯 我给你的预判

dip_recovery 很可能：

* 不是伪 alpha
* 但会明显低于 0.5 Kappa
* Sharpe 不会大幅优于之前

如果它真的 survive 上面所有攻击，

那我会承认：

> 你抓到了一个结构性 crypto edge。

---

等你 double check 完，

把这几项发给我：

1. 正样本比例
2. 随机标签 Kappa
3. 阈值敏感性结果
4. 成本后 Sharpe
5. ETH 测试结果

我们做最后一轮专业判断。
