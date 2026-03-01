#!/usr/bin/env bash
# =============================================================================
# FcstLabPro v0218 — Google Cloud Run Job 部署脚本
# 每天北京时间 08:00 (UTC 00:00) 运行
#
# Bull 模型: Orion-BiX v2 (T=21)
# 策略: 信号反转 + 三重MA过滤 (MA50+MA150+MA200) + 14天持仓期
#
# 前置条件:
#   1. 安装 gcloud CLI 并登录: gcloud auth login
#   2. 创建 GCP 项目并设为当前项目: gcloud config set project <PROJECT_ID>
#   3. 启用计费
#
# 用法:
#   chmod +x deploy/deploy_v0218.sh
#   ./deploy/deploy_v0218.sh              # 完整流程
#   ./deploy/deploy_v0218.sh build        # 仅构建镜像
#   ./deploy/deploy_v0218.sh deploy       # 仅部署 Job
#   ./deploy_v0218.sh scheduler           # 仅设置定时
# =============================================================================
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# 配置变量
# ─────────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-forecastlab-prod}"
REGION="asia-east1"
REPO_NAME="fcstlabpro"
IMAGE_NAME="fcstlabpro-v0218"
IMAGE_TAG="latest"
JOB_NAME="daily-btc-signal-v0218"
SCHEDULER_NAME="daily-btc-signal-v0218-trigger"
MEMORY="16Gi"
CPU="4"

# 完整镜像地址
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${IMAGE_TAG}"

# ─────────────────────────────────────────────────────────────
# Step 0: 前置检查
# ─────────────────────────────────────────────────────────────
echo ""
echo "=== FcstLabPro v0218 部署脚本 ==="
echo "  Bull 模型: Orion-BiX v2 (T=21)"
echo "  策略: 信号反转 + 三重MA过滤 + 14天持仓期"
echo ""
echo "=== Step 0: 前置检查 ==="
echo "  项目: ${PROJECT_ID}"
echo "  区域: ${REGION}"
echo "  镜像: ${IMAGE_URI}"
echo "  Job:  ${JOB_NAME}"
echo ""

command -v gcloud >/dev/null 2>&1 || { echo "❌ 请先安装 gcloud CLI"; exit 1; }
ls Dockerfile >/dev/null 2>&1 || { echo "❌ 请在项目根目录运行此脚本"; exit 1; }

gcloud config set project "${PROJECT_ID}" --quiet

echo "✅ 前置检查通过"

# ─────────────────────────────────────────────────────────────
# Step 1: 构建并推送镜像
# ─────────────────────────────────────────────────────────────
if [[ "${1:-}" == "deploy" || "${1:-}" == "scheduler" || -z "${1:-}" ]]; then
    echo ""
    echo "=== Step 1: 构建并推送镜像 ==="
    echo "  镜像: ${IMAGE_URI}"
    echo ""

    echo "  启用 Artifact Registry API..."
    gcloud services enable artifactregistry.googleapis.com --quiet 2>/dev/null || true
    echo "  启用 Cloud Run API..."
    gcloud services enable run.googleapis.com --quiet 2>/dev/null || true
    echo "  启用 Cloud Scheduler API..."
    gcloud services enable cloudscheduler.googleapis.com --quiet 2>/dev/null || true

    echo "  检查 Artifact Registry 仓库..."
    gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" 2>/dev/null || {
        echo "  创建 Artifact Registry 仓库..."
        gcloud artifacts repositories create "${REPO_NAME}" \
            --location="${REGION}" \
            --repository-format=docker \
            --quiet
    }

    echo "  构建 Docker 镜像..."
    gcloud builds submit \
        --tag "${IMAGE_URI}" \
        --project="${PROJECT_ID}" \
        --gcs-log-dir="gs://forecastlab-prod-builds/builds"

    echo "✅ 镜像构建完成: ${IMAGE_URI}"
fi

# ─────────────────────────────────────────────────────────────
# Step 2: 部署 Cloud Run Job
# ─────────────────────────────────────────────────────────────
if [[ "${1:-}" == "scheduler" || -z "${1:-}" ]]; then
    echo ""
    echo "=== Step 2: 部署 Cloud Run Job ==="

    # 检查 Job 是否已存在
    if gcloud run jobs describe "${JOB_NAME}" --region="${REGION}" --project="${PROJECT_ID}" 2>/dev/null; then
        echo "  更新现有 Job..."
        gcloud run jobs deploy "${JOB_NAME}" \
            --image="${IMAGE_URI}" \
            --region="${REGION}" \
            --project="${PROJECT_ID}" \
            --memory="${MEMORY}" \
            --cpu="${CPU}" \
            --max-retries=2 \
            --task-timeout=3600s \
            --set-env-vars=PYTHONUNBUFFERED=1 \
            --quiet
    else
        echo "  创建新 Job..."
        gcloud run jobs deploy "${JOB_NAME}" \
            --image="${IMAGE_URI}" \
            --region="${REGION}" \
            --project="${PROJECT_ID}" \
            --memory="${MEMORY}" \
            --cpu="${CPU}" \
            --max-retries=2 \
            --task-timeout=3600s \
            --set-env-vars=PYTHONUNBUFFERED=1
    fi

    echo "✅ Job 部署完成: ${JOB_NAME}"
fi

# ─────────────────────────────────────────────────────────────
# Step 3: 设置定时调度
# ─────────────────────────────────────────────────────────────
if [[ -z "${1:-}" ]]; then
    echo ""
    echo "=== Step 3: 设置定时调度 ==="

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
fi

# ─────────────────────────────────────────────────────────────
# 完成
# ─────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "✅ FcstLabPro v0218 部署完成！"
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
