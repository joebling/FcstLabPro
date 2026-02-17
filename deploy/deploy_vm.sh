#!/usr/bin/env bash
# =============================================================================
# FcstLabPro v0215 — Compute Engine VM 部署脚本（统一简洁版）
# 功能：创建 VM + 运行任务，一键搞定
#
# 用法：
#   ./deploy/deploy_vm.sh
# =============================================================================
set -euo pipefail

# 配置
PROJECT_ID="${GCP_PROJECT_ID:-forecastlab-prod}"
REGION="asia-east1"
ZONE="asia-east1-a"
VM_NAME="fcstlabpro-signal-vm"
MACHINE_TYPE="n2d-standard-8"  # 8 vCPU, 32GB 内存
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/fcstlabpro/fcstlabpro-0215:latest"

echo ""
echo "=============================================="
echo "🚀 FcstLabPro VM 部署"
echo "=============================================="
echo ""

# 1. 检查/创建 VM
echo "=== 步骤 1: 检查 VM ==="
if ! gcloud compute instances describe ${VM_NAME} --zone=${ZONE} >/dev/null 2>&1; then
    echo "VM 不存在，正在创建 (${MACHINE_TYPE})..."
    gcloud compute instances create ${VM_NAME} \
        --zone=${ZONE} \
        --machine-type=${MACHINE_TYPE} \
        --boot-disk-size=50GB \
        --image-family=ubuntu-2204-lts \
        --image-project=ubuntu-os-cloud \
        --scopes=https://www.googleapis.com/auth/cloud-platform
    echo "✅ VM 创建成功！"
    echo "等待 60 秒启动..."
    sleep 60
else
    echo "✅ VM 已存在"
fi

# 2. 在 VM 上运行任务
echo ""
echo "=== 步骤 2: 运行任务 ==="
echo "（如果提示输入 SSH 密码，直接按 Enter）"
echo ""

gcloud compute ssh ${VM_NAME} --zone=${ZONE} --command="
    set -e
    echo '=============================================='
    echo '🚀 VM 内部执行'
    echo '=============================================='

    # 安装 Docker（如果需要）
    if ! command -v docker &> /dev/null; then
        echo ''
        echo '📦 安装 Docker...'
        curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
        sudo sh /tmp/get-docker.sh
    fi

    # 启动 Docker
    sudo systemctl start docker
    sudo systemctl enable docker

    # 配置凭证
    sudo gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet

    # 拉取镜像
    echo ''
    echo '📥 拉取镜像...'
    sudo docker pull ${IMAGE_URI}

    # 运行
    echo ''
    echo '🎯 运行任务...'
    sudo docker run --rm \\
        -e OUT_BUCKET=${OUT_BUCKET:-} \\
        -e NOTIFICATION_URL=${NOTIFICATION_URL:-} \\
        -e SMTP_USER=${SMTP_USER:-} \\
        -e SMTP_PASS=${SMTP_PASS:-} \\
        -e MAIL_TO=${MAIL_TO:-} \\
        -e GEMINI_API_KEY=${GEMINI_API_KEY:-} \\
        ${IMAGE_URI}

    echo ''
    echo '=============================================='
    echo '✅ 任务完成！'
    echo '=============================================='
"

echo ""
echo "=============================================="
echo "🎉 全部完成！"
echo "=============================================="
echo ""
echo "下次运行任务，直接执行："
echo "  ./deploy/deploy_vm.sh"
