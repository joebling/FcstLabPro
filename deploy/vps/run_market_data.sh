#!/usr/bin/env bash
# =============================================================================
# FcstLabPro VPS 市场展示数据同步 —— 独立 best-effort 任务 (与信号 pipeline 解耦)
#
# 编排逻辑在 scripts/sync_market_data.py:
#   刷新 funding + OI/多空比(merge) + macro, 每源独立 try/except。
#
# 这些**不是**模型特征 (模型只吃 OHLCV+FGI), 故本任务与信号完全隔离:
# 它挂了只影响市场图, 信号毫发无伤。
#
# 调度: 建议每 6 小时 (覆盖 funding 8h 结算 + 美股收盘后刷 macro + 瞬时失败自恢复)。
#   crontab 示例:
#     0 */6 * * * /opt/.../FcstLabPro/deploy/vps/run_market_data.sh >> /var/log/fcstlab_market.log 2>&1
#
# git 冲突治理 (data/external 是 tracked, 本任务会原地改写 CSV):
#   拉代码前先丢弃本地再生数据, 再 pull (反正下次 sync 自动重灌):
#     git checkout -- data/external/*.csv && git pull
# =============================================================================
set -uo pipefail  # 不用 -e: best-effort, 单源失败不该让整脚本崩

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_PYTHON="${REPO_DIR}/.venv/bin/python"
ENV_FILE="${REPO_DIR}/.env"

echo "=============================================="
echo " FcstLabPro 市场数据同步 — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=============================================="

# ── 前置检查 ──────────────────────────────────────────────────────────────
if [ ! -f "${VENV_PYTHON}" ]; then
    echo " 虚拟环境不存在: ${VENV_PYTHON}"
    exit 1
fi

# ── 加载环境变量 (若有) ────────────────────────────────────────────────────
if [ -f "${ENV_FILE}" ]; then
    set -a
    # shellcheck source=/dev/null
    source "${ENV_FILE}"
    set +a
fi

export PYTHONPATH="${REPO_DIR}:${PYTHONPATH:-}"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

# ── 点火 ───────────────────────────────────────────────────────────────────
"${VENV_PYTHON}" "${REPO_DIR}/scripts/sync_market_data.py"
RC=$?

if [ "${RC}" -ne 0 ]; then
    echo " 部分市场数据源同步失败 (退出码 ${RC}) — 市场图可能未全部刷新, 信号不受影响"
fi
exit "${RC}"
