#!/usr/bin/env bash
# =============================================================================
# FcstLabPro v7 — Google Cloud Run Job 部署脚本
# 每天北京时间 08:00 (UTC 00:00) 运行，预测未来 21/28 天 BTC 价格走势
#
# Bull 模型: Orion-BiX (T=21)
# Bear 模型: LightGBM (T=28)
#
# 前置条件:
#   1. 安装 gcloud CLI 并登录: gcloud auth login
#   2. 创建 GCP 项目并设为当前项目: gcloud config set project <PROJECT_ID>
#   3. 启用计费
#
# 用法:
#   chmod +x deploy/deploy_v7.sh
#   ./deploy/deploy_v7.sh
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
IMAGE_NAME="fcstlabpro-0215"                 # 镜像名 (v7)
IMAGE_TAG="latest"
JOB_NAME="daily-btc-signal-v7"              # Cloud Run Job 名
SCHEDULER_NAME="daily-btc-signal-v7-trigger"  # Cloud Scheduler 名
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
echo "=== FcstLabPro v7 部署脚本 ==="
echo "  Bull 模型: Orion-BiX (T=21)"
echo "  Bear 模型: LightGBM (T=28)"
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
# Step 1: 构建并推送镜像
# ─────────────────────────────────────────────────────────────
echo ""
echo "=== Step 1: 构建并推送镜像 ==="
echo "  镜像: ${IMAGE_URI}"
echo ""

# 启用必要的 API
echo "  启用 Artifact Registry API..."
gcloud services enable artifactregistry.googleapis.com --quiet 2>/dev/null || true
echo "  启用 Cloud Run API..."
gcloud services enable run.googleapis.com --quiet 2>/dev/null || true
echo "  启用 Cloud Scheduler API..."
gcloud services enable cloudscheduler.googleapis.com --quiet 2>/dev/null || true

# 创建 Artifact Registry 仓库（如果不存在）
echo "  检查 Artifact Registry 仓库..."
gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" 2>/dev/null || {
    echo "  创建 Artifact Registry 仓库..."
    gcloud artifacts repositories create "${REPO_NAME}" \
        --location="${REGION}" \
        --repository-format=docker \
        --quiet
}

# 构建并推送镜像
echo "  构建 Docker 镜像..."
gcloud builds submit \
    --tag "${IMAGE_URI}" \
    --project="${PROJECT_ID}" \
    --gcs-log-dir="gs://forecastlab-prod-builds/builds"

echo "✅ 镜像构建完成: ${IMAGE_URI}"

# ─────────────────────────────────────────────────────────────
# Step 2: 部署 Cloud Run Job
# ─────────────────────────────────────────────────────────────
echo ""
echo "=== Step 2: 部署 Cloud Run Job ==="

# 构建 Job 命令
JOB_CMD="gcloud run jobs deploy ${JOB_NAME} \
    --image=${IMAGE_URI} \
    --region=${REGION} \
    --project=${PROJECT_ID} \
    --memory=${MEMORY} \
    --cpu=${CPU} \
    --max-retries=2 \
    --task-timeout=600s"

# 添加环境变量
JOB_CMD="${JOB_CMD} --set-env-vars=PYTHONUNBUFFERED=1"

if [ -n "${OUT_BUCKET}" ]; then
    JOB_CMD="${JOB_CMD} --set-env-vars=OUT_BUCKET=${OUT_BUCKET}"
fi

if [ -n "${NOTIFICATION_URL}" ]; then
    JOB_CMD="${JOB_CMD} --set-env-vars=NOTIFICATION_URL=${NOTIFICATION_URL}"
fi

if [ -n "${SMTP_USER}" ]; then
    JOB_CMD="${JOB_CMD} --set-env-vars=SMTP_USER=${SMTP_USER}"
fi

if [ -n "${SMTP_PASS}" ]; then
    JOB_CMD="${JOB_CMD} --set-env-vars=SMTP_PASS=${SMTP_PASS}"
fi

if [ -n "${MAIL_TO}" ]; then
    JOB_CMD="${JOB_CMD} --set-env-vars=MAIL_TO=${MAIL_TO}"
fi

if [ -n "${GEMINI_API_KEY}" ]; then
    JOB_CMD="${JOB_CMD} --set-env-vars=GEMINI_API_KEY=${GEMINI_API_KEY}"
fi

if [ -n "${SERVICE_ACCOUNT}" ]; then
    JOB_CMD="${JOB_CMD} --service-account=${SERVICE_ACCOUNT}"
fi

# 执行 Job 部署
echo "  部署 Job: ${JOB_NAME}"
eval ${JOB_CMD}

echo "✅ Job 部署完成: ${JOB_NAME}"

# ─────────────────────────────────────────────────────────────
# Step 3: 设置定时调度（可选）
# ─────────────────────────────────────────────────────────────
if [ "${SKIP_SCHEDULER:-false}" != "true" ]; then
    echo ""
    echo "=== Step 3: 设置定时调度 ==="

    # 检查调度器是否已存在
    if gcloud scheduler jobs describe "${SCHEDULER_NAME}" --location="${REGION}" --project="${PROJECT_ID}" 2>/dev/null; then
        echo "  更新现有调度器..."
        gcloud scheduler jobs update http "${SCHEDULER_NAME}" \
            --location="${REGION}" \
            --project="${PROJECT_ID}" \
            --uri="https://${REGION}-run.googleapis.com/apis/run/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run" \
            --schedule="0 0 * * *" \
            --time-zone="Asia/Shanghai" \
            --quiet
    else
        echo "  创建新调度器..."
        gcloud scheduler jobs create http "${SCHEDULER_NAME}" \
            --location="${REGION}" \
            --project="${PROJECT_ID}" \
            --uri="https://${REGION}-run.googleapis.com/apis/run/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run" \
            --schedule="0 0 * * *" \
            --time-zone="Asia/Shanghai" \
            --quiet
    fi

    echo "✅ 调度器设置完成: ${SCHEDULER_NAME}"
    echo "  运行时间: 每天北京时间 08:00 (UTC 00:00)"
else
    echo ""
    echo "=== Step 3: 跳过调度器设置 (SKIP_SCHEDULER=true) ==="
fi

# ─────────────────────────────────────────────────────────────
# 完成
# ─────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "✅ FcstLabPro v7 部署完成！"
echo "============================================================"
echo ""
echo "Job 信息:"
echo "  - Job 名称: ${JOB_NAME}"
echo "  - 镜像: ${IMAGE_URI}"
echo "  - 区域: ${REGION}"
echo ""
echo "手动触发:"
echo "  gcloud run jobs execute ${JOB_NAME} --region ${REGION}"
echo ""
echo "查看日志:"
echo "  gcloud logging read \\"
echo "    'resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${JOB_NAME}\"' \\"
echo "    --limit=50"
echo ""
echo "如需暂停调度:"
echo "  gcloud scheduler jobs pause ${SCHEDULER_NAME} --location=${REGION}"
echo ""
