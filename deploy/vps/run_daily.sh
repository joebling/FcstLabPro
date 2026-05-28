#!/usr/bin/env bash
# =============================================================================
# FcstLabPro VPS 每日信号运行脚本
#
# cron 自动调用（由 setup_vps.sh 注册），也可手动运行:
#   bash deploy/vps/run_daily.sh
#
# 依赖:
#   - Docker 已安装
#   - /opt/fcstlabpro/.env 已配置
#   - fcstlabpro:latest 镜像已构建（见 setup_vps.sh）
# =============================================================================
set -euo pipefail

# ── 路径配置 ──────────────────────────────────────────────────────────────────
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_DIR="/opt/fcstlabpro"
ENV_FILE="${DATA_DIR}/.env"
IMAGE_NAME="fcstlabpro:latest"

echo "=============================================="
echo "🔮 FcstLabPro 每日信号 — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=============================================="

# ── 前置检查 ──────────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "❌ Docker 未安装。请先运行: bash ${REPO_DIR}/deploy/vps/setup_vps.sh"
    exit 1
fi

if [ ! -f "${ENV_FILE}" ]; then
    echo "❌ 找不到 ${ENV_FILE}"
    echo "   请先运行: bash ${REPO_DIR}/deploy/vps/setup_vps.sh"
    exit 1
fi

# 若镜像不存在则自动重建
if ! docker image inspect "${IMAGE_NAME}" &>/dev/null; then
    echo "⚠️  镜像 ${IMAGE_NAME} 不存在，自动重建..."
    docker build -t "${IMAGE_NAME}" "${REPO_DIR}"
fi

# ── 运行容器 ──────────────────────────────────────────────────────────────────
echo ""
echo "🐳 启动容器..."
echo "  镜像:   ${IMAGE_NAME}"
echo "  状态卷: ${DATA_DIR}/state → /tmp/state"
echo "  信号卷: ${DATA_DIR}/signals → /tmp/signals"
echo ""

docker run --rm \
    --name "fcstlabpro-$(date +%Y%m%d-%H%M%S)" \
    --env-file "${ENV_FILE}" \
    --volume "${DATA_DIR}/state:/tmp/state" \
    --volume "${DATA_DIR}/signals:/tmp/signals" \
    --memory="2g" \
    --cpus="2" \
    "${IMAGE_NAME}"

EXIT_CODE=$?

echo ""
if [ "${EXIT_CODE}" -eq 0 ]; then
    echo "✅ 运行完成 — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo "   信号文件: ls ${DATA_DIR}/signals/"
else
    echo "❌ 运行失败 (exit=${EXIT_CODE})"
    exit "${EXIT_CODE}"
fi
