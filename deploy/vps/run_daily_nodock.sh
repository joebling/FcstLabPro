#!/usr/bin/env bash
# =============================================================================
# FcstLabPro VPS 每日信号运行脚本（无 Docker）—— 点火瘦壳 (路 B)
#
# 编排逻辑全部收敛到 scripts/run_production_pipeline.py:
#   下载 OHLCV → 下载 FGI → freshness 强校验(决策A) → 信号 → JSON → LLM → 邮件
#
# 本脚本只负责 bash 擅长的事: 加载 .env、前置检查、线程设置, 然后点火。
# 模型清单 / 变体由 models/production/active.yaml 决定 (单一真相源),
# 不再用 MODEL_NAMES / STRATEGY_VARIANT 环境变量 (那是旧的多处真相源做法)。
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_DIR="/opt/fcstlabpro"
VENV_PYTHON="${REPO_DIR}/.venv/bin/python"
ENV_FILE="${DATA_DIR}/.env"

echo "=============================================="
echo "🔮 FcstLabPro 每日信号 — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=============================================="

# ── 前置检查 ──────────────────────────────────────────────────────────────
if [ ! -f "${VENV_PYTHON}" ]; then
    echo "❌ 虚拟环境不存在: ${VENV_PYTHON}"
    echo "   请先运行: sudo bash ${REPO_DIR}/deploy/vps/setup_vps_nodock.sh"
    exit 1
fi
if [ ! -f "${ENV_FILE}" ]; then
    echo "❌ 找不到 ${ENV_FILE}，请先配置"
    exit 1
fi

# ── 加载环境变量 ───────────────────────────────────────────────────────────
set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +a

export PYTHONPATH="${REPO_DIR}:${PYTHONPATH:-}"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

# 输出根目录: pipeline 默认 /opt/fcstlabpro, 显式传入保持一致
export FCST_DATA_DIR="${DATA_DIR}"

# ── 点火: 编排全部委托给 pipeline ───────────────────────────────────────────
# --include-paper: 连 active.yaml 里 status=paper 的模型也跑 (如需只跑 live, 去掉它)
exec "${VENV_PYTHON}" "${REPO_DIR}/scripts/run_production_pipeline.py" --include-paper "$@"
