#!/usr/bin/env bash
# =============================================================================
# FcstLabPro VPS 无 Docker 初始化脚本
#
# 用法（root 或 sudo）:
#   sudo bash deploy/vps/setup_vps_nodock.sh
#
# 做的事：
#   1. 安装系统依赖（Python 3.10+, libgomp1）
#   2. 创建 Python 虚拟环境 + 安装依赖
#   3. 生成 .env 模板
#   4. 注册 cron 定时任务
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_DIR="/opt/fcstlabpro"
VENV_DIR="${REPO_DIR}/.venv"

# ── root 检查 ──────────────────────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
    echo "❌ 请用 sudo 运行: sudo bash $0"
    exit 1
fi
CRON_USER="${SUDO_USER:-root}"

echo "=============================================="
echo "🐶 FcstLabPro VPS 初始化（无 Docker）"
echo "  项目目录: ${REPO_DIR}"
echo "  虚拟环境: ${VENV_DIR}"
echo "  数据目录: ${DATA_DIR}"
echo "  cron 用户: ${CRON_USER}"
echo "=============================================="

# ── 1. 系统依赖 ────────────────────────────────────────────────────────────
echo ""
echo ">>> [1/4] 安装系统依赖..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv libgomp1
echo "✅ 系统依赖就绪 (Python $(python3 --version))"

# ── 2. 虚拟环境 + Python 依赖 ──────────────────────────────────────────────
echo ""
echo ">>> [2/4] 安装 Python 依赖..."
python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip setuptools wheel
"${VENV_DIR}/bin/pip" install --quiet -r "${REPO_DIR}/requirements.txt"
# 安装项目本身（让 src/ 可以被 import）
"${VENV_DIR}/bin/pip" install --quiet -e "${REPO_DIR}"
chown -R "${CRON_USER}:${CRON_USER}" "${VENV_DIR}" 2>/dev/null || true
echo "✅ Python 环境就绪: ${VENV_DIR}"

# ── 3. 持久化数据目录 ──────────────────────────────────────────────────────
echo ""
echo ">>> [3/4] 创建数据目录..."
mkdir -p "${DATA_DIR}/state"    # 持仓状态
mkdir -p "${DATA_DIR}/signals"  # 信号 JSON
mkdir -p "${DATA_DIR}/logs"     # 运行日志
chown -R "${CRON_USER}:${CRON_USER}" "${DATA_DIR}" 2>/dev/null || true
echo "✅ 数据目录: ${DATA_DIR}"

# ── 生成 .env 模板 ──────────────────────────────────────────────
# 配置唯一真相源: 仓库根 .env (被 .gitignore 忽略, git pull 碰不到)。
ENV_FILE="${REPO_DIR}/.env"
if [ ! -f "${ENV_FILE}" ]; then
    cat > "${ENV_FILE}" << 'ENVEOF'
# ============================================================
# FcstLabPro VPS 环境变量  —  填写后保存
# ============================================================

# 串行运行多个模型，用英文逗号分隔。
# 如果只想跑一个模型，也可以只保留一个值。
MODEL_NAMES=e1-conservative,e8-touch
STRATEGY_VARIANT=conservative

SMTP_USER=your_qq@qq.com
SMTP_PASS=your_qq_smtp_authcode
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
MAIL_TO=your_receive@example.com

COINGECKO_API_KEY=
COINGLASS_API_KEY=

# LLM 策略分析 (可选): LLM_PROVIDER=gemini / deepseek / anthropic
LLM_PROVIDER=gemini
GEMINI_API_KEY=
# 官方 DeepSeek (platform.deepseek.com, OpenAI 兼容格式):
# LLM_PROVIDER=deepseek
# DEEPSEEK_API_KEY=sk-xxxxx
# LLM_MODEL=deepseek-chat            # 可选, 默认 deepseek-chat
# LLM_BASE_URL=https://api.deepseek.com   # 可选, 默认即此
# anthropic (如 DeepSeek via 腾讯 tokenhub):
# LLM_PROVIDER=anthropic
# LLM_API_KEY=
# LLM_BASE_URL=https://tokenhub.tencentmaas.com/
# LLM_MODEL=deepseek-v4-pro

STATE_BUCKET=
ENVEOF
    chmod 600 "${ENV_FILE}"
    echo "⚠️  请填写配置: nano ${ENV_FILE}"
else
    echo "ℹ️  .env 已存在，跳过"
fi

# ── 4. 注册 cron ───────────────────────────────────────────────────────────
echo ""
echo ">>> [4/4] 注册 cron 定时任务..."
RUNNER="${REPO_DIR}/deploy/vps/run_daily_nodock.sh"
chmod +x "${RUNNER}"

# 每天 UTC 00:10（北京时间 08:10）
CRON_LINE="10 0 * * * bash ${RUNNER} >> ${DATA_DIR}/logs/daily_\$(date +\%Y\%m\%d).log 2>&1"

if [ "${CRON_USER}" = "root" ]; then
    ( crontab -l 2>/dev/null | grep -v "run_daily_nodock" ; echo "${CRON_LINE}" ) | crontab -
else
    ( crontab -u "${CRON_USER}" -l 2>/dev/null | grep -v "run_daily_nodock" ; echo "${CRON_LINE}" ) \
        | crontab -u "${CRON_USER}" -
fi

echo "✅ cron 已注册: 每日 UTC 00:10"

echo ""
echo "=============================================="
echo "🎉 初始化完成！"
echo ""
echo "下一步:"
echo "  1. 填写配置:  nano ${ENV_FILE}"
echo "  2. 手动测试:  bash ${RUNNER}"
echo "  3. 查看日志:  tail -f ${DATA_DIR}/logs/daily_\$(date +%Y%m%d).log"
echo "=============================================="
