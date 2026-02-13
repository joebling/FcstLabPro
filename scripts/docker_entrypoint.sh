#!/usr/bin/env bash
# =============================================================================
# FcstLabPro v6 Cloud Run Job 入口脚本
# 功能: 1) 下载最新 Binance 日线数据  2) 生成每日交易信号  3) 上传结果到 GCS
# =============================================================================
set -euo pipefail

echo "=============================================="
echo "🔮 FcstLabPro v6 Daily Signal — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=============================================="

# ── 环境变量（Cloud Run Job 通过 --set-env-vars 传入） ──
BULL_DIR="${BULL_DIR:-experiments/weekly/weekly_bull_v6_20260213_214847_a29943}"
BEAR_DIR="${BEAR_DIR:-experiments/weekly/weekly_bear_v6_20260213_215211_1928bd}"
OUT_DIR="${OUT_DIR:-/tmp/signals}"
OUT_BUCKET="${OUT_BUCKET:-}"           # gs://your-bucket/signals（可选）
NOTIFICATION_URL="${NOTIFICATION_URL:-}"  # Webhook URL（可选）

mkdir -p "${OUT_DIR}"

# ── Step 1: 下载最新数据 + 生成信号 ──
echo ""
echo "📥 Step 1: 下载最新数据并生成信号..."
python /app/scripts/weekly_signal.py \
    --download \
    --bull-dir "${BULL_DIR}" \
    --bear-dir "${BEAR_DIR}" \
    --save

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
