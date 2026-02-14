#!/bin/bash
# 切换 Cloud Run Job 部署的 Bull/Bear 模型版本（A6/A8/v6/v1/v4等）
# 用法：
#   ./switch_weekly_model.sh A6A8
#   ./switch_weekly_model.sh v6
#   ./switch_weekly_model.sh v1v4
#
# 需先配置好 gcloud CLI、GCP 项目和权限。

set -e

# === 配置区 ===
REGION="asia-east1"
JOB_NAME="daily-btc-signal-v6"
IMAGE_URI="asia-east1-docker.pkg.dev/forecastlab-prod/fcstlabpro/fcstlabpro-v6:latest"

# 预设模型目录映射
case "$1" in
  A6A8)
    BULL_DIR="experiments/weekly/ablation_bull_A6_xxx"
    BEAR_DIR="experiments/weekly/ablation_bear_A8_xxx"
    ;;
  v6)
    BULL_DIR="experiments/weekly/weekly_bull_v6_20260213_214847_a29943"
    BEAR_DIR="experiments/weekly/weekly_bear_v6_20260213_215211_1928bd"
    ;;
  v1v4)
    BULL_DIR="experiments/weekly/weekly_bull_v1_xxx"
    BEAR_DIR="experiments/weekly/weekly_bear_v4_xxx"
    ;;
  *)
    echo "用法: $0 [A6A8|v6|v1v4]"
    exit 1
    ;;
esac

# === 构建新 Job 启动命令 ===
CMD="python scripts/weekly_signal.py --bull-dir $BULL_DIR --bear-dir $BEAR_DIR"

echo "[INFO] 切换 Cloud Run Job 启动命令为:"
echo "  $CMD"

gcloud run jobs update $JOB_NAME \
  --image $IMAGE_URI \
  --region $REGION \
  --command "bash" \
  --args "-c","$CMD"

echo "[OK] 切换完成。可用如下命令手动触发："
echo "  gcloud run jobs execute $JOB_NAME --region $REGION"
