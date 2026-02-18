#!/usr/bin/env bash
# =============================================================================
# FcstLabPro v0215 — Compute Engine VM 完整部署脚本
# 功能：构建镜像 → 推送 → 创建 VM → 设置 cron 定时任务
#
# 用法：
#   ./deploy/deploy_vm_v0215.sh          # 完整流程（构建+推送+部署+设置cron）
#   ./deploy/deploy_vm_v0215.sh build    # 仅构建和推送镜像
#   ./deploy/deploy_vm_v0215.sh deploy   # 仅部署VM和设置cron
#   ./deploy/deploy_vm_v0215.sh run      # 仅手动运行一次任务
# =============================================================================
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# 加载配置
# ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"

if [ -f "${PROJECT_ROOT}/.env" ]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

PROJECT_ID="${GCP_PROJECT_ID:-forecastlab-prod}"
REGION="asia-east1"
ZONE="asia-east1-a"
REPO_NAME="fcstlabpro"
IMAGE_NAME="fcstlabpro-0215"
VM_NAME="fcstlabpro-signal-vm"
MACHINE_TYPE="n2d-standard-8"  # 8 vCPU, 32GB 内存
TIMESTAMP=$(date +%Y%m%d%H%M%S)
IMAGE_TAG="${TIMESTAMP}"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${IMAGE_TAG}"
LATEST_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:latest"

# ─────────────────────────────────────────────────────────────
# 步骤 1: 构建和推送镜像
# ─────────────────────────────────────────────────────────────
build_and_push() {
    echo ""
    echo "=============================================="
    echo "📦 步骤 1: 构建并推送 Docker 镜像"
    echo "=============================================="
    echo ""
    echo "  项目: ${PROJECT_ID}"
    echo "  镜像: ${IMAGE_URI}"
    echo ""

    cd "${PROJECT_ROOT}"

    # 运行测试
    echo "  🧪 运行推理流程测试..."
    source venv_py310/bin/activate || source venv/bin/activate
    python -m pytest tests/test_inference_pipeline.py -v 2>/dev/null || python tests/test_inference_pipeline.py

    echo ""
    echo "  🧪 运行邮件内容测试..."
    python -m pytest tests/test_email_content.py -v 2>/dev/null || python tests/test_email_content.py

    # 设置项目
    gcloud config set project "${PROJECT_ID}" --quiet

    # 启用 API
    gcloud services enable artifactregistry.googleapis.com --quiet 2>/dev/null || true

    # 创建仓库（如果不存在）
    gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" 2>/dev/null || {
        echo "  📁 创建 Artifact Registry 仓库..."
        gcloud artifacts repositories create "${REPO_NAME}" \
            --location="${REGION}" \
            --repository-format=docker \
            --quiet
    }

    # 构建并推送
    echo "  🔨 开始构建..."
    gcloud builds submit \
        --tag "${IMAGE_URI}" \
        --tag "${LATEST_URI}" \
        --project="${PROJECT_ID}" \
        --gcs-log-dir="gs://forecastlab-prod-builds/builds"

    echo ""
    echo "✅ 镜像构建完成！"
    echo "  ${IMAGE_URI}"
    echo "  ${LATEST_URI}"
}

# ─────────────────────────────────────────────────────────────
# 步骤 2: 创建/检查 VM
# ─────────────────────────────────────────────────────────────
setup_vm() {
    echo ""
    echo "=============================================="
    echo "🖥️  步骤 2: 设置 Compute Engine VM"
    echo "=============================================="
    echo ""

    # 检查/创建 VM
    if ! gcloud compute instances describe "${VM_NAME}" --zone="${ZONE}" >/dev/null 2>&1; then
        echo "VM 不存在，正在创建 (${MACHINE_TYPE})..."
        gcloud compute instances create "${VM_NAME}" \
            --zone="${ZONE}" \
            --machine-type="${MACHINE_TYPE}" \
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

    # 在 VM 上安装 Docker
    echo ""
    echo "🐳 在 VM 上安装 Docker..."
    gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --tunnel-through-iap --command="
        if ! command -v docker &> /dev/null; then
            echo '📦 安装 Docker...'
            curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
            sudo sh /tmp/get-docker.sh
            sudo systemctl start docker
            sudo systemctl enable docker
        fi
        sudo gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet
    "
    echo "✅ Docker 配置完成"
}

# ─────────────────────────────────────────────────────────────
# 步骤 3: 创建运行脚本
# ─────────────────────────────────────────────────────────────
create_run_script() {
    echo ""
    echo "📝 步骤 3: 创建 VM 运行脚本"
    echo ""

    gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --tunnel-through-iap --command="
        cat > /home/\$USER/run_fcstlabpro.sh << 'EOF'
#!/bin/bash
# FcstLabPro 每日运行脚本
set -e

echo \"==============================================\"
echo \"🔮 FcstLabPro 每日任务 - \$(date '+%Y-%m-%d %H:%M:%S')\"
echo \"==============================================\"

# 拉取最新镜像
echo \"📥 拉取最新镜像...\"
sudo docker pull ${LATEST_URI}

# 运行容器（包含环境变量）
echo \"🚀 运行容器...\"
sudo docker rm -f fcstlabpro-daily 2>/dev/null || true
sudo docker run --name fcstlabpro-daily \\
    -e SMTP_HOST=${SMTP_HOST:-smtp.qq.com} \\
    -e SMTP_PORT=${SMTP_PORT:-465} \\
    -e SMTP_USER=${SMTP_USER:-} \\
    -e SMTP_PASS=${SMTP_PASS:-} \\
    -e MAIL_TO=${MAIL_TO:-} \\
    -e GEMINI_API_KEY=${GEMINI_API_KEY:-} \\
    ${LATEST_URI}

# 清理
echo \"🧹 清理完成\"
sudo docker rm -f fcstlabpro-daily 2>/dev/null || true

echo \"✅ 任务完成\"
EOF

        chmod +x /home/\$USER/run_fcstlabpro.sh
    "
    echo "✅ 运行脚本已创建"
}

# ─────────────────────────────────────────────────────────────
# 步骤 4: 设置 cron 定时任务
# ─────────────────────────────────────────────────────────────
setup_cron() {
    echo ""
    echo "⏰ 步骤 4: 设置 cron 定时任务"
    echo ""

    gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --tunnel-through-iap --command="
        # 备份当前 crontab
        crontab -l > /tmp/crontab_backup.txt 2>/dev/null || true
        
        # 移除旧的 fcstlabpro 任务（如果有）
        (crontab -l 2>/dev/null | grep -v 'fcstlabpro') | crontab -
        
        # 添加新的 cron 任务（每天 UTC 00:00 = 北京时间 08:00）
        (crontab -l 2>/dev/null; echo \"0 0 * * * /home/\$USER/run_fcstlabpro.sh >> /home/\$USER/fcstlabpro_cron.log 2>&1\") | crontab -
        
        # 验证
        echo \"当前 crontab 配置：\"
        crontab -l
    "
    echo "✅ cron 任务已设置"
}

# ─────────────────────────────────────────────────────────────
# 手动运行一次任务
# ─────────────────────────────────────────────────────────────
run_task() {
    echo ""
    echo "🎯 手动运行一次任务"
    echo ""

    gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --tunnel-through-iap --command="
        /home/\$USER/run_fcstlabpro.sh
    "
}

# ─────────────────────────────────────────────────────────────
# 主函数
# ─────────────────────────────────────────────────────────────
main() {
    local cmd="${1:-full}"

    echo ""
    echo "=============================================="
    echo "🚀 FcstLabPro v0215 VM 完整部署"
    echo "=============================================="
    echo ""
    echo "  项目: ${PROJECT_ID}"
    echo "  区域: ${REGION}"
    echo "  VM: ${VM_NAME}"
    echo ""

    case "${cmd}" in
        build)
            build_and_push
            ;;
        deploy)
            setup_vm
            create_run_script
            setup_cron
            ;;
        run)
            run_task
            ;;
        full)
            build_and_push
            setup_vm
            create_run_script
            setup_cron
            echo ""
            echo "=============================================="
            echo "🎉 部署完成！"
            echo "=============================================="
            echo ""
            echo "📅 运行时间：每天 UTC 00:00（北京时间 08:00）"
            echo ""
            echo "🧪 手动测试："
            echo "  ./deploy/deploy_vm_v0215.sh run"
            echo ""
            echo "📜 查看 cron 日志："
            echo "  gcloud compute ssh ${VM_NAME} --zone=${ZONE} --tunnel-through-iap --command='tail -f /home/\$USER/fcstlabpro_cron.log'"
            echo ""
            ;;
        *)
            echo "用法："
            echo "  ./deploy/deploy_vm_v0215.sh          # 完整流程（构建+推送+部署+设置cron）"
            echo "  ./deploy/deploy_vm_v0215.sh build    # 仅构建和推送镜像"
            echo "  ./deploy/deploy_vm_v0215.sh deploy   # 仅部署VM和设置cron"
            echo "  ./deploy/deploy_vm_v0215.sh run      # 仅手动运行一次任务"
            echo ""
            exit 1
            ;;
    esac
}

main "$@"
