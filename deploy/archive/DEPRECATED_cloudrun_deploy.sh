#!/usr/bin/env bash
# =============================================================================
# ⛔️ DEPRECATED (2026-06-02) — Cloud Run 部署已完全停用, 勿运行!
#
# 现役生产链路 = VPS 无 Docker:
#     deploy/vps/run_daily_nodock.sh → scripts/run_production_pipeline.py
#     模型/variant 由 models/production/active.yaml 单一真相源决定。
#
# 本脚本用旧的 MODEL_NAME / STRATEGY_VARIANT 环境变量 (多处真相源),
# 与现架构不兼容。仅作历史备查。
# 详见 deploy/README.md
# =============================================================================
# =============================================================================
# FcstLabPro 通用部署脚本 (模型无关)
#
# 用法:
#   MODEL_NAME=e1-conservative ./deploy/deploy.sh           # 完整流程
#   MODEL_NAME=e8-touch ./deploy/deploy.sh                  # 部署 E8
#   MODEL_NAME=e1-conservative ./deploy/deploy.sh build      # 仅构建
#   MODEL_NAME=e1-conservative ./deploy/deploy.sh deploy     # 仅部署 Job
#   MODEL_NAME=e1-conservative ./deploy/deploy.sh scheduler  # 仅定时
# =============================================================================
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# 配置变量
# ─────────────────────────────────────────────────────────────
MODEL_NAME="${MODEL_NAME:?ERROR: 请设置 MODEL_NAME. 例: MODEL_NAME=e1-conservative}"
PROJECT_ID="${GCP_PROJECT_ID:-forecastlab-prod}"
REGION="asia-east1"
REPO_NAME="fcstlabpro"
IMAGE_NAME="fcstlabpro-v0305"
IMAGE_TAG="latest"
JOB_NAME="daily-btc-signal-${MODEL_NAME}"
SCHEDULER_NAME="trigger-${MODEL_NAME}"

MEMORY="2Gi"
CPU="2"
STRATEGY_VARIANT="${STRATEGY_VARIANT:-conservative}"
STATE_BUCKET="${STATE_BUCKET:-gs://forecastlab-prod-signals/${MODEL_NAME}}"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${IMAGE_TAG}"

# 验证模型目录存在
MODEL_DIR="models/production/${MODEL_NAME}"
for f in "${MODEL_DIR}/model.joblib" "${MODEL_DIR}/config.yaml" "${MODEL_DIR}/manifest.json"; do
    [ -f "$f" ] || { echo "❌ 缺少文件: $f"; exit 1; }
done

# 从 manifest 读取模型信息
LABEL=$(python3 -c "import json; m=json.load(open('${MODEL_DIR}/manifest.json')); print(m['strategy']['label'])")
KAPPA=$(python3 -c "import json; m=json.load(open('${MODEL_DIR}/manifest.json')); print(f\"{m['metrics']['classification']['cohen_kappa']:.2f}\")")

echo ""
echo "=== FcstLabPro 部署 ==="
echo "  模型:     ${MODEL_NAME}"
echo "  标签:     ${LABEL}"
echo "  Kappa:   ${KAPPA}"
echo "  变体:     ${STRATEGY_VARIANT}"
echo "  镜像:     ${IMAGE_URI}"
echo "  Job:     ${JOB_NAME}"
echo "  状态桶:   ${STATE_BUCKET}"
echo ""

command -v gcloud >/dev/null 2>&1 || { echo "❌ 请先安装 gcloud CLI"; exit 1; }
gcloud config set project "${PROJECT_ID}" --quiet
echo "✅ 前置检查通过"

# ─────────────────────────────────────────────────────────────
# Step 1: 构建并推送镜像 (所有模型共享同一镜像)
# ─────────────────────────────────────────────────────────────
if [[ "${1:-}" == "build" || -z "${1:-}" ]]; then
    echo ""
    echo "=== Step 1: 构建镜像 ==="

    for api in artifactregistry run cloudscheduler; do
        gcloud services enable ${api}.googleapis.com --quiet 2>/dev/null || true
    done

    gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" 2>/dev/null || {
        gcloud artifacts repositories create "${REPO_NAME}" \
            --location="${REGION}" --repository-format=docker --quiet
    }

    BUCKET_NAME=$(echo "${STATE_BUCKET}" | sed 's|gs://||' | cut -d'/' -f1)
    gsutil ls "gs://${BUCKET_NAME}" 2>/dev/null || {
        gsutil mb -l "${REGION}" "gs://${BUCKET_NAME}" || true
    }

    gcloud builds submit . \
        --tag "${IMAGE_URI}" \
        --project="${PROJECT_ID}" \
        --gcs-log-dir="gs://forecastlab-prod-builds/builds" \
        --ignore-file=.dockerignore

    echo "✅ 镜像构建完成: ${IMAGE_URI}"
fi

# ─────────────────────────────────────────────────────────────
# Step 2: 部署 Cloud Run Job (MODEL_NAME 特定)
# ─────────────────────────────────────────────────────────────
if [[ "${1:-}" == "deploy" || -z "${1:-}" ]]; then
    echo ""
    echo "=== Step 2: 部署 Job: ${JOB_NAME} ==="

    ENV_VARS="PYTHONUNBUFFERED=1"
    ENV_VARS="${ENV_VARS},MODEL_NAME=${MODEL_NAME}"
    ENV_VARS="${ENV_VARS},STRATEGY_VARIANT=${STRATEGY_VARIANT}"
    ENV_VARS="${ENV_VARS},STATE_BUCKET=${STATE_BUCKET}"
    ENV_VARS="${ENV_VARS},SMTP_HOST=smtp.qq.com"
    ENV_VARS="${ENV_VARS},SMTP_PORT=465"
    ENV_VARS="${ENV_VARS},SMTP_USER=792680027@qq.com"
    ENV_VARS="${ENV_VARS},SMTP_PASS=mlefgnksjkafbfei"
    ENV_VARS="${ENV_VARS},MAIL_TO=792680027@qq.com"

    SECRET_NAME="gemini-api-key"

    gcloud run jobs deploy "${JOB_NAME}" \
        --image="${IMAGE_URI}" \
        --region="${REGION}" \
        --project="${PROJECT_ID}" \
        --memory="${MEMORY}" \
        --cpu="${CPU}" \
        --max-retries=2 \
        --task-timeout=600s \
        --set-env-vars="${ENV_VARS}" \
        --set-secrets="GEMINI_API_KEY=${SECRET_NAME}:latest" \
        --quiet

    echo "✅ Job 部署完成: ${JOB_NAME}"
fi

# ─────────────────────────────────────────────────────────────
# Step 3: 设置定时调度
# ─────────────────────────────────────────────────────────────
if [[ "${1:-}" == "scheduler" || -z "${1:-}" ]]; then
    echo ""
    echo "=== Step 3: 设置定时调度 ==="

    SA_EMAIL=$(gcloud run jobs describe "${JOB_NAME}" --region="${REGION}" \
        --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || echo "")

    SCHEDULER_CMD="gcloud scheduler jobs"
    if gcloud scheduler jobs describe "${SCHEDULER_NAME}" --location="${REGION}" --project="${PROJECT_ID}" 2>/dev/null; then
        SCHEDULER_ACTION="update"
    else
        SCHEDULER_ACTION="create"
    fi

    # 获取项目数字 ID (Cloud Run URI 需要用数字 ID)
    PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(number)" 2>/dev/null || echo "${PROJECT_ID}")

    ${SCHEDULER_CMD} ${SCHEDULER_ACTION} http "${SCHEDULER_NAME}" \
        --location="${REGION}" \
        --project="${PROJECT_ID}" \
        --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_NUMBER}/jobs/${JOB_NAME}:run" \
        --schedule="5 0 * * *" \
        --time-zone="UTC" \
        --http-method=POST \
        --oauth-service-account-email="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
        --quiet

    echo "✅ 调度器: ${SCHEDULER_NAME} (每天 UTC 00:05)"
fi

# ─────────────────────────────────────────────────────────────
# 完成
# ─────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "✅ ${MODEL_NAME} 部署完成！"
echo "============================================================"
echo ""
echo "手动触发:"
echo "  gcloud run jobs execute ${JOB_NAME} --region ${REGION}"
echo ""
echo "查看日志:"
echo "  gcloud logging read 'resource.labels.job_name=\"${JOB_NAME}\"' --limit=50"
echo ""
echo "查看状态:"
echo "  gsutil cat ${STATE_BUCKET}/signal_state.json | python3 -m json.tool"
echo ""
echo "暂停调度:"
echo "  gcloud scheduler jobs pause ${SCHEDULER_NAME} --location=${REGION}"
echo ""
