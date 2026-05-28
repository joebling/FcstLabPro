#!/usr/bin/env bash
# =============================================================================
# FcstLabPro VPS 一键初始化脚本
#
# 用法（在 VPS 上以 root 或 sudo 权限运行）:
#   curl -fsSL <your-raw-url>/deploy/vps/setup_vps.sh | bash
#   ——或——
#   git clone <repo> FcstLabPro && cd FcstLabPro && bash deploy/vps/setup_vps.sh
#
# 该脚本会:
#   1. 安装 Docker（若未安装）
#   2. 创建持久化数据目录
#   3. 生成 .env 模板（如不存在）
#   4. 构建 Docker 镜像
#   5. 注册 cron 每日定时任务
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_DIR="/opt/fcstlabpro"
IMAGE_NAME="fcstlabpro"
CRON_USER="${SUDO_USER:-$(whoami)}"

echo "=============================================="
echo "🐶 FcstLabPro VPS 初始化开始"
echo "  项目目录: ${REPO_DIR}"
echo "  数据目录: ${DATA_DIR}"
echo "=============================================="

# ── 1. 安装 Docker ──────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo ""
    echo ">>> [1/5] 安装 Docker..."
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg lsb-release
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
         https://download.docker.com/linux/ubuntu \
         $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io
    systemctl enable docker
    systemctl start docker
    # 允许当前用户不用 sudo 运行 Docker
    usermod -aG docker "${CRON_USER}" || true
    echo "✅ Docker 已安装"
else
    echo ">>> [1/5] Docker 已存在，跳过安装"
fi

# ── 2. 创建持久化数据目录 ────────────────────────────────────────────────────
echo ""
echo ">>> [2/5] 创建数据目录..."
mkdir -p "${DATA_DIR}/state"    # 持仓状态 signal_state.json
mkdir -p "${DATA_DIR}/signals"  # 历史信号 JSON
mkdir -p "${DATA_DIR}/logs"     # 运行日志
chown -R "${CRON_USER}:${CRON_USER}" "${DATA_DIR}" 2>/dev/null || true
echo "✅ 数据目录就绪: ${DATA_DIR}"

# ── 3. 生成 .env 模板 ────────────────────────────────────────────────────────
ENV_FILE="${DATA_DIR}/.env"
if [ ! -f "${ENV_FILE}" ]; then
    echo ""
    echo ">>> [3/5] 生成 .env 模板..."
    cat > "${ENV_FILE}" << 'EOF'
# ============================================================
# FcstLabPro VPS 环境变量
# 填入你的配置后，重新运行 setup_vps.sh 或直接运行 run_daily.sh
# ============================================================

# ── 必填：模型选择 ─────────────────────────────────────────
# 可选: e1-conservative (风控优先) 或 e8-touch (收益优先)
MODEL_NAME=e1-conservative
STRATEGY_VARIANT=conservative

# ── 必填：邮件通知 ─────────────────────────────────────────
# QQ 邮箱授权码（在 QQ 邮箱设置 → 账户 → POP3/SMTP 生成）
SMTP_USER=your_qq@qq.com
SMTP_PASS=your_qq_smtp_authcode
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
MAIL_TO=your_receive@example.com

# ── 可选：外部 API ──────────────────────────────────────────
# CoinGecko Demo Key: https://www.coingecko.com/en/api/pricing
COINGECKO_API_KEY=
# Coinglass: https://www.coinglass.com/
COINGLASS_API_KEY=
# Gemini LLM 分析（可选，不填则跳过）
GEMINI_API_KEY=

# ── VPS 特有：状态桶留空（使用本地文件存储）────────────────
STATE_BUCKET=
EOF
    echo "✅ .env 模板已生成: ${ENV_FILE}"
    echo ""
    echo "⚠️  请编辑 ${ENV_FILE} 填入你的 SMTP 凭据等配置！"
    echo "   nano ${ENV_FILE}"
else
    echo ">>> [3/5] .env 已存在，跳过生成（${ENV_FILE}）"
fi

# ── 4. 构建 Docker 镜像 ──────────────────────────────────────────────────────
echo ""
echo ">>> [4/5] 构建 Docker 镜像（首次较慢，约 3-5 分钟）..."
docker build -t "${IMAGE_NAME}:latest" "${REPO_DIR}"
echo "✅ 镜像构建完成: ${IMAGE_NAME}:latest"

# ── 5. 注册 cron 定时任务 ────────────────────────────────────────────────────
echo ""
echo ">>> [5/5] 注册 cron 每日任务..."
RUNNER="${REPO_DIR}/deploy/vps/run_daily.sh"
chmod +x "${RUNNER}"

# 每天 UTC 00:10 运行（北京时间 08:10）
CRON_LINE="10 0 * * * bash ${RUNNER} >> ${DATA_DIR}/logs/daily_\$(date +\%Y\%m\%d).log 2>&1"

# 幂等：先删旧条目再添加
(crontab -u "${CRON_USER}" -l 2>/dev/null | grep -v "run_daily.sh" ; echo "${CRON_LINE}") \
    | crontab -u "${CRON_USER}" -

echo "✅ cron 已注册: 每日 UTC 00:10 运行"
echo "   查看: crontab -l"
echo "   日志: ${DATA_DIR}/logs/"

echo ""
echo "=============================================="
echo "🎉 初始化完成！"
echo ""
echo "下一步:"
echo "  1. 编辑配置: nano ${ENV_FILE}"
echo "  2. 手动测试: bash ${REPO_DIR}/deploy/vps/run_daily.sh"
echo "  3. 查看日志: tail -f ${DATA_DIR}/logs/daily_\$(date +%Y%m%d).log"
echo "=============================================="
