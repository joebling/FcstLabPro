# FcstLabPro 邮件未发送 + 模型信息 N/A 问题诊断报告

**日期**: 2026-02-15  
**问题**: 早上8点未收到邮件，昨晚测试邮件中模型元信息显示 N/A

---

## 🔍 问题诊断

### 问题 1: 早上 8 点未收到邮件

#### 根本原因
通过分析 [`deploy/gcloud_deploy.sh`](deploy/gcloud_deploy.sh:186) 和 [`job.yaml`](job.yaml:1)，发现了**关键配置不一致**：

1. **部署脚本中的 Job 名称**: `daily-btc-signal-v6` (第 25 行)
2. **实际运行的 Job 名称**: `daily-btc-signal-a6a8` (job.yaml 第 15 行)
3. **Cloud Scheduler 配置**: 调度器触发的是 `daily-btc-signal-v6`，但实际运行的 Job 是 `daily-btc-signal-a6a8`

**结论**: Cloud Scheduler 每天 08:00 触发的 Job 名称与实际部署的 Job 不匹配，导致调度失败。

#### 证据链
- [`gcloud_deploy.sh:25`](deploy/gcloud_deploy.sh:25): `JOB_NAME="daily-btc-signal-v6"`
- [`gcloud_deploy.sh:178`](deploy/gcloud_deploy.sh:178): Scheduler 触发 URI 使用 `${JOB_NAME}`
- [`job.yaml:15`](job.yaml:15): 实际 Job 名称为 `daily-btc-signal-a6a8`

### 问题 2: 模型元信息显示 N/A

#### 根本原因
通过分析 [`job.yaml`](job.yaml:38-40) 和模型目录，发现：

1. **当前使用的模型**:
   - Bull: `weekly_bull_ablation_triple_barrier_20260214_001719_ee6ac2`
   - Bear: `ablation_bear_A8_v4style_T14_20260214_002053_92a350`

2. **元信息缺失字段**:
   - Bull 模型 [`meta.json`](experiments/weekly/weekly_bull_ablation_triple_barrier_20260214_001719_ee6ac2/meta.json:1) 缺少:
     - `version` 字段
     - `label_strategy` 字段
     - `feature_set` 字段
   - Bear 模型 [`meta.json`](experiments/weekly/ablation_bear_A8_v4style_T14_20260214_002053_92a350/meta.json:1) 缺少相同字段

3. **代码期望字段**:
   - [`weekly_signal.py:209-221`](scripts/weekly_signal.py:209): 期望 `version`, `kappa`, `label_strategy`, `feature_set`
   - [`send_signal_email.py:69-72`](scripts/send_signal_email.py:69): 期望相同字段

**结论**: 消融实验（ablation）模型的 `meta.json` 缺少必要的元信息字段，导致邮件模板中显示 N/A。

#### 对比分析
- ✅ **v8b 模型** (默认模型) 包含完整元信息:
  - [`weekly_bull_v8b meta.json`](experiments/weekly/weekly_bull_v8b_20260213_235350_e97aaf/meta.json:3): 有 `version` 字段
  - 有 `aggregate_metrics.cohen_kappa` 字段
  
- ❌ **ablation 模型** (当前使用) 缺少关键字段:
  - 无 `version` 字段
  - 无 `label_strategy` 字段  
  - 无 `feature_set` 字段

---

## 🎯 修复方案

### 方案 1: 修复 Cloud Run Job 名称不一致

**选项 A: 更新 Scheduler 指向正确的 Job** (推荐)
- 修改 Cloud Scheduler 触发的 Job 名称为 `daily-btc-signal-a6a8`
- 优点: 不影响现有运行的 Job
- 缺点: 需要手动执行 gcloud 命令

**选项 B: 重新部署 Job 使用正确名称**
- 删除 `daily-btc-signal-a6a8`，重新部署为 `daily-btc-signal-v6`
- 优点: 名称统一，符合部署脚本
- 缺点: 需要重新部署

### 方案 2: 修复模型元信息缺失

**选项 A: 增强 `weekly_signal.py` 的容错逻辑** (推荐)
- 从 `config.yaml` 中提取缺失的元信息
- 为缺失字段提供合理的默认值
- 优点: 兼容所有模型（包括旧模型和消融实验）
- 缺点: 需要修改代码

**选项 B: 切换回 v8b 模型**
- 使用默认的 v8b 模型（包含完整元信息）
- 优点: 无需修改代码
- 缺点: 放弃当前消融实验模型

**选项 C: 手动补充 meta.json**
- 为消融实验模型手动添加缺失字段
- 优点: 保留当前模型
- 缺点: 治标不治本，未来新模型可能仍有问题

---

## 📋 推荐修复步骤

### 步骤 1: 修复 Cloud Scheduler (立即生效)

```bash
# 方案 A: 更新 Scheduler 指向正确的 Job
gcloud scheduler jobs update http daily-btc-signal-trigger \
    --location=asia-east1 \
    --uri="https://asia-east1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/955286039748/jobs/daily-btc-signal-a6a8:run"

# 或方案 B: 删除旧 Job，重新部署
gcloud run jobs delete daily-btc-signal-a6a8 --region=asia-east1 --quiet
./deploy/gcloud_deploy.sh
```

### 步骤 2: 增强 `weekly_signal.py` 容错逻辑

修改 [`scripts/weekly_signal.py`](scripts/weekly_signal.py:51) 的 `load_model_and_features()` 函数：

```python
def load_model_and_features(exp_dir: str):
    """加载模型、特征配置和元信息（增强容错）."""
    import yaml, json
    exp_path = PROJECT_ROOT / exp_dir
    model = joblib.load(exp_path / "model.joblib")
    
    with open(exp_path / "config.yaml") as f:
        config = yaml.safe_load(f)
    
    # 加载 meta.json
    meta = {}
    for meta_file in ["metrics.json", "meta.json"]:
        meta_path = exp_path / meta_file
        if meta_path.exists():
            with open(meta_path) as mf:
                meta = json.load(mf)
            break
    
    # 🔧 增强：从 config 补充缺失字段
    if "version" not in meta:
        meta["version"] = config.get("experiment", {}).get("name", "unknown")
    
    if "label_strategy" not in meta:
        meta["label_strategy"] = config.get("label", {}).get("strategy", "unknown")
    
    if "feature_set" not in meta:
        meta["feature_set"] = config.get("features", {}).get("sets", [])
    
    if "kappa" not in meta:
        kappa = None
        if "aggregate_metrics" in meta and "cohen_kappa" in meta["aggregate_metrics"]:
            kappa = meta["aggregate_metrics"]["cohen_kappa"]
        meta["kappa"] = kappa if kappa is not None else "N/A"
    
    return model, config, meta
```

### 步骤 3: 更新部署脚本环境变量

修改 [`deploy/gcloud_deploy.sh`](deploy/gcloud_deploy.sh:125) 的环境变量配置：

```bash
# 选项 1: 使用 v8b 模型（推荐，元信息完整）
ENV_VARS="BULL_DIR=experiments/weekly/weekly_bull_v8b_20260213_235350_e97aaf"
ENV_VARS="${ENV_VARS},BEAR_DIR=experiments/weekly/weekly_bear_v8b_20260214_000003_545cf4"

# 选项 2: 继续使用消融实验模型（需先修复 weekly_signal.py）
ENV_VARS="BULL_DIR=experiments/weekly/weekly_bull_ablation_triple_barrier_20260214_001719_ee6ac2"
ENV_VARS="${ENV_VARS},BEAR_DIR=experiments/weekly/ablation_bear_A8_v4style_T14_20260214_002053_92a350"
```

### 步骤 4: 添加 SMTP 环境变量到部署脚本

修改 [`deploy/gcloud_deploy.sh`](deploy/gcloud_deploy.sh:125)，添加邮件配置：

```bash
# 在 ENV_VARS 中添加 SMTP 配置
ENV_VARS="${ENV_VARS},SMTP_USER=${SMTP_USER:-}"
ENV_VARS="${ENV_VARS},SMTP_PASS=${SMTP_PASS:-}"
ENV_VARS="${ENV_VARS},MAIL_TO=${MAIL_TO:-}"
```

### 步骤 5: 验证修复

```bash
# 1. 手动触发 Job 测试
gcloud run jobs execute daily-btc-signal-a6a8 --region=asia-east1 --wait

# 2. 查看日志
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="daily-btc-signal-a6a8"' --limit=50

# 3. 检查邮件是否收到

# 4. 验证 Scheduler 配置
gcloud scheduler jobs describe daily-btc-signal-trigger --location=asia-east1
```

---

## 🔄 长期优化建议

1. **统一模型元信息规范**
   - 在 [`src/experiment/runner.py`](src/experiment/runner.py:1) 中确保所有实验都生成完整的 `meta.json`
   - 添加必需字段: `version`, `label_strategy`, `feature_set`, `kappa`

2. **增强部署脚本健壮性**
   - 添加 Job 名称一致性检查
   - 添加环境变量验证（SMTP 配置）
   - 添加模型目录存在性检查

3. **添加监控告警**
   - Cloud Scheduler 执行失败告警
   - Job 执行失败告警
   - 邮件发送失败告警

4. **文档更新**
   - 更新 [`deploy/DEPLOY_GUIDE.md`](deploy/DEPLOY_GUIDE.md:1) 添加故障排查章节
   - 添加模型切换操作指南

---

## 📊 影响分析

### 当前状态
- ❌ Cloud Scheduler 无法触发 Job（名称不匹配）
- ❌ 邮件内容显示 N/A（元信息缺失）
- ✅ 手动执行 Job 可以正常运行
- ✅ 邮件发送功能正常（昨晚测试邮件已收到）

### 修复后状态
- ✅ Cloud Scheduler 每天 08:00 自动触发
- ✅ 邮件内容显示完整模型信息
- ✅ 兼容所有模型（包括消融实验）
- ✅ 部署流程标准化

---

## 🚀 快速修复命令（立即执行）

```bash
# 1. 修复 Scheduler（选择其中一个）
# 方案 A: 更新 Scheduler URI
gcloud scheduler jobs update http daily-btc-signal-trigger \
    --location=asia-east1 \
    --uri="https://asia-east1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/955286039748/jobs/daily-btc-signal-a6a8:run"

# 方案 B: 重新部署（需先修改代码）
# 1) 修改 weekly_signal.py（见步骤 2）
# 2) 重新部署
./deploy/gcloud_deploy.sh

# 2. 手动测试
gcloud run jobs execute daily-btc-signal-a6a8 --region=asia-east1 --wait
```
