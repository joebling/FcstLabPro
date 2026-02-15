# 代码修改清单

## 📝 需要修改的文件

### 1. `scripts/weekly_signal.py`

**修改位置**: 第 51-74 行，`load_model_and_features()` 函数

**修改前**:
```python
def load_model_and_features(exp_dir: str):
    """加载模型、特征配置和元信息."""
    import yaml, json
    exp_path = PROJECT_ROOT / exp_dir
    model = joblib.load(exp_path / "model.joblib")
    with open(exp_path / "config.yaml") as f:
        config = yaml.safe_load(f)
    meta = {}
    for meta_file in ["metrics.json", "meta.json"]:
        meta_path = exp_path / meta_file
        if meta_path.exists():
            with open(meta_path) as mf:
                meta = json.load(mf)
            break
    # 修复：自动补充 kappa 字段
    if "kappa" not in meta:
        kappa = None
        if "aggregate_metrics" in meta and "cohen_kappa" in meta["aggregate_metrics"]:
            kappa = meta["aggregate_metrics"]["cohen_kappa"]
        if kappa is not None:
            meta["kappa"] = kappa
    # 调试输出 meta 内容
    logger.info(f"[DEBUG] loaded meta for {exp_dir}: {meta}")
    return model, config, meta
```

**修改后**:
```python
def load_model_and_features(exp_dir: str):
    """加载模型、特征配置和元信息（增强容错）."""
    import yaml, json
    exp_path = PROJECT_ROOT / exp_dir
    model = joblib.load(exp_path / "model.joblib")
    
    with open(exp_path / "config.yaml") as f:
        config = yaml.safe_load(f)
    
    # 加载 meta.json 或 metrics.json
    meta = {}
    for meta_file in ["metrics.json", "meta.json"]:
        meta_path = exp_path / meta_file
        if meta_path.exists():
            with open(meta_path) as mf:
                meta = json.load(mf)
            break
    
    # 🔧 增强：从 config 补充缺失字段
    exp_config = config.get("experiment", {})
    
    # 补充 version
    if "version" not in meta:
        meta["version"] = exp_config.get("name", meta.get("name", "unknown"))
    
    # 补充 label_strategy
    if "label_strategy" not in meta:
        label_cfg = config.get("label", {})
        meta["label_strategy"] = label_cfg.get("strategy", "unknown")
    
    # 补充 feature_set
    if "feature_set" not in meta:
        feat_cfg = config.get("features", {})
        meta["feature_set"] = feat_cfg.get("sets", [])
    
    # 补充 kappa
    if "kappa" not in meta:
        kappa = None
        if "aggregate_metrics" in meta and "cohen_kappa" in meta["aggregate_metrics"]:
            kappa = meta["aggregate_metrics"]["cohen_kappa"]
            # 格式化为 2 位小数
            if kappa is not None:
                kappa = f"{kappa:.2f}"
        meta["kappa"] = kappa if kappa is not None else "N/A"
    
    logger.info(f"[DEBUG] loaded meta for {exp_dir}: version={meta.get('version')}, kappa={meta.get('kappa')}, label_strategy={meta.get('label_strategy')}")
    
    return model, config, meta
```

---

### 2. `deploy/gcloud_deploy.sh`

#### 修改 2.1: 添加 SMTP 配置变量

**修改位置**: 第 18 行后（在配置变量区域）

**添加内容**:
```bash
# SMTP 邮件配置（从环境变量读取）
SMTP_USER="${SMTP_USER:-}"
SMTP_PASS="${SMTP_PASS:-}"
MAIL_TO="${MAIL_TO:-}"
```

#### 修改 2.2: 添加部署前检查

**修改位置**: 第 117 行后（在 Step 3 和 Step 4 之间）

**添加内容**:
```bash
# ─────────────────────────────────────────────────────────────
# Step 3.5: 部署前检查
# ─────────────────────────────────────────────────────────────
echo ""
echo "=== Step 3.5: 部署前检查 ==="

# 检查 SMTP 配置
if [ -z "${SMTP_USER}" ] || [ -z "${SMTP_PASS}" ] || [ -z "${MAIL_TO}" ]; then
    echo "⚠️  警告: SMTP 配置不完整，邮件发送功能将被禁用"
    echo "   请设置环境变量: SMTP_USER, SMTP_PASS, MAIL_TO"
    read -p "   是否继续部署? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ 部署已取消"
        exit 1
    fi
else
    echo "✅ SMTP 配置已设置"
fi

# 检查模型目录是否存在
BULL_DIR_CHECK="${BULL_DIR:-experiments/weekly/weekly_bull_v8b_20260213_235350_e97aaf}"
BEAR_DIR_CHECK="${BEAR_DIR:-experiments/weekly/weekly_bear_v8b_20260214_000003_545cf4}"

if [ ! -d "${BULL_DIR_CHECK}" ]; then
    echo "❌ Bull 模型目录不存在: ${BULL_DIR_CHECK}"
    exit 1
fi
if [ ! -d "${BEAR_DIR_CHECK}" ]; then
    echo "❌ Bear 模型目录不存在: ${BEAR_DIR_CHECK}"
    exit 1
fi
echo "✅ 模型目录检查通过"
```

#### 修改 2.3: 更新环境变量构建逻辑

**修改位置**: 第 125-133 行

**修改前**:
```bash
# 构建环境变量
ENV_VARS="BULL_DIR=experiments/weekly/weekly_bull_v6_20260213_214847_a29943"
ENV_VARS="${ENV_VARS},BEAR_DIR=experiments/weekly/weekly_bear_v6_20260213_215211_1928bd"
ENV_VARS="${ENV_VARS},OUT_DIR=/tmp/signals"
if [ -n "${OUT_BUCKET}" ]; then
    ENV_VARS="${ENV_VARS},OUT_BUCKET=${OUT_BUCKET}"
fi
if [ -n "${NOTIFICATION_URL}" ]; then
    ENV_VARS="${ENV_VARS},NOTIFICATION_URL=${NOTIFICATION_URL}"
fi
```

**修改后**:
```bash
# 构建环境变量
ENV_VARS="BULL_DIR=${BULL_DIR:-experiments/weekly/weekly_bull_v8b_20260213_235350_e97aaf}"
ENV_VARS="${ENV_VARS},BEAR_DIR=${BEAR_DIR:-experiments/weekly/weekly_bear_v8b_20260214_000003_545cf4}"
ENV_VARS="${ENV_VARS},OUT_DIR=/tmp/signals"

# 添加 SMTP 配置
if [ -n "${SMTP_USER}" ]; then
    ENV_VARS="${ENV_VARS},SMTP_USER=${SMTP_USER}"
fi
if [ -n "${SMTP_PASS}" ]; then
    ENV_VARS="${ENV_VARS},SMTP_PASS=${SMTP_PASS}"
fi
if [ -n "${MAIL_TO}" ]; then
    ENV_VARS="${ENV_VARS},MAIL_TO=${MAIL_TO}"
fi

# 可选配置
if [ -n "${OUT_BUCKET}" ]; then
    ENV_VARS="${ENV_VARS},OUT_BUCKET=${OUT_BUCKET}"
fi
if [ -n "${NOTIFICATION_URL}" ]; then
    ENV_VARS="${ENV_VARS},NOTIFICATION_URL=${NOTIFICATION_URL}"
fi
```

---

## 🚀 部署命令汇总

### 准备阶段

```bash
# 1. 进入项目目录
cd /Users/qiubling/Desktop/projects/FcstLabPro

# 2. 设置环境变量
export GCP_PROJECT_ID="forecastlab-prod"
export SMTP_USER="792680027@qq.com"
export SMTP_PASS="mlefgnksjkafbfei"
export MAIL_TO="792680027@qq.com"

# 3. 可选：指定模型目录（默认使用 v8b）
# export BULL_DIR="experiments/weekly/weekly_bull_ablation_triple_barrier_20260214_001719_ee6ac2"
# export BEAR_DIR="experiments/weekly/ablation_bear_A8_v4style_T14_20260214_002053_92a350"
```

### 删除旧 Job

```bash
# 删除旧 Job
gcloud run jobs delete daily-btc-signal-a6a8 \
    --region=asia-east1 \
    --quiet

# 确认删除
gcloud run jobs list --region=asia-east1 | grep daily-btc-signal
```

### 暂停 Scheduler（可选）

```bash
# 暂停 Scheduler（避免部署期间触发）
gcloud scheduler jobs pause daily-btc-signal-trigger \
    --location=asia-east1
```

### 执行部署

```bash
# 执行部署脚本
./deploy/gcloud_deploy.sh
```

### 验证部署

```bash
# 1. 查看 Job 配置
gcloud run jobs describe daily-btc-signal-v6 \
    --region=asia-east1 \
    --format=yaml > /tmp/job_config.yaml

# 2. 检查环境变量
grep -A 20 "env:" /tmp/job_config.yaml

# 3. 查看 Scheduler 配置
gcloud scheduler jobs describe daily-btc-signal-trigger \
    --location=asia-east1

# 4. 恢复 Scheduler
gcloud scheduler jobs resume daily-btc-signal-trigger \
    --location=asia-east1
```

### 测试执行

```bash
# 1. 手动触发 Job
gcloud run jobs execute daily-btc-signal-v6 \
    --region=asia-east1 \
    --wait

# 2. 查看执行日志
gcloud logging read \
    'resource.type="cloud_run_job" AND resource.labels.job_name="daily-btc-signal-v6"' \
    --limit=50

# 3. 查看执行历史
gcloud run jobs executions list \
    --job=daily-btc-signal-v6 \
    --region=asia-east1 \
    --limit=5
```

### 测试 Scheduler 触发

```bash
# 手动触发 Scheduler
gcloud scheduler jobs run daily-btc-signal-trigger \
    --location=asia-east1

# 等待 1-2 分钟后查看执行记录
gcloud run jobs executions list \
    --job=daily-btc-signal-v6 \
    --region=asia-east1 \
    --limit=5
```

---

## 📋 验收检查清单

### 部署前检查
- [ ] 代码修改已完成（`weekly_signal.py`）
- [ ] 部署脚本已更新（`gcloud_deploy.sh`）
- [ ] 环境变量已设置（SMTP_USER, SMTP_PASS, MAIL_TO）
- [ ] 模型目录存在且包含 `model.joblib`

### 部署后验证
- [ ] Job 名称为 `daily-btc-signal-v6`
- [ ] Scheduler 触发 URI 指向 `daily-btc-signal-v6`
- [ ] 环境变量包含 SMTP 配置
- [ ] 手动执行 Job 成功
- [ ] 收到邮件通知
- [ ] 邮件内容无 N/A（模型版本、Kappa、标签策略、特征集）
- [ ] Scheduler 状态为 ENABLED
- [ ] 调度时间为每天 08:00 (Asia/Shanghai)

---

## 🔄 快速回滚方案

如果部署失败：

```bash
# 1. 暂停新 Scheduler
gcloud scheduler jobs pause daily-btc-signal-trigger --location=asia-east1

# 2. 更新 Scheduler 指向旧 Job（如果旧 Job 还存在）
gcloud scheduler jobs update http daily-btc-signal-trigger \
    --location=asia-east1 \
    --uri="https://asia-east1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/955286039748/jobs/daily-btc-signal-a6a8:run"

# 3. 恢复 Scheduler
gcloud scheduler jobs resume daily-btc-signal-trigger --location=asia-east1
```

---

## 📞 故障排查命令

### 查看 Job 状态
```bash
gcloud run jobs describe daily-btc-signal-v6 --region=asia-east1
```

### 查看执行日志
```bash
gcloud logging read \
    'resource.type="cloud_run_job" AND resource.labels.job_name="daily-btc-signal-v6"' \
    --limit=100
```

### 查看错误日志
```bash
gcloud logging read \
    'resource.type="cloud_run_job" AND severity>=ERROR' \
    --limit=50
```

### 查看 Scheduler 执行历史
```bash
gcloud scheduler jobs executions list \
    --job=daily-btc-signal-trigger \
    --location=asia-east1
```
