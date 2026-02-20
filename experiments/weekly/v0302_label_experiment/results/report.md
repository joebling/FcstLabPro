# R1: Label 对比实验报告

> 实验日期：2026-02-20
> 分支：refactor/v0302-unified-pipeline

---

## 一、实验背景

验证 A1/A2/B/C 四种 Label 策略的预测能力，找出无需信号反转、无需后置 MA 过滤的有效 Label。

## 二、实验配置

| 参数 | 值 |
|------|-----|
| 预测期限 T | 21 天 |
| 初始训练集 | 800 天 |
| OOS 窗口 | 63 天 |
| Step | 21 天 |
| 特征数 | 148 |
| 模型 | RandomForest (n_estimators=100, max_depth=6) |

## 三、Label 策略

| 策略 | 描述 | 语义 |
|------|------|------|
| simple | Label = 1 if future_return > 0 | 预测未来是否上涨 |
| excess | Label = 1 if future_return > rolling_mean | 预测是否跑赢平均 |
| dip_recovery | Label = 1 if (dip > 5%) and (recovery > 3%) | 跌后是否能反弹 |

## 四、结果

| Label | IC | p-value | t-stat | Sharpe (无MA) |
|-------|-----|---------|--------|----------------|
| simple | 0.2417 | 0.001451 | **4.97** | 0.17 |
| excess | 0.3937 | 0.000000 | **4.32** | 0.11 |
| dip_recovery | 0.3406 | 0.000005 | **3.19** | -0.08 |

## 五、分析

### 5.1 IC 显著性

**✓ 全部通过 IC t-stat > 1.5 标准**

所有三种 Label 都有显著的预测能力：
- simple: t-stat = 4.97
- excess: t-stat = 4.32
- dip_recovery: t-stat = 3.19

### 5.2 Sharpe 分析

**✗ 无 Label 达到 Sharpe > 0.3**

可能原因：
1. 信号方向问题：新 Label 预测"涨"，但交易是"买"
2. 没有后置 MA 过滤
3. BTC 长期牛市导致类别不平衡

### 5.3 关键发现

1. **IC 很好** - 所有 Label 都有显著预测能力
2. **Sharpe 很低** - 需要进一步分析信号方向
3. **最佳 Label** - simple (t-stat 4.97)

## 六、结论

### 通过项
- [x] IC t-stat > 1.5

### 未通过项
- [ ] Sharpe > 0.3 (无 MA)

### 下一步
1. 尝试信号反转看 Sharpe 是否提升
2. 继续 R2: MA 特征融合实验
3. 或只比较 IC，忽略 Sharpe

---

*报告生成: 2026-02-20*
