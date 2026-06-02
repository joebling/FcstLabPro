#!/usr/bin/env bash
# =============================================================================
# ⛔️ DEPRECATED (2026-06-02) — Cloud Run 容器入口已完全停用, 勿运行!
#
# 现役生产链路 = VPS 无 Docker:
#     deploy/vps/run_daily_nodock.sh → scripts/run_production_pipeline.py
#     → live_signal.run_for_model() (variant flags 从 active.yaml 解析)
#
# 本脚本的 STRATEGY_VARIANT 环境变量是旧的多真相源做法。仅作历史备查。
# 详见 deploy/README.md
# =============================================================================
# =============================================================================
# FcstLabPro 通用 Cloud Run Job 入口脚本 (模型无关)
#
# 通过 MODEL_NAME 环境变量切换模型:
#   MODEL_NAME=e1-conservative  →  🛡️ 风控优先
#   MODEL_NAME=e8-touch         →  💰 收益优先
#
# 所有模型元信息从 manifest.json 读取，零硬编码。
# =============================================================================
set -euo pipefail

echo "=============================================="
echo "🔮 FcstLabPro Daily Signal — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=============================================="

# ── 环境变量 ──
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

MODEL_NAME="${MODEL_NAME:?ERROR: MODEL_NAME 未设置. 例: MODEL_NAME=e1-conservative}"
STRATEGY_VARIANT="${STRATEGY_VARIANT:-conservative}"
STATE_BUCKET="${STATE_BUCKET:-}"
OUT_DIR="${OUT_DIR:-/tmp/signals}"
MODEL_DIR="/app/models/production/${MODEL_NAME}"

mkdir -p "${OUT_DIR}" /tmp/state

# ── 验证模型目录 ──
for f in "${MODEL_DIR}/model.joblib" "${MODEL_DIR}/config.yaml" "${MODEL_DIR}/manifest.json"; do
    [ -f "$f" ] || { echo "❌ 缺少文件: $f"; exit 1; }
done

# ── 解析策略变体为 CLI 参数 ──
SIGNAL_FLAGS=""
case "${STRATEGY_VARIANT}" in
    base)         SIGNAL_FLAGS="" ;;
    moderate)     SIGNAL_FLAGS="--take-profit" ;;
    conservative) SIGNAL_FLAGS="--take-profit --regime-switch" ;;
    *) echo "❌ 未知 STRATEGY_VARIANT: ${STRATEGY_VARIANT}"; exit 1 ;;
esac

echo ""
echo "📊 配置:"
echo "  模型:     ${MODEL_NAME}"
echo "  变体:     ${STRATEGY_VARIANT}"
echo "  CLI:     ${SIGNAL_FLAGS}"
echo "  状态桶:   ${STATE_BUCKET:-未配置}"
echo ""

# ── Step 1: 下载最新数据 ──
echo "=== Step 1: 下载数据 ==="
python3 - << 'PYEOF'
import sys
sys.path.insert(0, '/app')
from pathlib import Path

Path("/app/data/raw").mkdir(parents=True, exist_ok=True)

try:
    from src.data.downloader import download_binance_klines
    print("📥 下载 Binance BTCUSDT 日线数据...")
    df = download_binance_klines(symbol="BTCUSDT", interval="1d", start="2020-01-01")
    data_path = Path("/app/data/raw/btc_binance_BTCUSDT_1d.csv")
    df.to_csv(data_path)
    print(f"✅ 数据已保存: {data_path}, {len(df)} 行")
except Exception as e:
    print(f"⚠️ Binance API 不可用: {e}")
    data_path = Path("/app/data/raw/btc_binance_BTCUSDT_1d.csv")
    if data_path.exists():
        print(f"ℹ️ 使用已有本地数据: {data_path}")
    else:
        print("❌ 无本地数据且 API 不可用，无法继续")
        sys.exit(1)

try:
    from src.data.external import download_fear_greed_index
    print("📥 下载 FGI 数据...")
    fgi = download_fear_greed_index(cache=True)
    print(f"✅ FGI: {len(fgi)} 行")
except Exception as e:
    print(f"⚠️ FGI 下载失败: {e} (将使用缓存)")
PYEOF
echo "✅ 数据准备完成"

# ── Step 2: 恢复持仓状态 (GCS) ──
STATE_FILE="/tmp/state/signal_state.json"
if [ -n "${STATE_BUCKET}" ]; then
    echo ""
    echo "=== Step 2: 恢复持仓状态 ==="
    python3 -c "
from google.cloud import storage
client = storage.Client()
bucket_name, prefix = '${STATE_BUCKET}'.replace('gs://', '').split('/', 1)
bucket = client.bucket(bucket_name)
blob = bucket.blob(prefix + '/signal_state.json')
if blob.exists():
    blob.download_to_filename('${STATE_FILE}')
    print('✅ 状态已恢复')
else:
    print('ℹ️ 无历史状态，初始化空仓位')
" 2>/dev/null || {
        echo "ℹ️ 无历史状态，初始化空仓位"
    }
fi

# ── Step 3: 运行推理 ──
echo ""
echo "=== Step 3: 运行 ${MODEL_NAME} 推理 ==="
python /app/scripts/live_signal.py \
    --model "${MODEL_DIR}/model.joblib" \
    --config "${MODEL_DIR}/config.yaml" \
    --state "${STATE_FILE}" \
    ${SIGNAL_FLAGS}

# ── Step 4: 保存持仓状态到 GCS ──
if [ -n "${STATE_BUCKET}" ] && [ -f "${STATE_FILE}" ]; then
    echo ""
    echo "=== Step 4: 上传持仓状态 ==="
    python3 -c "
from google.cloud import storage
client = storage.Client()
bucket_name, prefix = '${STATE_BUCKET}'.replace('gs://', '').split('/', 1)
bucket = client.bucket(bucket_name)
blob = bucket.blob(prefix + '/signal_state.json')
blob.upload_from_filename('${STATE_FILE}')
print('✅ 状态已保存')
"
fi

# ── Step 5: 生成信号 JSON (从 manifest.json 读取模型元信息) ──
echo ""
echo "=== Step 5: 生成信号 JSON ==="
python3 /app/scripts/build_signal_json.py \
    --model-dir "${MODEL_DIR}" \
    --state-file "${STATE_FILE}" \
    --variant "${STRATEGY_VARIANT}" \
    --output-dir "${OUT_DIR}"

# ── Step 6: LLM 分析 (可选) ──
if [ -n "${GEMINI_API_KEY:-}" ]; then
    echo ""
    echo "=== Step 6: LLM 分析 ==="
    LATEST_SIGNAL=$(ls -t /tmp/signals/signal_*.json 2>/dev/null | head -1)
    if [ -f "${LATEST_SIGNAL:-}" ]; then
        python3 /app/scripts/enrich_llm_analysis.py "${LATEST_SIGNAL}" || echo "⚠️ LLM 分析失败"
    fi
fi

# ── Step 7: 发送邮件 ──
if [ -n "${SMTP_USER:-}" ] && [ -n "${SMTP_PASS:-}" ]; then
    echo ""
    echo "=== Step 7: 发送邮件 ==="
    LATEST_SIGNAL=$(ls -t /tmp/signals/signal_*.json 2>/dev/null | head -1)
    if [ -f "${LATEST_SIGNAL:-}" ]; then
        python /app/scripts/send_signal_email.py "${LATEST_SIGNAL}" || echo "⚠️ 邮件发送失败"
    fi
fi

# ── Step 8: 上传信号到 GCS ──
if [ -n "${STATE_BUCKET}" ]; then
    echo ""
    echo "=== Step 8: 上传信号 ==="
    python3 -c "
from google.cloud import storage
import glob
client = storage.Client()
bucket_name, prefix = '${STATE_BUCKET}'.replace('gs://', '').split('/', 1)
bucket = client.bucket(bucket_name)
for f in glob.glob('/tmp/signals/signal_*.json'):
    blob = bucket.blob(prefix + '/signals/' + f.split('/')[-1])
    blob.upload_from_filename(f)
print('✅ 信号已上传')
" 2>/dev/null || true
fi

echo ""
echo "=============================================="
echo "🎉 ${MODEL_NAME} 完成！ — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=============================================="
