# FcstLabPro 标准化操作手册

本文档定义 FcstLabPro 模型的标准化训练、实验与部署流程。

---

## 一、实验设计原则

### 1.1 实验类型

| 类型 | 目标 | 方法 |
|------|------|------|
| 消融实验 | 验证特征/组件贡献 | 逐个添加/移除，对比基线 |
| 超参数搜索 | 优化模型配置 | 网格搜索/贝叶斯优化 |
| 对比实验 | 评估不同方案 | 控制变量，多组并行 |

### 1.2 实验流程

```
目标定义 → 配置创建 → 执行 → 分析 → 记录
```

1. **目标定义**: 明确要验证的假设
2. **配置创建**: 在 `configs/experiments/` 下创建 YAML
3. **执行**: 运行训练脚本
4. **分析**: 检查 metrics.json、feature_importance.csv
5. **记录**: 更新 registry.json

### 1.3 配置规范

- 命名: `{type}_{model}_{version}_{feature}.yaml`
- 目录: `experiments/weekly/{exp_name}/`
- 必含文件: config.yaml, metrics.json, model.joblib, feature_cols.joblib

---

## 二、模型训练

### 2.1 训练环境

- Python 3.10 环境 (`venv_py310`)
- 确认数据文件存在: `data/binance_btc_usdt_daily.csv`

### 2.2 训练命令

```bash
cd /Users/qiubling/Desktop/projects/FcstLabPro
source venv_py310/bin/activate

# 执行训练
python scripts/train_orion_final.py  # 或对应脚本
```

### 2.3 验证项

- [ ] 特征列数量与配置一致
- [ ] 模型可正常加载
- [ ] 预测输出格式正确
- [ ] 标签分布合理

```bash
# 验证特征数量
python -c "import joblib; f=joblib.load('experiments/weekly/{exp_name}/feature_cols.joblib'); print(len(f))"
```

---

## 三、实验经验

### 3.1 有效策略

- **分治**: Bull/Bear 模型分别优化
- **窗口**: 不同模型适用不同预测窗口 T
- **特征**: 外部数据单独使用优于组合
- **模型容量**: n_estimators 需要与特征数量匹配（148特征建议 n_estimators >= 50）
- **特征剪枝**: 特征过多时(>100)建议剪枝到 30-50 个

### 3.2 常见陷阱

- 一次性引入过多外部数据 → 过拟合
- 不同模型共用同一套超参数 → 次优结果
- 标签与特征高度共线 → Kappa 为负
- **n_estimators 太小** → 模型容量不足，Fold 出现大量 Kappa=0
- **特征过多** → 欠拟合，预测能力弱
- **PnL 回测结果与报告不符** → 检查数据版本和脚本逻辑

### 3.3 超参数参考

| 参数 | 范围 | 说明 |
|------|------|------|
| n_estimators | 50-200 | Orion-BiX 建议 50-200，与特征数量相关 |
| max_depth | 3-8 | 控制复杂度 |
| learning_rate | 0.01-0.1 | 越小需要更多树 |
| num_leaves | 8-64 | GBDT 专用 |
| reg_alpha/lambda | 0.1-1.0 | 正则化 |

### 3.4 实验命名规范

- 基准实验: `weekly_bull_v27_orion_0218` (原版)
- 改进实验001: `weekly_bull_v27_orion_001` (增加模型容量)
- 改进实验002: `weekly_bull_v27_orion_002` (特征剪枝)

### 3.5 报告生成

```bash
# 生成实验报告 (包含 PnL 回测)
python scripts/generate_experiment_report.py --dir experiments/weekly/{exp_name}
```

必含文件:
- config.yaml - 配置文件
- fold_metrics.csv - 每个 fold 的指标
- predictions.csv - 预测结果
- metrics.json - 汇总指标
- report.md - 实验报告 (自动生成)

---

## 四、文档与同步

### 4.1 训练后检查

- [ ] 模型文件生成 (model.joblib)
- [ ] 标准化器生成 (scaler.joblib)
- [ ] 特征列保存 (feature_cols.joblib)
- [ ] 配置保存 (config.yaml)

### 4.2 部署同步

需更新的文件:
- `scripts/docker_entrypoint.sh` - 模型路径
- `deploy/deploy_v*.sh` - 版本信息
- `deploy/*_deployment_report.md` - 训练指标

---

## 五、部署流程

### 5.1 本地验证

```bash
# PnL 回测
python scripts/pnl_backtest.py --bull-dir {bull_dir} --bear-dir {bear_dir}

# 信号生成
python scripts/weekly_signal.py --download --save
```

验证指标:
- Kappa ≥ 0.10
- 年化收益 > 0
- 卡玛比率 > 1.0
- 最大回撤 < 25%

### 5.2 Docker 测试

```bash
docker build -t fcstlabpro-test .
docker run fcstlabpro-test
```

### 5.3 部署执行

```bash
./deploy/deploy_v*.sh
```

验证项:
- 镜像构建成功
- 镜像推送成功
- Cloud Run Job 部署成功
- Scheduler 创建成功

### 5.4 部署后验证

```bash
gcloud run jobs execute {job_name} --region asia-east1
gcloud logging read 'resource.type="cloud_run_job"' --limit=20
```

---

## 六、关键配置速查

### 模型配置

| 模型 | 配置文件 | T 窗口 |
|------|----------|--------|
| Bull | exp_weekly_bull_*.yaml | 21 |
| Bear | exp_weekly_bear_*.yaml | 28 |

### 部署配置

| 项目 | 值 |
|------|-----|
| 区域 | asia-east1 |
| 定时 | UTC 00:00 (北京时间 08:00) |

---

## 七、问题排查

### 特征数量不匹配

**症状**: `IndexError: shapes not aligned`

**原因**: 特征列获取在添加标签之后

**解决**: 先获取特征列，再添加标签

### 模块未找到

**症状**: `ModuleNotFoundError`

**解决**: 确认使用正确的 Python 环境 (venv_py310)

### Kappa 为负

**解决**:
- 检查标签是否颠倒
- 检查特征与目标是否共线

### 消融实验不稳定

**解决**:
- 增加 Walk-Forward 窗口
- 检查数据泄露

### 部署结果不一致

**解决**:
- 确认数据源一致
- 验证外部数据同步

### Cloud Run 超时

**解决**: 增加 `--task-timeout` 参数

### PnL 回测结果与报告不符

**症状**: 报告中年化收益 +26.63%，实际运行 -50%

**原因**:
1. 数据在报告生成后被更新
2. 脚本有 bug (signal_delay=0 时逻辑错误)
3. predictions.csv 被错误地重新生成

**解决**:
- 使用 `scripts/train_orion_walkforward.py` 重新训练
- 使用 `scripts/generate_experiment_report.py` 生成报告

---

## 八、检查清单

- [ ] 实验目标明确
- [ ] 配置命名规范
- [ ] 消融实验逐个验证
- [ ] 训练后特征数量正确
- [ ] PnL 回测指标达标
- [ ] Docker 测试通过
- [ ] 部署配置同步更新
- [ ] 部署后验证成功
- [ ] 记录实验结果

---

*本文档最后更新: 2026-02-18*
