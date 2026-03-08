#!/usr/bin/env bash
# =============================================================================
# FcstLabPro v0305 E1 Cloud Run Job 入口脚本
#
# 策略: directional_filtered (decontaminated)
#   - Label: 跌后反弹 (RSI<45 & <SMA50 → 21天内 ≥4%)
#   - 变体: 基础/+止盈/+止盈+regime (由环境变量控制)
#   - 模型: 单个 LightGBM (129 特征, 无污染)
#   - 状态: GCS 持久化持仓状态
# =============================================================================
set -euo pipefail

echo "=============================================="
echo "🔮 FcstLabPro v0305 E1 Daily Signal — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=============================================="

# ── 环境变量 (由 Cloud Run --set-env-vars 传入) ──
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

# 策略配置
STRATEGY_VARIANT="${STRATEGY_VARIANT:-conservative}"   # base | moderate | conservative
STATE_BUCKET="${STATE_BUCKET:-}"                        # gs://bucket/path (GCS 状态持久化)
OUT_DIR="${OUT_DIR:-/tmp/signals}"
MODEL_VERSION="v0305-E1"

mkdir -p "${OUT_DIR}" /tmp/state

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
echo "  策略变体: ${STRATEGY_VARIANT}"
echo "  CLI 参数: ${SIGNAL_FLAGS}"
echo "  状态桶:   ${STATE_BUCKET:-未配置 (无持久化)}"
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

# 下载外部数据 (FGI 等)
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
    gsutil cp "${STATE_BUCKET}/signal_state.json" "${STATE_FILE}" 2>/dev/null || {
        echo "ℹ️ 无历史状态，初始化空仓位"
    }
fi

# ── Step 3: 运行推理 ──
echo ""
echo "=== Step 3: 运行 E1 推理 ==="
python /app/scripts/live_signal.py \
    --state "${STATE_FILE}" \
    ${SIGNAL_FLAGS}

# ── Step 4: 保存持仓状态到 GCS ──
if [ -n "${STATE_BUCKET}" ] && [ -f "${STATE_FILE}" ]; then
    echo ""
    echo "=== Step 4: 上传持仓状态 ==="
    gsutil cp "${STATE_FILE}" "${STATE_BUCKET}/signal_state.json"
    echo "✅ 状态已保存: ${STATE_BUCKET}/signal_state.json"
fi

# ── Step 5: 生成信号 JSON (邮件用) ──
echo ""
echo "=== Step 5: 生成信号 JSON ==="
python3 - << PYEOF
import json, sys
from pathlib import Path
from datetime import datetime

state_file = Path("${STATE_FILE}")
if not state_file.exists():
    print("⚠️ 状态文件不存在，跳过 JSON 生成")
    sys.exit(0)

with open(state_file) as f:
    state = json.load(f)

# 读取最新价格
import pandas as pd
df = pd.read_csv("/app/data/raw/btc_binance_BTCUSDT_1d.csv", index_col=0)
df = df.sort_index()
price = float(df["close"].iloc[-1])
date_str = state.get("last_signal_date", datetime.utcnow().strftime("%Y-%m-%d"))

signal = state.get("last_signal", "SILENT")
signal_display = {
    "BUY":    "🟢 买入 (E1 v0305)",
    "HOLD":   "🟡 持有中",
    "SELL":   "🔴 卖出",
    "SILENT": "⚪ 静默 (无信号)",
}.get(signal, signal)

# PnL 信息
pnl_info = ""
if state.get("in_position") and state.get("entry_price"):
    pnl = (price - state["entry_price"]) / state["entry_price"]
    pnl_info = f"浮盈 {pnl:+.2%}, 买入于 {state['entry_date']} @ \${state['entry_price']:,.0f}"

# 历史胜率
history = state.get("history", [])
if history:
    wins = sum(1 for t in history if t.get("pnl", 0) > 0)
    total = len(history)
    win_rate = wins / total
    avg_pnl = sum(t.get("pnl", 0) for t in history) / total
    hist_info = f"已完成 {total} 笔, 胜率 {win_rate:.0%}, 均盈 {avg_pnl:+.2%}"
else:
    hist_info = "尚无历史交易"

signal_data = {
    "date": date_str,
    "price": price,
    "signal": signal,
    "signal_display": signal_display,
    "action": pnl_info or "无操作",
    "position_pct": 100 if state.get("in_position") else 0,
    "risk_level": "中",
    "risk_notes": [
        f"ℹ️ 策略变体: ${STRATEGY_VARIANT}",
        f"📊 {hist_info}",
        "📊 E1 回测 Kappa=0.19, PF=1.32, MaxDD=-12.7% (保守版)",
    ],
    "model_version": {"e1": "weekly_bear_v0305_E1_decontam"},
    "kappa": {"e1": "0.19"},
    "label_strategy": {"e1": "directional_filtered (decontaminated)"},
    "feature_set": {"e1": ["technical", "volume", "flow", "market_structure", "external_fgi"]},
    "strategy_version": {"e1": "${MODEL_VERSION}"},
    "bull_prob": 0.0,
    "bear_prob": 0.0,
    "llm_analysis": None,
    "version": "${MODEL_VERSION}",
}

out_path = Path("/tmp/signals/signal_{}.json".format(date_str))
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w") as f:
    json.dump(signal_data, f, indent=2, ensure_ascii=False)
print(f"✅ 信号 JSON: {out_path}")
print(f"   {signal_display} | \${price:,.2f} | {pnl_info or '无持仓'}")
PYEOF

# ── Step 6: LLM 分析 (可选) ──
if [ -n "${GEMINI_API_KEY:-}" ]; then
    echo ""
    echo "=== Step 6: LLM 分析 ==="
    LATEST_SIGNAL=$(ls -t /tmp/signals/signal_*.json 2>/dev/null | head -1)
    if [ -f "${LATEST_SIGNAL:-}" ]; then
        python3 - "${LATEST_SIGNAL}" << 'PYEOF' || echo "⚠️ LLM 分析失败"
import sys, json
from pathlib import Path
sys.path.insert(0, '/app')

signal_path = sys.argv[1]
with open(signal_path) as f:
    data = json.load(f)

try:
    from src.llm.analyst import generate_analysis
    import pandas as pd
    df = pd.read_csv("/app/data/raw/btc_binance_BTCUSDT_1d.csv", index_col=0).sort_index()
    recent = df.tail(7)
    klines = [{"date": str(idx)[:10], "close": float(r["close"]),
               "volume": float(r["volume"])} for idx, r in recent.iterrows()]
    analysis = generate_analysis(data, klines, {})
    if analysis:
        data["llm_analysis"] = analysis
        with open(signal_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ LLM 分析已添加")
except Exception as e:
    print(f"⚠️ LLM 分析出错: {e}")
PYEOF
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
    gsutil -m cp /tmp/signals/signal_*.json "${STATE_BUCKET}/signals/" 2>/dev/null || true
    echo "✅ 信号已上传"
fi

echo ""
echo "=============================================="
echo "🎉 v0305 E1 完成！ — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=============================================="
