#!/usr/bin/env bash
# =============================================================================
# FcstLabPro VPS 每日信号运行脚本（无 Docker）
#
# 支持单模型或多模型串行：
#   MODEL_NAME=e1-conservative
#   MODEL_NAMES=e1-conservative,e8-touch
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_DIR="/opt/fcstlabpro"
VENV_PYTHON="${REPO_DIR}/.venv/bin/python"
ENV_FILE="${DATA_DIR}/.env"
STATE_DIR="${DATA_DIR}/state"
SIGNALS_DIR="${DATA_DIR}/signals"

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

export REPO_DIR
export PYTHONPATH="${REPO_DIR}:${PYTHONPATH:-}"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

STRATEGY_VARIANT="${STRATEGY_VARIANT:-conservative}"
MODEL_LIST="${MODEL_NAMES:-${MODEL_NAME:-e1-conservative}}"

mkdir -p "${STATE_DIR}" "${SIGNALS_DIR}"

echo ""
echo "📊 配置:"
echo "  模型队列: ${MODEL_LIST}"
echo "  变体:     ${STRATEGY_VARIANT}"
echo ""

# ── Step 1: 下载数据（所有模型共享，一天只下它一次，别当流量刺客）──────────────
echo "=== Step 1: 下载数据 ==="
"${VENV_PYTHON}" - << 'PYEOF'
import os
import sys
from pathlib import Path

repo_dir = Path(os.environ.get("REPO_DIR", "."))
sys.path.insert(0, str(repo_dir))

try:
    from src.data.downloader import download_binance_klines
    print("📥 下载 Binance BTCUSDT 日线...")
    df = download_binance_klines(symbol="BTCUSDT", interval="1d", start="2020-01-01")
    out = repo_dir / "data/raw/btc_binance_BTCUSDT_1d.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out)
    print(f"✅ 已保存: {out} ({len(df)} 行)")
except Exception as e:
    print(f"⚠️  Binance API: {e}，尝试使用本地缓存...")
    cache = repo_dir / "data/raw/btc_binance_BTCUSDT_1d.csv"
    if not cache.exists():
        print("❌ 无缓存且 API 不可用")
        sys.exit(1)
    print(f"ℹ️  使用缓存: {cache}")

try:
    from src.data.external import download_fear_greed_index
    # cache=False: 强制刷新, 不吃 12h 缓存 (防止用旧 FGI 蒙混过 freshness gate)
    fgi = download_fear_greed_index(cache=False)
    print(f"✅ FGI: {len(fgi)} 行")
except Exception as e:
    # 决策 A: FGI 不能静默跳过。下载彻底失败且无缓存 → 后续 freshness gate 会 fatal。
    print(f"⚠️  FGI 下载异常: {e}（交由 Step 1.5 校验判定）")
PYEOF

# ── Step 1.5: 数据新鲜度强校验 (决策 A — 缺失/过期一律 fatal)─────────────
echo ""
echo "=== Step 1.5: 数据新鲜度校验 (决策 A) ==="
"${VENV_PYTHON}" - << 'PYEOF'
import os
import sys
sys.path.insert(0, os.environ["REPO_DIR"])
from src.serving.data_freshness import check_all, DataFreshnessError
try:
    for r in check_all(require_fgi=True):
        print(f"✅ {r.source}: stale={r.stale_days}d / SLA={r.sla_days}d ({r.end})")
except DataFreshnessError as e:
    print(f"❌ 数据校验失败 (决策 A, 拒绝出信号): {e}")
    sys.exit(1)
PYEOF

signal_flags_for_variant() {
    case "${STRATEGY_VARIANT}" in
        base)         echo "" ;;
        moderate)     echo "--take-profit" ;;
        conservative) echo "--take-profit --regime-switch" ;;
        *) echo "❌ 未知 STRATEGY_VARIANT: ${STRATEGY_VARIANT}" >&2; return 1 ;;
    esac
}

run_model() {
    local model_name="$1"
    local model_dir="${REPO_DIR}/models/production/${model_name}"
    local state_file="${STATE_DIR}/${model_name}_state.json"
    local out_dir="${SIGNALS_DIR}/${model_name}"
    local latest_signal=""
    local signal_flags=""

    signal_flags="$(signal_flags_for_variant)"
    mkdir -p "${out_dir}"

    echo ""
    echo "=============================================="
    echo "🚀 开始模型: ${model_name}"
    echo "  状态文件: ${state_file}"
    echo "  信号目录: ${out_dir}"
    echo "=============================================="

    for f in "${model_dir}/model.joblib" "${model_dir}/config.yaml" "${model_dir}/manifest.json"; do
        if [ ! -f "$f" ]; then
            echo "❌ 缺少模型文件: $f"
            return 1
        fi
    done

    echo ""
    echo "=== ${model_name}: 推理 ==="
    # shellcheck disable=SC2086
    "${VENV_PYTHON}" "${REPO_DIR}/scripts/live_signal.py" \
        --model "${model_dir}/model.joblib" \
        --config "${model_dir}/config.yaml" \
        --state "${state_file}" \
        ${signal_flags}

    echo ""
    echo "=== ${model_name}: 生成信号 JSON ==="
    "${VENV_PYTHON}" "${REPO_DIR}/scripts/build_signal_json.py" \
        --model-dir "${model_dir}" \
        --state-file "${state_file}" \
        --variant "${STRATEGY_VARIANT}" \
        --output-dir "${out_dir}" || echo "⚠️  ${model_name}: build_signal_json 失败，跳过"

    latest_signal=$(ls -t "${out_dir}"/signal_*.json 2>/dev/null | head -1 || true)

    if [ -n "${GEMINI_API_KEY:-}" ] && [ -n "${latest_signal}" ]; then
        echo ""
        echo "=== ${model_name}: LLM 分析 ==="
        "${VENV_PYTHON}" "${REPO_DIR}/scripts/enrich_llm_analysis.py" "${latest_signal}" \
            || echo "⚠️  ${model_name}: LLM 分析失败，跳过"
    fi

    if [ -n "${SMTP_USER:-}" ] && [ -n "${SMTP_PASS:-}" ] && [ -n "${latest_signal}" ]; then
        echo ""
        echo "=== ${model_name}: 发送邮件 ==="
        "${VENV_PYTHON}" "${REPO_DIR}/scripts/send_signal_email.py" "${latest_signal}" \
            || echo "⚠️  ${model_name}: 邮件发送失败，跳过"
    fi

    echo "✅ ${model_name} 完成"
}

# 逗号分隔模型列表，串行执行。
IFS=',' read -ra MODELS <<< "${MODEL_LIST}"
for raw_model in "${MODELS[@]}"; do
    model="$(echo "${raw_model}" | xargs)"
    [ -n "${model}" ] || continue
    run_model "${model}"
done

echo ""
echo "=============================================="
echo "🎉 全部模型完成！— $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "  信号根目录: ${SIGNALS_DIR}"
echo "=============================================="
