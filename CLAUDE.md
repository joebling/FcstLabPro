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

### 5.2 模型晋升流程 (Promotion)

实验模型 **不能直接用于部署**。必须通过 `promote_model.py` 晋升到 `models/production/`：

```bash
# 1. 晋升 (自动执行 5.1 自检)
python scripts/promote_model.py \
    --experiment experiments/weekly/{exp_name} \
    --name {production_name} \
    --variant conservative

# 2. 提交到 git (models/production/ 是 git-tracked 的)
git add models/production/{production_name}/
git commit -m "promote: {production_name} from {exp_name}"

# 3. 部署
./deploy/deploy_v0305.sh
```

**晋升产物** (`models/production/{name}/`):

| 文件 | 说明 |
|------|------|
| `model.joblib` | 生产模型 |
| `config.yaml` | 训练配置 (含特征集、标签定义) |
| `manifest.json` | 模型谱系 (来源实验、git commit、哈希、指标、检查清单) |
| `meta.json` | 实验元数据 |
| `metrics.json` | 分类指标 |
| `pnl_metrics.json` | PnL 回测指标 |

**关键约束**:
- 部署脚本 (`deploy_v0305.sh`) 检查 `models/production/` 是否存在，不存在则拒绝部署
- `live_signal.py` 默认从 `models/production/{name}/` 加载模型
- `.gcloudignore` 确保 `models/production/` 进入 Docker 镜像
- 回滚 = `git revert` 晋升 commit

### 5.3 信号生成

```bash
# 信号生成时必须带上 --download 确保使用最新 Layer 0 数据
python scripts/weekly_signal.py --download --save

```

---

## 六、 本地 vs GPU 训练

### 6.1 训练环境选择

| 模型类型 | 训练环境 | 说明 |
|----------|----------|------|
| **LightGBM** | 本地 CPU | 快速训练，几分钟内完成 |
| **Orion-BiX** | GPU (vast.ai) | 需要 GPU 显存 8GB+，约 10 分钟 |
| **其他深度学习** | GPU (vast.ai) | 如 LSTM, Transformer 等 |

### 6.2 实验命名规范

**格式**: `{animal}_{direction}_{version}_{experiment_type}[_{variant}]`

**示例**:
- `weekly_bull_v0302_dip_recovery` (基础版)
- `weekly_bull_v0302_dip_recovery_v1` (变体v1)
- `weekly_bear_v0302_prod` (生产版)
- `weekly_bear_v13_prod` (v13生产版)

**重要**: 使用 `--overwrite` 参数生成简洁的目录名，避免时间戳。

```bash
# ✅ 正确
python scripts/run_experiment.py --config configs/experiments/weekly/{config}.yaml --overwrite

# ❌ 错误：带时间戳
python scripts/run_experiment.py --config configs/experiments/weekly/{config}.yaml
```

### 6.3 训练命令

**本地 (LightGBM)**:
```bash
python scripts/run_experiment.py --config configs/experiments/weekly/{config}.yaml --overwrite
```

**GPU (vast.ai)**:
```bash
# 1. 先提交代码到 GitHub
git add . && git commit -m "feat: 添加实验配置"
git push origin main

# 2. 在 vast.ai 上拉取代码并训练
nohup python scripts/run_experiment.py --config configs/experiments/weekly/{config}.yaml > experiments/weekly/{exp_name}/train.log 2>&1 &
```

### 6.4 实验提交规范

**每个实验完成后提交一次**（保持commit历史清晰）:

```bash
# 方式1: 每个实验单独提交
git add experiments/weekly/{exp_name}/
git commit -m "feat: 实验 {exp_name} 完成，Kappa=0.xx"

# 方式2: 多个相关实验一起提交
git add experiments/weekly/label_comparison_*/
git commit -m "feat: 完成标签策略对比实验"
```

**提交时机**:
- ✅ 实验有实质性进展/明确结论
- ✅ 文档/报告更新
- ❌ 快速迭代调参中（暂不提交）
- ❌ 结果不理想需要重做时

---

## 七、 GPU 远程训练 (vast.ai)

### 7.1 运行命令模式

在 vast.ai 等 GPU 服务器上运行实验的标准命令:

```bash
# 1. 创建实验目录
mkdir -p experiments/weekly/{exp_name}

# 2. 后台运行并保存日志
nohup python scripts/run_experiment.py --config configs/experiments/weekly/{config_name}.yaml > experiments/weekly/{exp_name}/train.log 2>&1 &

# 3. 查看日志
tail -f experiments/weekly/{exp_name}/train.log
```

### 7.2 实验完成后的操作

1. 检查 `meta.json` 中的 `status` 字段确认是否成功
2. 查看 `metrics.json` 获取汇总指标
3. 查看 `fold_metrics.csv` 分析各 fold 表现

---

## 七、 维护记录

* **2026-02-18**: 初始版本。
* **2026-02-19**: 引入 Institutional Framework，修正 IC 分析逻辑，增加 Layer 0-5 架构约束。
* **2026-02-27**: 添加 vast.ai GPU 远程训练命令规范。

---

*本文档由 FcstLabPro 核心架构组维护*