#!/usr/bin/env bash
# =============================================================================
# FcstLabPro v9 — Google Cloud Run Job 部署脚本
# 每天北京时间 08:00 (UTC 00:00) 运行，预测未来 14 天 BTC 价格走势
#
# 前置条件:
#   1. 安装 gcloud CLI 并登录: gcloud auth login
#   2. 创建 GCP 项目并设为当前项目: gcloud config set project <PROJECT_ID>
#   3. 启用计费
#
# 用法:
#   chmod +x deploy/gcloud_deploy.sh
#   ./deploy/gcloud_deploy.sh
# =============================================================================
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# 加载本地 .env 文件（如果有）
# ─────────────────────────────────────────────────────────────
if [ -f "$(dirname "$0")/../.env" ]; then
    set -a
    source "$(dirname "$0")/../.env"
    set +a
fi

# ─────────────────────────────────────────────────────────────
# 配置变量（⬇️ 根据你的实际情况修改 ⬇️）
# ─────────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-forecastlab-prod}"
REGION="asia-east1"                          # 台湾区域，延迟低
REPO_NAME="fcstlabpro"                       # Artifact Registry 仓库名
IMAGE_NAME="fcstlabpro-v6"                   # 镜像名
IMAGE_TAG="latest"
JOB_NAME="daily-btc-signal-v9"              # Cloud Run Job 名
SCHEDULER_NAME="daily-btc-signal-trigger"   # Cloud Scheduler 名
MEMORY="2Gi"
CPU="1"

# 信号输出 GCS 桶（可选，留空则不上传）
OUT_BUCKET="${OUT_BUCKET:-}"
# 通知 Webhook（可选，如 Slack / 飞书 / Telegram Bot）
NOTIFICATION_URL="${NOTIFICATION_URL:-}"

# Service Account（留空则用默认 Compute SA）
SERVICE_ACCOUNT="${GCP_SERVICE_ACCOUNT:-}"

# SMTP 邮件配置（从环境变量读取）
SMTP_USER="${SMTP_USER:-}"
SMTP_PASS="${SMTP_PASS:-}"
MAIL_TO="${MAIL_TO:-}"

# Gemini API Key（LLM 策略分析，可选）
GEMINI_API_KEY="${GEMINI_API_KEY:-}"

# 完整镜像地址
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${IMAGE_TAG}"

# ─────────────────────────────────────────────────────────────
# Step 0: 前置检查
# ─────────────────────────────────────────────────────────────
echo ""
echo "=== Step 0: 前置检查 ==="
echo "  项目: ${PROJECT_ID}"
echo "  区域: ${REGION}"
echo "  镜像: ${IMAGE_URI}"
echo "  Job:  ${JOB_NAME}"
echo ""

# 检查 gcloud
command -v gcloud >/dev/null 2>&1 || { echo "❌ 请先安装 gcloud CLI"; exit 1; }

# 检查 Dockerfile
ls Dockerfile >/dev/null 2>&1 || { echo "❌ 请在项目根目录运行此脚本"; exit 1; }

# 设置项目
gcloud config set project "${PROJECT_ID}" --quiet

echo "✅ 前置检查通过"

# ─────────────────────────────────────────────────────────────
# Step 1: 启用 API
# ─────────────────────────────────────────────────────────────
echo ""
echo "=== Step 1: 启用 Google Cloud API ==="
gcloud services enable \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    run.googleapis.com \
    cloudscheduler.googleapis.com \
    --quiet

echo "✅ API 已启用"

# ─────────────────────────────────────────────────────────────
# Step 2: 创建 Artifact Registry 仓库
# ─────────────────────────────────────────────────────────────
echo ""
echo "=== Step 2: 创建 Artifact Registry 仓库 ==="
gcloud artifacts repositories describe "${REPO_NAME}" \
    --location="${REGION}" 2>/dev/null || \
gcloud artifacts repositories create "${REPO_NAME}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="FcstLabPro 镜像仓库"

echo "✅ 仓库就绪: ${REPO_NAME}"

# ─────────────────────────────────────────────────────────────
# Step 3: 构建并推送镜像
# ─────────────────────────────────────────────────────────────
echo ""
echo "=== Step 3: 构建并推送镜像 ==="
echo "  镜像: ${IMAGE_URI}"

# 创建 .gcloudignore 排除不需要的文件
cat > .gcloudignore <<'EOF'
.git
.gitignore
__pycache__
*.pyc
lab-venv/
.venv/
notebooks/
reports/
logs/
tests/
*.md
.DS_Store
EOF

gcloud builds submit --tag "${IMAGE_URI}" .

echo "✅ 镜像已推送"

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
BULL_DIR_CHECK="${BULL_DIR:-experiments/weekly/weekly_bull_v9_fgi_v2_20260215_113918_2181e7}"
BEAR_DIR_CHECK="${BEAR_DIR:-experiments/weekly/weekly_bear_v9_fgi_v2_20260215_114152_6c90ee}"

if [ ! -d "${BULL_DIR_CHECK}" ]; then
    echo "❌ Bull 模型目录不存在: ${BULL_DIR_CHECK}"
    exit 1
fi
if [ ! -d "${BEAR_DIR_CHECK}" ]; then
    echo "❌ Bear 模型目录不存在: ${BEAR_DIR_CHECK}"
    exit 1
fi
echo "✅ 模型目录检查通过"

# ─────────────────────────────────────────────────────────────
# Step 4: 创建/更新 Cloud Run Job
# ─────────────────────────────────────────────────────────────
echo ""
echo "=== Step 4: 创建/更新 Cloud Run Job ==="

# 构建环境变量
ENV_VARS="BULL_DIR=${BULL_DIR:-experiments/weekly/weekly_bull_v9_fgi_v2_20260215_113918_2181e7}"
ENV_VARS="${ENV_VARS},BEAR_DIR=${BEAR_DIR:-experiments/weekly/weekly_bear_v9_fgi_v2_20260215_114152_6c90ee}"
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

# 添加 Gemini API Key
if [ -n "${GEMINI_API_KEY}" ]; then
    ENV_VARS="${ENV_VARS},GEMINI_API_KEY=${GEMINI_API_KEY}"
fi

# 可选配置
if [ -n "${OUT_BUCKET}" ]; then
    ENV_VARS="${ENV_VARS},OUT_BUCKET=${OUT_BUCKET}"
fi
if [ -n "${NOTIFICATION_URL}" ]; then
    ENV_VARS="${ENV_VARS},NOTIFICATION_URL=${NOTIFICATION_URL}"
fi

JOB_CMD="gcloud run jobs"

if ${JOB_CMD} describe "${JOB_NAME}" --region="${REGION}" 2>/dev/null; then
    echo "  Job 已存在，更新..."
    ${JOB_CMD} update "${JOB_NAME}" \
        --image "${IMAGE_URI}" \
        --region "${REGION}" \
        --set-env-vars "${ENV_VARS}" \
        --memory "${MEMORY}" \
        --cpu "${CPU}" \
        --max-retries 2 \
        --task-timeout 600
else
    echo "  创建新 Job..."
    ${JOB_CMD} create "${JOB_NAME}" \
        --image "${IMAGE_URI}" \
        --region "${REGION}" \
        --set-env-vars "${ENV_VARS}" \
        --memory "${MEMORY}" \
        --cpu "${CPU}" \
        --max-retries 2 \
        --task-timeout 600
fi

echo "✅ Cloud Run Job 已就绪: ${JOB_NAME}"

# ─────────────────────────────────────────────────────────────
# Step 5: 手动执行一次（测试）
# ─────────────────────────────────────────────────────────────
echo ""
echo "=== Step 5: 手动执行一次（测试） ==="
gcloud run jobs execute "${JOB_NAME}" --region "${REGION}" --wait

echo "✅ 测试执行完成"

# ─────────────────────────────────────────────────────────────
# Step 6: 创建 Cloud Scheduler（每天 08:00 北京时间）
# ─────────────────────────────────────────────────────────────
echo ""
echo "=== Step 6: 创建 Cloud Scheduler ==="
echo "  调度: 每天 08:00 (Asia/Shanghai)"

# Cloud Scheduler 触发 Cloud Run Job 的 URI
TRIGGER_URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run"

# 获取 Service Account
if [ -z "${SERVICE_ACCOUNT}" ]; then
    PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')
    SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
fi

SCHEDULE_CRON="0 8 * * *"  # 北京时间 08:00 每天

if gcloud scheduler jobs describe "${SCHEDULER_NAME}" --location="${REGION}" 2>/dev/null; then
    echo "  Scheduler 已存在，更新..."
    gcloud scheduler jobs update http "${SCHEDULER_NAME}" \
        --schedule="${SCHEDULE_CRON}" \
        --time-zone="Asia/Shanghai" \
        --location="${REGION}" \
        --uri="${TRIGGER_URI}" \
        --http-method=POST \
        --oidc-service-account-email="${SERVICE_ACCOUNT}"
else
    echo "  创建新 Scheduler..."
    gcloud scheduler jobs create http "${SCHEDULER_NAME}" \
        --schedule="${SCHEDULE_CRON}" \
        --time-zone="Asia/Shanghai" \
        --location="${REGION}" \
        --uri="${TRIGGER_URI}" \
        --http-method=POST \
        --oidc-service-account-email="${SERVICE_ACCOUNT}"
fi

echo "✅ Cloud Scheduler 已创建"

# ─────────────────────────────────────────────────────────────
# 部署完成
# ─────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "🎉 FcstLabPro v6 部署完成！"
echo "============================================================"
echo ""
echo "📋 部署摘要:"
echo "  镜像:      ${IMAGE_URI}"
echo "  Job:       ${JOB_NAME} (${REGION})"
echo "  Scheduler: ${SCHEDULER_NAME}"
echo "  调度时间:  每天 08:00 (Asia/Shanghai)"
echo "  预测窗口:  未来 14 天 BTC 价格走势"
echo ""
echo "📊 数据源:"
echo "  唯一数据源: Binance BTCUSDT 日线 K线"
echo "  API 端点:   https://api.binance.com/api/v3/klines"
echo "  获取字段:   OHLCV + quote_volume + trades"
echo "  无需 API Key（公开接口）"
echo ""
echo "🔧 常用运维命令:"
echo ""
echo "  # 手动触发一次"
echo "  gcloud run jobs execute ${JOB_NAME} --region ${REGION}"
echo ""
echo "  # 查看执行记录"
echo "  gcloud run jobs executions list --job=${JOB_NAME} --region=${REGION}"
echo ""
echo "  # 查看日志"
echo "  gcloud logging read 'resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${JOB_NAME}\"' --limit=50"
echo ""
echo "  # 暂停/恢复调度"
echo "  gcloud scheduler jobs pause ${SCHEDULER_NAME} --location=${REGION}"
echo "  gcloud scheduler jobs resume ${SCHEDULER_NAME} --location=${REGION}"
echo ""
echo "  # 更新镜像后重新部署"
echo "  gcloud builds submit --tag ${IMAGE_URI} ."
echo "  gcloud run jobs update ${JOB_NAME} --image ${IMAGE_URI} --region ${REGION}"
echo ""
