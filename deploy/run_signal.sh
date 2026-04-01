#!/bin/bash
# FcstLabPro 信号生成 + 邮件发送自动化脚本 (双模型版本)

cd /Users/qiubling/Desktop/projects/FcstLabPro

# 配置: 两个模型
MODELS=("e1-conservative" "e8-touch")
STRATEGY_VARIANTS=("conservative" "conservative")

OUT_DIR="/tmp/signals"

# 1. 下载最新数据 (只需一次)
echo "=== 1. 下载数据 ==="
/Users/qiubling/Desktop/projects/FcstLabPro/venv_py310/bin/python -c "
import sys
sys.path.insert(0, '/Users/qiubling/Desktop/projects/FcstLabPro')
from src.data.downloader import download_binance_klines
from pathlib import Path

Path('/Users/qiubling/Desktop/projects/FcstLabPro/data/raw').mkdir(parents=True, exist_ok=True)
df = download_binance_klines(symbol='BTCUSDT', interval='1d', start='2020-01-01')
df.to_csv('/Users/qiubling/Desktop/projects/FcstLabPro/data/raw/btc_binance_BTCUSDT_1d.csv', index=True)
print(f'数据已更新: {len(df)} 行')
"

# 2. 依次运行每个模型
for i in "${!MODELS[@]}"; do
    MODEL_NAME="${MODELS[$i]}"
    STRATEGY_VARIANT="${STRATEGY_VARIANTS[$i]}"
    MODEL_DIR="/Users/qiubling/Desktop/projects/FcstLabPro/models/production/${MODEL_NAME}"
    STATE_FILE="/tmp/signal_state_${MODEL_NAME}.json"

    echo ""
    echo "=== 运行模型: ${MODEL_NAME} ==="

    # 构建 SIGNAL_FLAGS
    case "${STRATEGY_VARIANT}" in
        base)         SIGNAL_FLAGS="" ;;
        moderate)     SIGNAL_FLAGS="--take-profit" ;;
        conservative) SIGNAL_FLAGS="--take-profit --regime-switch" ;;
        *) echo "❌ 未知 STRATEGY_VARIANT: ${STRATEGY_VARIANT}"; exit 1 ;;
    esac

    # 运行推理
    /Users/qiubling/Desktop/projects/FcstLabPro/venv_py310/bin/python /Users/qiubling/Desktop/projects/FcstLabPro/scripts/live_signal.py \
        --model "${MODEL_DIR}/model.joblib" \
        --config "${MODEL_DIR}/config.yaml" \
        --state "${STATE_FILE}" \
        ${SIGNAL_FLAGS}

    # 生成信号 JSON
    /Users/qiubling/Desktop/projects/FcstLabPro/venv_py310/bin/python /Users/qiubling/Desktop/projects/FcstLabPro/scripts/build_signal_json.py \
        --model-dir "${MODEL_DIR}" \
        --state-file "${STATE_FILE}" \
        --variant "${STRATEGY_VARIANT}" \
        --output-dir "${OUT_DIR}"

    # 发送邮件
    SIGNAL_FILE=$(ls -t ${OUT_DIR}/signal_*.json 2>/dev/null | head -1)
    if [ -n "$SIGNAL_FILE" ]; then
        echo "发送邮件: $SIGNAL_FILE"
        /Users/qiubling/Desktop/projects/FcstLabPro/venv_py310/bin/python /Users/qiubling/Desktop/projects/FcstLabPro/scripts/send_signal_email.py "$SIGNAL_FILE"
    fi
done

echo ""
echo "✅ 全部完成"