#!/usr/bin/env bash
# =============================================================================
# FcstLabPro v0215 — 只构建和推送 Docker 镜像
# 用途：更新镜像后重新构建并推送，不部署 Cloud Run Job
# =============================================================================
set -euo pipefail

# 加载本地 .env 文件
if [ -f "$(dirname "$0")/../.env" ]; then
    set -a
    source "$(dirname "$0")/../.env"
    set +a
fi

PROJECT_ID="${GCP_PROJECT_ID:-forecastlab-prod}"
REGION="asia-east1"
REPO_NAME="fcstlabpro"
IMAGE_NAME="fcstlabpro-0215"
TIMESTAMP=$(date +%Y%m%d%H%M%S)
IMAGE_TAG="${TIMESTAMP}"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${IMAGE_TAG}"
LATEST_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:latest"

echo ""
echo "=== 构建并推送 v0215 镜像 ==="
echo "  镜像: ${IMAGE_URI}"
echo ""

# 设置项目
gcloud config set project "${PROJECT_ID}" --quiet

# 启用 API
gcloud services enable artifactregistry.googleapis.com --quiet 2>/dev/null || true

# 创建仓库（如果不存在）
gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" 2>/dev/null || {
    echo "  创建 Artifact Registry 仓库..."
    gcloud artifacts repositories create "${REPO_NAME}" \
        --location="${REGION}" \
        --repository-format=docker \
        --quiet
}

# 构建并推送
echo "  开始构建..."
gcloud builds submit \
    --tag "${IMAGE_URI}" \
    --tag "${LATEST_URI}" \
    --project="${PROJECT_ID}" \
    --gcs-log-dir="gs://forecastlab-prod-builds/builds"

echo ""
echo "✅ 镜像构建完成！"
echo "  ${IMAGE_URI}"
echo "  ${LATEST_URI}"
echo ""
echo "现在可以运行 VM 任务了："
echo "  ./deploy/deploy_vm.sh"
