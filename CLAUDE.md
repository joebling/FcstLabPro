# FcstLabPro 机构级研究与实验操作手册 (V2.0)

本文档基于 **Institutional Crypto Alpha Research Framework** 构建，定义 FcstLabPro 的标准化研发、统计验证与部署流程。

---

## 一、 研究架构设计 (Layered Architecture)

所有开发必须严格遵循分层原则，严禁跨层调用逻辑：

| 层级 | 定义 | 核心关注点 |
| --- | --- | --- |
| **Layer 0** | **数据层 (Integrity)** | 确保 `feature[t]` 仅使用 `<=t` 数据，消除未来函数。 |
| **Layer 1** | **标签层 (Labels)** | **强制非重叠 (Non-overlapping)** 收益计算。 |
| **Layer 2** | **信号层 (Raw Alpha)** | 纯粹的 `signal vs future_return` 研究，不含策略逻辑。 |
| **Layer 3** | **验证层 (Validation)** | **真正 Walk-Forward** 滚动训练与 IC 稳定性测试。 |
| **Layer 4** | **组合层 (Portfolio)** | 波动率目标 (Vol Targeting) 与信号平滑。 |
| **Layer 5** | **执行层 (Backtest)** | 考虑成本、滑点与延迟的真实回测。 |

---

## 二、 实验核心规范 (Hard Rules)

### 2.1 标签与采样 (Layer 1)

* **非重叠规则**：若预测窗口 ，实验样本必须每 21 天采样一次。
* **严禁行为**：严禁在研究阶段使用每日滑动的重叠标签进行统计。

### 2.2 滚动训练 (Layer 3)

* **标准模式**：必须使用 `Expanding` 或 `Rolling` Walk-Forward。
* **禁止行为**：严禁“一次训练，全段预测 (Train Once, Predict All)”的伪 OOS 测试。
* **锁定原则**：一旦进入 OOS 阶段，严禁调整超参数或根据结果反推信号方向。

### 2.3 统计准则 (Validation)

实验报告必须包含以下指标，且需达到机构级门槛：

| 指标 | 门槛 (Crypto 单资产) | 说明 |
| --- | --- | --- |
| **Rank IC** |  (有价值) | 超过  需启动代码审计 |
| **IC t-stat** |  (显著) | 基于 IC 时间序列计算，非样本量 |
| **Annualized Vol** | 目标  | 通过 Vol Targeting 实现 |
| **Sharpe (OOS)** |  | 成本后净收益比率 |

---

## 三、 实验执行流程

### 3.1 实验准备

1. **目标定义**: 明确验证的 Alpha 假设（如：Funding Rate 的领先性）。
2. **配置创建**: 在 `configs/experiments/` 下创建 YAML，需注明 `sampling_step`（需等于标签 ）。

### 3.2 运行训练与 IC 分析

```bash
# 1. 执行修正版 Walk-Forward 训练
python scripts/train_orion_walkforward.py --config configs/experiments/{exp_name}.yaml

# 2. 执行独立 IC 分析 (使用 ic_analysis_corrected.py)
python scripts/ic_analysis_corrected.py --bull-dir experiments/weekly/{exp_name}

```

### 3.3 结果判定

* 若 **Rank IC < 0.02**：判定为噪音，放弃该特征/模型。
* 若 **IC t-stat < 1.0**：信号不稳定，存在 Regime 依赖，需增加状态识别模块。
* 若 **Sharpe > 3.0**：极大概率存在数据泄露，需自查 Layer 0。

---

## 四、 实验经验与坑点清单

### 4.1 有效策略

* **Regime-Specific**: 分别优化 Bull/Bear 模型的  窗口（Bull 建议 21，Bear 建议 28）。
* **Vol Targeting**: 仓位与反向实现波动率挂钩，而非简单的 MA 过滤。
* **特征剪枝**: 特征过多(>100)会导致欠拟合，建议通过相关性分析保留前 30-50 个。

### 4.2 致命陷阱 (Pitfalls)

* **自欺欺人**: 反复调整  窗口直至 IC 变高（即 Over-fitting the process）。
* **信号延迟**: 忽视了  时刻收盘后，执行通常在  开盘，导致回测虚高。
* **模型容量**: `n_estimators` 过小导致 Fold 出现大量 Kappa=0，无法捕捉非线性关系。

---

## 五、 部署与同步流程

### 5.1 部署前强制自检

* [ ] **IC 验证**: `ic_analysis_corrected.py` 报告输出正常，t-stat > 1.5。
* [ ] **Non-overlapping**: 确认标签采样步长与预测窗口一致。
* [ ] **Docker 一致性**: 确认生产环境 Python 版本为 3.10。

### 5.2 信号生成

```bash
# 信号生成时必须带上 --download 确保使用最新 Layer 0 数据
python scripts/weekly_signal.py --download --save

```

---

## 六、 维护记录

* **2026-02-18**: 初始版本。
* **2026-02-19**: 引入 Institutional Framework，修正 IC 分析逻辑，增加 Layer 0-5 架构约束。

---

*本文档由 FcstLabPro 核心架构组维护*