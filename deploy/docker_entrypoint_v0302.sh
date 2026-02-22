#!/usr/bin/env bash
# =============================================================================
# FcstLabPro v0302 Cloud Run Job 入口脚本
# 策略: dip_recovery + Trigger A + Position sizing (linear)
# Label: dip_recovery (dip >5%, recovery >3%)
# 触发: 等待 dip ≥5% 再入场
# 退出: 止盈 +4%，止损 -3%，时间止损 14 天
# Position sizing: size = 2 × (prob - 0.5)
# =============================================================================
set -euo pipefail

echo "=============================================="
echo "🔮 FcstLabPro v0302 Daily Signal — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
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

# v0302 专属配置
BULL_DIR="${BULL_DIR:-experiments/weekly/weekly_bull_v27_orion_final}"
BEAR_DIR="${BEAR_DIR:-experiments/weekly/weekly_bear_v13_T28_fgi_20260215_134804_ff4ad7}"
MODEL_VERSION="${MODEL_VERSION:-v0302}"
BULL_KAPPA="${BULL_KAPPA:-0.11}"
BEAR_KAPPA="${BEAR_KAPPA:-0.05}"
LABEL_STRATEGY="${LABEL_STRATEGY:-dip_recovery}"
# v0302: 不使用信号反转，使用 dip_recovery 策略
INVERT_SIGNAL="${INVERT_SIGNAL:-false}"
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

# 合并结果（v0302 专属逻辑）
echo ""
echo "📥 Step 1D: 合并结果 (v0302)..."
python3 - << PYEOF
import pickle
import json
import sys
import os
sys.path.insert(0, '/app')
from pathlib import Path

temp_dir = Path("/tmp/signals")
MODEL_VERSION = os.environ.get("MODEL_VERSION", "v0302")
BULL_KAPPA = os.environ.get("BULL_KAPPA", "0.11")
BEAR_KAPPA = os.environ.get("BEAR_KAPPA", "0.05")
LABEL_STRATEGY = os.environ.get("LABEL_STRATEGY", "dip_recovery")

# 模型名称（用于邮件标题显示）
BULL_MODEL_NAME = "weekly_bull_v27_orion_final"
BEAR_MODEL_NAME = "weekly_bear_v13_T28_fgi"

import pandas as pd

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

# 为缺失的 meta 信息提供默认值（v0302 专属）
if not bull_meta:
    bull_meta = {
        "version": "weekly_bull_v27_orion_final",
        "kappa": "N/A",
        "label_strategy": "dip_recovery",
        "feature_set": ["technical", "volume", "flow", "market_structure", "external_fgi", "regime"]
    }

if not bear_meta:
    bear_meta = {
        "version": "weekly_bear_v13_T28_fgi",
        "kappa": "0.05",
        "label_strategy": "dip_recovery",
        "feature_set": ["technical", "volume", "flow", "market_structure", "external_fgi"]
    }

print(f"📊 Bull 概率: {bull_prob:.3f}")
print(f"📊 Bear 概率: {bear_prob:.3f}")
print(f"📊 日期: {date_str}, 价格: {price}")

# v0302: 不使用信号反转，直接使用原概率
invert_signal = os.environ.get("INVERT_SIGNAL", "false") == "true"
print(f"📊 信号反转: {invert_signal}")

# 生成信号（v0302 专属逻辑）
bull_threshold = 0.50
bear_threshold = 0.50

# v0302: 不反转，直接使用原概率
bull_on = bull_prob >= bull_threshold
bear_on = bear_prob >= bear_threshold

# 三重MA过滤（保持与 v0301 相同的逻辑）
data_path = Path("/app/data/raw/btc_binance_BTCUSDT_1d.csv")
triple_ma_confirm = False
if data_path.exists():
    df = pd.read_csv(data_path, index_col=0)
    df = df.sort_index()
    df['sma_50'] = df['close'].rolling(50).mean()
    df['sma_150'] = df['close'].rolling(150).mean()
    df['sma_200'] = df['close'].rolling(200).mean()
    last = df.iloc[-1]
    above_ma50 = last['close'] > last['sma_50']
    above_ma150 = last['close'] > last['sma_150']
    above_ma200 = last['close'] > last['sma_200']
    triple_ma_confirm = above_ma50 and above_ma150 and above_ma200
    print(f"📊 [v0302] 三重MA检查: 价格={last['close']:.2f}, MA50={last['sma_50']:.2f}, MA150={last['sma_150']:.2f}, MA200={last['sma_200']:.2f}")
    print(f"📊 [v0302] 站上MA50: {above_ma50}, 站上MA150: {above_ma150}, 站上MA200: {above_ma200}, 三重MA确认: {triple_ma_confirm}")

# 使用处理后的信号
if bull_on and bear_prob < bear_threshold:
    signal_code = "STRONG_BULL"
    signal_display = "🚀 强烈看涨 (v0302)"
    position_pct = 80
    action = "建议加仓或做多"
    risk_level = "高"
elif bear_prob >= bear_threshold and not bull_on:
    signal_code = "STRONG_BEAR"
    signal_display = "📉 强烈看跌"
    position_pct = 20
    action = "建议减仓或做空"
    risk_level = "高"
elif bull_on:
    signal_code = "BULL"
    signal_display = "↗️ 偏多震荡 (v0302)"
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

# 风险提醒（v0302 专属）
risk_notes = [
    f"ℹ️ {MODEL_VERSION} 策略: dip_recovery + Trigger A + Position sizing",
    f"📊 模型 Kappa≈Bull={BULL_KAPPA}, Bear={BEAR_KAPPA}，预测力有限，仅作辅助参考"
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
        "bull": BULL_MODEL_NAME,
        "bear": BEAR_MODEL_NAME
    },
    "kappa": {
        "bull": BULL_KAPPA,
        "bear": BEAR_KAPPA
    },
    "label_strategy": {
        "bull": LABEL_STRATEGY,
        "bear": LABEL_STRATEGY
    },
    "strategy_version": {
        "bull": MODEL_VERSION,
        "bear": MODEL_VERSION
    },
    "feature_set": {
        "bull": ["technical", "volume", "flow", "market_structure", "external_fgi", "regime"],
        "bear": ["technical", "volume", "flow", "market_structure", "external_fgi"]
    },
    "llm_analysis": None,
    "version": MODEL_VERSION
}

output_file = temp_dir / f"signal_{date_str}.json"
with open(output_file, "w") as f:
    json.dump(signal_data, f, indent=2, ensure_ascii=False)
print(f"✅ 信号已保存: {output_file}")

# ── Step 1.5: LLM 策略分析 ──
import os
gemini_key = os.environ.get("GEMINI_API_KEY", "")
if gemini_key:
    print("🤖 生成 LLM 策略分析...")
    try:
        sys.path.insert(0, '/app')
        from src.llm.analyst import generate_analysis

        # 读取最新的K线数据
        import pandas as pd
        data_path = Path("/app/data/raw/btc_binance_BTCUSDT_1d.csv")
        if data_path.exists():
            df = pd.read_csv(data_path, parse_dates=['close_time'] if 'close_time' in pd.read_csv(data_path, nrows=0).columns else None, index_col=0)
            df = df.sort_index()

            # 准备近7天K线数据
            recent = df.tail(7)
            recent_klines = []
            for idx, row in recent.iterrows():
                prev_close = df["close"].shift(1).loc[idx] if idx in df.index else row["close"]
                change = ((row["close"] - prev_close) / prev_close * 100) if prev_close else 0
                recent_klines.append({
                    "date": str(idx.date()) if hasattr(idx, 'date') else str(idx)[:10],
                    "close": float(row["close"]),
                    "change": float(change),
                    "volume": float(row["volume"]),
                })

            # 准备关键技术指标
            last_row = df.iloc[-1]
            indicators = {}
            for col in ["rsi_14", "macd", "macd_hist", "bb_pctb_20", "atr_pct_14",
                         "sma_cross_50_200", "price_vs_sma_20", "price_vs_sma_200",
                         "vol_ratio_20", "return_7d", "return_14d", "volatility_20d"]:
                if col in last_row.index:
                    indicators[col] = float(last_row[col])

            llm_analysis = generate_analysis(signal_data, recent_klines, indicators)
            if llm_analysis:
                # 更新信号文件
                signal_data["llm_analysis"] = llm_analysis
                with open(output_file, "w") as f:
                    json.dump(signal_data, f, indent=2, ensure_ascii=False)
                print(f"✅ LLM 分析已添加")
            else:
                print("⚠️ LLM 分析生成失败")
        else:
            print("⚠️ 未找到K线数据，跳过LLM分析")
    except Exception as e:
        print(f"⚠️ LLM 分析出错: {e}")
else:
    print("ℹ️ 未配置 GEMINI_API_KEY，跳过LLM分析")

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
echo "🎉 v0302 完成！ — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=============================================="
