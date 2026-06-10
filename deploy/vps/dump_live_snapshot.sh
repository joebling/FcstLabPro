#!/usr/bin/env bash
# dump_live_snapshot.sh - VPS 上抓 live state + ohlcv 到 git-tracked snapshot
#
# 用途: dashboard 双 check / 事故复盘 / 30 天回放, 需要本地能看到 VPS 的实盘账本.
# 设计原则 (lesson_0602 兼容): 不动 data/raw/ 训练基准, 也不动 data/live/ (gitignored),
# 只往 data/snapshots/ 这个独立目录写日期戳文件, 完全不打破现有路径隔离.
#
# 用法 (VPS 上):
#   bash deploy/vps/dump_live_snapshot.sh           # 抓当日快照
#   bash deploy/vps/dump_live_snapshot.sh --commit  # 抓 + git commit + push
#
# 输出 (data/snapshots/ 下):
#   btc_live_<UTC日期>.csv         - data/live/btc_binance_BTCUSDT_1d.csv 副本
#   fgi_<UTC日期>.csv              - data/live/fear_greed_index.csv 副本 (如有)
#   state_<model>_<UTC日期>.json   - /opt/fcstlabpro/state/{model}_state.json 副本 (每个模型一份)
#
# 命名带日期 = 每次 dump 都是新文件, 不覆盖历史; git log 看 dump 频率.

set -euo pipefail

REPO_DIR="${REPO_DIR:-/root/FcstLabPro}"
DATA_DIR="${FCST_DATA_DIR:-/opt/fcstlabpro}"
SNAPSHOT_DIR="${REPO_DIR}/data/snapshots"
TODAY=$(date -u +%Y%m%d)
COMMIT_FLAG="${1:-}"

mkdir -p "${SNAPSHOT_DIR}"

echo "=== dump_live_snapshot.sh @ $(date -u +'%Y-%m-%d %H:%M:%S UTC') ==="
echo "REPO_DIR=${REPO_DIR}"
echo "DATA_DIR=${DATA_DIR}"
echo "SNAPSHOT_DIR=${SNAPSHOT_DIR}"
echo "TODAY=${TODAY}"
echo

# 1. OHLCV (data/live/)
SRC_OHLCV="${REPO_DIR}/data/live/btc_binance_BTCUSDT_1d.csv"
if [[ -f "${SRC_OHLCV}" ]]; then
    DST="${SNAPSHOT_DIR}/btc_live_${TODAY}.csv"
    cp "${SRC_OHLCV}" "${DST}"
    echo "[OK] OHLCV -> ${DST} ($(wc -l < ${DST}) rows)"
else
    echo "[SKIP] OHLCV: ${SRC_OHLCV} not found"
fi

# 2. FGI (data/live/)
SRC_FGI="${REPO_DIR}/data/live/fear_greed_index.csv"
if [[ -f "${SRC_FGI}" ]]; then
    DST="${SNAPSHOT_DIR}/fgi_${TODAY}.csv"
    cp "${SRC_FGI}" "${DST}"
    echo "[OK] FGI -> ${DST} ($(wc -l < ${DST}) rows)"
else
    echo "[SKIP] FGI: ${SRC_FGI} not found"
fi

# 3. State JSONs (每个生产模型一份)
SHOT_COUNT=0
for STATE_FILE in "${DATA_DIR}/state/"*_state.json; do
    if [[ ! -f "${STATE_FILE}" ]]; then
        continue
    fi
    BASENAME=$(basename "${STATE_FILE}" _state.json)
    DST="${SNAPSHOT_DIR}/state_${BASENAME}_${TODAY}.json"
    cp "${STATE_FILE}" "${DST}"
    SHOT_COUNT=$((SHOT_COUNT + 1))
    echo "[OK] State -> ${DST}"
done
if [[ ${SHOT_COUNT} -eq 0 ]]; then
    echo "[WARN] no state JSON found in ${DATA_DIR}/state/"
fi

# 4. 跑 PnL replay (lesson_0609 followup) — 为每个非空 state 生成报告
REPORT_DIR="${SNAPSHOT_DIR}/reports"
mkdir -p "${REPORT_DIR}"
OHLCV_SNAPSHOT="${SNAPSHOT_DIR}/btc_live_${TODAY}.csv"
PY_VENV="${REPO_DIR}/.venv/bin/python"
if [[ ! -x "${PY_VENV}" ]]; then
    PY_VENV="python3"  # fallback
fi
REPLAY_SCRIPT="${REPO_DIR}/scripts/research/partial_bar_pnl_replay.py"

echo
if [[ -f "${OHLCV_SNAPSHOT}" && -f "${REPLAY_SCRIPT}" ]]; then
    for STATE_SNAP in "${SNAPSHOT_DIR}/state_"*"_${TODAY}.json"; do
        [[ -f "${STATE_SNAP}" ]] || continue
        # 检查 history 是否为空 (e1 退役模型 history=[] 跳过)
        if python3 -c "import json,sys; sys.exit(0 if json.load(open('${STATE_SNAP}')).get('history') else 1)" 2>/dev/null; then
            STATE_BASE=$(basename "${STATE_SNAP}" .json)
            MODEL_NAME=$(echo "${STATE_BASE}" | sed -E "s/^state_//; s/_${TODAY}\$//")
            REPORT_PATH="${REPORT_DIR}/pnl_replay_${MODEL_NAME}_${TODAY}.md"
            if "${PY_VENV}" "${REPLAY_SCRIPT}" \
                --state-file "${STATE_SNAP}" \
                --ohlcv-file "${OHLCV_SNAPSHOT}" \
                --output "${REPORT_PATH}" 2>&1; then
                echo "[OK] Replay -> ${REPORT_PATH}"
            else
                echo "[WARN] Replay failed for ${MODEL_NAME}"
            fi
        else
            MODEL_NAME=$(basename "${STATE_SNAP}" .json | sed -E "s/^state_//; s/_${TODAY}\$//")
            echo "[SKIP] Replay for ${MODEL_NAME}: history is empty"
        fi
    done
else
    echo "[SKIP] Replay: ohlcv snapshot or script not found"
fi

# 5. 可选 commit + push
if [[ "${COMMIT_FLAG}" == "--commit" ]]; then
    cd "${REPO_DIR}"
    if git diff --quiet -- data/snapshots/; then
        echo
        echo "[INFO] no changes to commit (snapshot identical to last)"
        exit 0
    fi
    git add data/snapshots/
    git commit -m "snapshot(live): dump ${TODAY} (ohlcv + fgi + state + replay reports)"
    git push origin main
    echo
    echo "[OK] committed + pushed."
else
    echo
    echo "[INFO] dry-run only (no commit). Add --commit to push."
fi
