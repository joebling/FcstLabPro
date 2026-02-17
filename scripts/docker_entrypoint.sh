#!/usr/bin/env bash
# =============================================================================
# FcstLabPro v0215 Cloud Run Job 入口脚本
# Bull: Orion-BiX (T=21, Kappa=0.1122)
# Bear: LightGBM v13 (T=28, Kappa=0.0529)
# 功能: 1) 下载最新 Binance 日线数据  2) 生成每日交易信号  3) 上传结果到 GCS
# =============================================================================
set -euo pipefail

echo "=============================================="
echo "🔮 FcstLabPro v0215 Daily Signal — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=============================================="

# ── 环境变量（Cloud Run Job 通过 --set-env-vars 传入） ──
# 强制 PyTorch 使用 CPU（减少内存占用）
export CUDA_VISIBLE_DEVICES=""
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
# 限制 PyTorch 内存分配（减少碎片）
export PYTORCH_CUDA_ALLOC_CONF="max_split_size_mb:64"
# 减少 glibc 内存碎片
export MALLOC_TRIM_THRESHOLD_=-1
export MALLOC_ARENA_MAX=2
# 禁用 PyTorch 缓存分配器（在 CPU-only 环境下减少内存开销）
export PYTORCH_NO_CUDA_MEMORY_CACHING=1

BULL_DIR="${BULL_DIR:-experiments/weekly/weekly_bull_v27_orion_final}"
BEAR_DIR="${BEAR_DIR:-experiments/weekly/weekly_bear_v13_T28_fgi_20260215_134804_ff4ad7}"
OUT_DIR="${OUT_DIR:-/tmp/signals}"
OUT_BUCKET="${OUT_BUCKET:-}"           # gs://your-bucket/signals（可选）
NOTIFICATION_URL="${NOTIFICATION_URL:-}"  # Webhook URL（可选）

mkdir -p "${OUT_DIR}"
TEMP_DIR="${OUT_DIR}"

# ── 先下载数据，避免后续进程找不到数据 ──
echo ""
echo "📥 先下载最新日线数据..."
python3 - << 'PYEOF'
import sys
sys.path.insert(0, '/app')
from src.data.downloader import download_binance_klines
from pathlib import Path

# 创建数据目录
Path("/app/data/raw").mkdir(parents=True, exist_ok=True)

# 下载数据
print("📥 下载 Binance BTCUSDT 日线数据...")
df = download_binance_klines(
    symbol="BTCUSDT",
    interval="1d",
    start="2020-01-01",
)
data_path = Path("/app/data/raw/btc_binance_BTCUSDT_1d.csv")
df.to_csv(data_path)
print(f"✅ 数据已保存到: {data_path}")
PYEOF
echo "✅ 数据下载完成"

# ── 进程级隔离：内存优化 ──
echo ""
echo "🔄 进程级隔离模式：内存优化"

# 进程A: Bull 特征计算 + 推理（完成后进程退出，释放内存）
echo ""
echo "📥 Step 1A: Bull 特征计算 + 推理 (Orion-BiX)..."
python /app/scripts/weekly_signal.py \
    --mode bull-infer \
    --download \
    --bull-dir "${BULL_DIR}" \
    --temp-dir "${TEMP_DIR}"

# 进程B: Bear 特征计算 + 推理（完成后进程退出，释放内存）
echo ""
echo "📥 Step 1B: Bear 特征计算 + 推理 (LightGBM)..."
python /app/scripts/weekly_signal.py \
    --mode bear-infer \
    --download \
    --bear-dir "${BEAR_DIR}" \
    --temp-dir "${TEMP_DIR}"

# 合并结果
echo ""
echo "📥 Step 1D: 合并结果..."
python3 - << 'PYEOF'
import pickle
import json
from pathlib import Path

temp_dir = Path("/tmp/signals")

# 读取 Bull 结果
with open(temp_dir / "bull_result.pkl", "rb") as f:
    bull = pickle.load(f)

# 读取 Bear 结果
with open(temp_dir / "bear_result.pkl", "rb") as f:
    bear = pickle.load(f)

bull_prob = bull["bull_prob"]
bear_prob = bear["bear_prob"]
date_str = bull["date"]
price = bull["price"]
bull_meta = bull.get("meta", {})
bear_meta = bear.get("meta", {})

print(f"📊 Bull 概率: {bull_prob:.3f}")
print(f"📊 Bear 概率: {bear_prob:.3f}")
print(f"📊 日期: {date_str}, 价格: {price}")

# 生成信号
bull_threshold = 0.50
bear_threshold = 0.50

if bull_prob >= bull_threshold and bear_prob < bear_threshold:
    signal_code = "STRONG_BULL"
    signal_display = "🚀 强烈看涨"
    position_pct = 80
    action = "建议加仓或做多"
    risk_level = "高"
elif bear_prob >= bear_threshold and bull_prob < bull_threshold:
    signal_code = "STRONG_BEAR"
    signal_display = "📉 强烈看跌"
    position_pct = 20
    action = "建议减仓或做空"
    risk_level = "高"
elif bull_prob > bear_prob:
    signal_code = "BULL"
    signal_display = "↗️ 偏多震荡"
    position_pct = 60
    action = "持有观望，可小仓位做多"
    risk_level = "中"
elif bear_prob > bull_prob:
    signal_code = "BEAR"
    signal_display = "↘️ 偏空震荡"
    position_pct = 40
    action = "持有观望，可小仓位做空"
    risk_level = "中"
else:
    signal_code = "NEUTRAL"
    signal_display = "⏸️ 震荡"
    position_pct = 50
    action = "维持当前仓位，无需操作"
    risk_level = "低"

# 风险提醒
risk_notes = [
    "ℹ️ 两个方向的信号均较弱，模型信心不足",
    f"📊 模型 Kappa≈Bull={bull_meta.get('kappa','N/A')}, Bear={bear_meta.get('kappa','N/A')}，预测力有限，仅作辅助参考"
]

# 保存信号
signal_data = {
    "date": date_str,
    "price": price,
    "signal": signal_code,
    "signal_display": signal_display,
    "bull_prob": bull_prob,
    "bear_prob": bear_prob,
    "position_pct": position_pct,
    "action": action,
    "risk_level": risk_level,
    "risk_notes": risk_notes,
    "model_version": {
        "bull": bull_meta.get("version", "N/A"),
        "bear": bear_meta.get("version", "N/A")
    },
    "kappa": {
        "bull": bull_meta.get("kappa", "N/A"),
        "bear": bear_meta.get("kappa", "N/A")
    },
    "label_strategy": {
        "bull": bull_meta.get("label_strategy", "N/A"),
        "bear": bear_meta.get("label_strategy", "N/A")
    },
    "feature_set": {
        "bull": bull_meta.get("feature_set", []),
        "bear": bear_meta.get("feature_set", [])
    },
    "llm_analysis": None,
    "version": "v0215-subprocess"
}

output_file = temp_dir / f"signal_{date_str}.json"
with open(output_file, "w") as f:
    json.dump(signal_data, f, indent=2, ensure_ascii=False)
print(f"✅ 信号已保存: {output_file}")
PYEOF

# 移动信号文件
cp -f /tmp/signals/signal_*.json "${OUT_DIR}/" 2>/dev/null || true

# 移动信号文件到输出目录
cp -f /app/signals/signal_*.json "${OUT_DIR}/" 2>/dev/null || true

echo ""
echo "📄 输出文件:"
ls -la "${OUT_DIR}/"

# ── Step 2: 上传到 GCS（如果配置了 OUT_BUCKET） ──
if [ -n "${OUT_BUCKET}" ]; then
    echo ""
    echo "☁️ Step 2: 上传到 GCS: ${OUT_BUCKET}"
    gsutil -m cp "${OUT_DIR}"/signal_*.json "${OUT_BUCKET%/}/" || true
    echo "✅ 上传完成"
fi

# ── Step 3: 发送通知（如果配置了 Webhook） ──
if [ -n "${NOTIFICATION_URL}" ]; then
    echo ""
    echo "📨 Step 3: 发送 Webhook 通知..."
    LATEST_SIGNAL=$(ls -t "${OUT_DIR}"/signal_*.json | head -1)
    if [ -f "${LATEST_SIGNAL}" ]; then
        curl -s -X POST "${NOTIFICATION_URL}" \
            -H "Content-Type: application/json" \
            -d @"${LATEST_SIGNAL}" || echo "⚠️ Webhook 通知发送失败"
        echo "✅ Webhook 通知已发送"
    fi
fi

# ── Step 4: 发送邮件（如果配置了 SMTP_USER） ──
if [ -n "${SMTP_USER:-}" ] && [ -n "${SMTP_PASS:-}" ]; then
    echo ""
    echo "📧 Step 4: 发送邮件通知..."
    LATEST_SIGNAL=$(ls -t "${OUT_DIR}"/signal_*.json | head -1)
    if [ -f "${LATEST_SIGNAL}" ]; then
        python /app/scripts/send_signal_email.py "${LATEST_SIGNAL}" || echo "⚠️ 邮件发送失败"
    fi
fi

echo ""
echo "=============================================="
echo "🎉 完成！ — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=============================================="
