#!/usr/bin/env bash
# =============================================================================
# FcstLabPro VPS 每日信号运行脚本（无 Docker）
#
# cron 自动调用，也可手动运行:
#   bash deploy/vps/run_daily_nodock.sh
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_DIR="/opt/fcstlabpro"
VENV_PYTHON="${REPO_DIR}/.venv/bin/python"
ENV_FILE="${DATA_DIR}/.env"
STATE_FILE="${DATA_DIR}/state/signal_state.json"
OUT_DIR="${DATA_DIR}/signals"

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

MODEL_NAME="${MODEL_NAME:?MODEL_NAME 未在 .env 中设置}"
STRATEGY_VARIANT="${STRATEGY_VARIANT:-conservative}"
MODEL_DIR="${REPO_DIR}/models/production/${MODEL_NAME}"

mkdir -p "${OUT_DIR}"

echo ""
echo "📊 配置:"
echo "  模型: ${MODEL_NAME}  变体: ${STRATEGY_VARIANT}"
echo ""

# ── Step 1: 下载数据 ────────────────────────────────────────────────────────
echo "=== Step 1: 下载数据 ==="
"${VENV_PYTHON}" - << 'PYEOF'
import sys
sys.path.insert(0, __import__('os').environ['REPO_DIR'] if 'REPO_DIR' in __import__('os').environ else '.')
from pathlib import Path

Path("/tmp/fcstlabpro_data/raw").mkdir(parents=True, exist_ok=True)

try:
    from src.data.downloader import download_binance_klines
    print("📥 下载 Binance BTCUSDT 日线...")
    df = download_binance_klines(symbol="BTCUSDT", interval="1d", start="2020-01-01")
    out = Path(__import__('os').environ.get('REPO_DIR', '.')) / "data/raw/btc_binance_BTCUSDT_1d.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out)
    print(f"✅ 已保存: {out} ({len(df)} 行)")
except Exception as e:
    print(f"⚠️  Binance API: {e}，尝试使用本地缓存...")
    cache = Path(__import__('os').environ.get('REPO_DIR', '.')) / "data/raw/btc_binance_BTCUSDT_1d.csv"
    if not cache.exists():
        print("❌ 无缓存且 API 不可用")
        sys.exit(1)
    print(f"ℹ️  使用缓存: {cache}")

try:
    from src.data.external import download_fear_greed_index
    fgi = download_fear_greed_index(cache=True)
    print(f"✅ FGI: {len(fgi)} 行")
except Exception as e:
    print(f"⚠️  FGI: {e}（跳过）")
PYEOF

# ── Step 2: 模型推理 ───────────────────────────────────────────────────────
echo ""
echo "=== Step 2: ${MODEL_NAME} 推理 ==="

case "${STRATEGY_VARIANT}" in
    base)         SIGNAL_FLAGS="" ;;
    moderate)     SIGNAL_FLAGS="--take-profit" ;;
    conservative) SIGNAL_FLAGS="--take-profit --regime-switch" ;;
    *) echo "❌ 未知 STRATEGY_VARIANT: ${STRATEGY_VARIANT}"; exit 1 ;;
esac

# shellcheck disable=SC2086
"${VENV_PYTHON}" "${REPO_DIR}/scripts/live_signal.py" \
    --model "${MODEL_DIR}/model.joblib" \
    --config "${MODEL_DIR}/config.yaml" \
    --state "${STATE_FILE}" \
    ${SIGNAL_FLAGS}

# ── Step 3: 生成信号 JSON ─────────────────────────────────────────────────
echo ""
echo "=== Step 3: 生成信号 JSON ==="
"${VENV_PYTHON}" "${REPO_DIR}/scripts/build_signal_json.py" \
    --model-dir "${MODEL_DIR}" \
    --state-file "${STATE_FILE}" \
    --variant "${STRATEGY_VARIANT}" \
    --output-dir "${OUT_DIR}" || echo "⚠️  build_signal_json 失败，跳过"

# ── Step 4: LLM 分析（可选）──────────────────────────────────────────────
if [ -n "${GEMINI_API_KEY:-}" ]; then
    echo ""
    echo "=== Step 4: LLM 分析 ==="
    LATEST_SIGNAL=$(ls -t "${OUT_DIR}"/signal_*.json 2>/dev/null | head -1 || true)
    if [ -n "${LATEST_SIGNAL}" ]; then
        "${VENV_PYTHON}" "${REPO_DIR}/scripts/enrich_llm_analysis.py" "${LATEST_SIGNAL}" \
            || echo "⚠️  LLM 分析失败，跳过"
    fi
fi

# ── Step 5: 发送邮件 ───────────────────────────────────────────────────────
if [ -n "${SMTP_USER:-}" ] && [ -n "${SMTP_PASS:-}" ]; then
    echo ""
    echo "=== Step 5: 发送邮件 ==="
    LATEST_SIGNAL=$(ls -t "${OUT_DIR}"/signal_*.json 2>/dev/null | head -1 || true)
    if [ -n "${LATEST_SIGNAL}" ]; then
        "${VENV_PYTHON}" "${REPO_DIR}/scripts/send_signal_email.py" "${LATEST_SIGNAL}" \
            || echo "⚠️  邮件发送失败，跳过"
    fi
fi

echo ""
echo "=============================================="
echo "🎉 ${MODEL_NAME} 完成！— $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "  信号目录: ${OUT_DIR}"
echo "=============================================="
