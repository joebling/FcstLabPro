#!/usr/bin/env bash
# =============================================================================
# FcstLabPro VPS 一键初始化脚本
#
# 用法（root 或 sudo 运行）:
#   sudo bash deploy/vps/setup_vps.sh
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_DIR="/opt/fcstlabpro"
IMAGE_NAME="fcstlabpro"

# ── root 检查 ──────────────────────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
    echo "❌ 请用 root 或 sudo 运行: sudo bash $0"
    exit 1
fi

# 用于注册 cron 的实际用户（sudo 时取原始用户，直接 root 登录则为 root）
CRON_USER="${SUDO_USER:-root}"

echo "=============================================="
echo "🐶 FcstLabPro VPS 初始化开始"
echo "  项目目录: ${REPO_DIR}"
echo "  数据目录: ${DATA_DIR}"
echo "  cron 用户: ${CRON_USER}"
echo "=============================================="

# ── 1. 安装 Docker ────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo ""
    echo ">>> [1/5] 安装 Docker..."
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    # 获取系统架构和 Ubuntu 版本名称
    ARCH="$(dpkg --print-architecture)"
    # shellcheck source=/dev/null
    UBUNTU_CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME}")"

    echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin
    systemctl enable docker
    systemctl start docker

    # 允许 CRON_USER 不用 sudo 跑 Docker
    if [ "${CRON_USER}" != "root" ]; then
        usermod -aG docker "${CRON_USER}"
        echo "ℹ️  ${CRON_USER} 已加入 docker 组（重新登录后生效）"
    fi
    echo "✅ Docker 已安装"
else
    echo ">>> [1/5] Docker 已存在，跳过安装 ($(docker --version))"
fi

# ── 2. 创建持久化数据目录 ──────────────────────────────────────────────────
echo ""
echo ">>> [2/5] 创建数据目录..."
mkdir -p "${DATA_DIR}/state"    # 持仓状态 signal_state.json
mkdir -p "${DATA_DIR}/signals"  # 历史信号 JSON
mkdir -p "${DATA_DIR}/logs"     # 运行日志
chown -R "${CRON_USER}:${CRON_USER}" "${DATA_DIR}" 2>/dev/null || true
echo "✅ 数据目录就绪: ${DATA_DIR}"

# ── 3. 生成 .env 模板 ────────────────────────────────────────────────────
ENV_FILE="${DATA_DIR}/.env"
if [ ! -f "${ENV_FILE}" ]; then
    echo ""
    echo ">>> [3/5] 生成 .env 模板..."
    cat > "${ENV_FILE}" << 'ENVEOF'
# ============================================================
# FcstLabPro VPS 环境变量  —  填写后保存，再跑 run_daily.sh
# ============================================================

# ── 必填：模型选择 ──────────────────────────────────────────
# 可选: e1-conservative (风控优先) | e8-touch (收益优先)
MODEL_NAME=e1-conservative
STRATEGY_VARIANT=conservative

# ── 必填：邮件通知 ──────────────────────────────────────────
# QQ 邮箱「授权码」（设置 → 账户 → POP3/SMTP → 生成授权码）
# 注意：不是 QQ 登录密码！
SMTP_USER=your_qq@qq.com
SMTP_PASS=your_qq_smtp_authcode
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
MAIL_TO=your_receive@example.com

# ── 可选：外部 API ───────────────────────────────────────────
COINGECKO_API_KEY=
COINGLASS_API_KEY=
GEMINI_API_KEY=

# ── VPS 专用：留空，使用本地卷代替 GCS ─────────────────────
STATE_BUCKET=
ENVEOF
    chmod 600 "${ENV_FILE}"
    echo "✅ .env 模板已生成: ${ENV_FILE}"
    echo ""
    echo "⚠️  请编辑配置文件: nano ${ENV_FILE}"
else
    echo ">>> [3/5] .env 已存在，跳过（${ENV_FILE}）"
fi

# ── 4. 构建 Docker 镜像 ───────────────────────────────────────────────────
echo ""
echo ">>> [4/5] 构建 Docker 镜像（首次约 3-5 分钟）..."
docker build -t "${IMAGE_NAME}:latest" "${REPO_DIR}"
echo "✅ 镜像构建完成: ${IMAGE_NAME}:latest"

# ── 5. 注册 cron 定时任务 ─────────────────────────────────────────────────
echo ""
echo ">>> [5/5] 注册 cron 每日任务..."
RUNNER="${REPO_DIR}/deploy/vps/run_daily.sh"
chmod +x "${RUNNER}"

# 每天 UTC 00:10 运行（北京时间 08:10）
# 注意：cron 里 % 需要转义为 \%
CRON_LINE="10 0 * * * bash ${RUNNER} >> ${DATA_DIR}/logs/daily_\$(date +\%Y\%m\%d).log 2>&1"

if [ "${CRON_USER}" = "root" ]; then
    # 直接操作 root 的 crontab
    ( crontab -l 2>/dev/null | grep -v "run_daily.sh" ; echo "${CRON_LINE}" ) | crontab -
else
    # 操作指定用户的 crontab
    ( crontab -u "${CRON_USER}" -l 2>/dev/null | grep -v "run_daily.sh" ; echo "${CRON_LINE}" ) \
        | crontab -u "${CRON_USER}" -
fi

echo "✅ cron 已注册（${CRON_USER}）: 每日 UTC 00:10"
echo "   查看: crontab -l"
echo "   日志: ${DATA_DIR}/logs/"

echo ""
echo "=============================================="
echo "🎉 初始化完成！"
echo ""
echo "下一步:"
echo "  1. 填写配置:  nano ${ENV_FILE}"
echo "  2. 手动测试:  bash ${RUNNER}"
echo "  3. 查看日志:  tail -f ${DATA_DIR}/logs/daily_\$(date +%Y%m%d).log"
echo "=============================================="
