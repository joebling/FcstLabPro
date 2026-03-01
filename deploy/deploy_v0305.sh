#!/usr/bin/env bash
# =============================================================================
# FcstLabPro v0305 E1 — Google Cloud Run Job 部署脚本
#
# 策略: directional_filtered (decontaminated)
#   - 模型: 单个 LightGBM, 129 特征 (已去污染 RSI/SMA)
#   - 标签: RSI<45 & <SMA50 → 21天内 ≥4% 反弹
#   - 变体: conservative (止盈+regime)
#   - PnL回测: CAGR 9.8%, MaxDD -12.7%, PF 1.32, Sharpe 0.63
#
# vs v0302 关键差异:
#   - 无 PyTorch / Orion-BiX → 镜像小, 内存低
#   - 单模型而非 bull+bear 双模型
#   - 持仓状态持久化 (GCS)
#   - 4种明确信号: BUY/HOLD/SELL/SILENT
#
# 前置条件:
#   1. gcloud CLI 已登录: gcloud auth login
#   2. GCP 项目已设置: gcloud config set project <PROJECT_ID>
#   3. 计费已启用
#
# 用法:
#   chmod +x deploy/deploy_v0305.sh
#   ./deploy/deploy_v0305.sh              # 完整流程
#   ./deploy/deploy_v0305.sh build        # 仅构建镜像
#   ./deploy/deploy_v0305.sh deploy       # 仅部署 Job
#   ./deploy/deploy_v0305.sh scheduler    # 仅设置定时
# =============================================================================
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# 配置变量
# ─────────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-forecastlab-prod}"
REGION="asia-east1"
REPO_NAME="fcstlabpro"
IMAGE_NAME="fcstlabpro-v0305-e1"
IMAGE_TAG="latest"
JOB_NAME="daily-btc-signal-v0305-e1"
SCHEDULER_NAME="daily-btc-signal-v0305-e1-trigger"

# E1 轻量级: 2Gi 内存, 2 CPU (对比 v0302 的 16Gi/4CPU)
MEMORY="2Gi"
CPU="2"

# 策略变体: base | moderate | conservative
STRATEGY_VARIANT="${STRATEGY_VARIANT:-conservative}"

# GCS 状态桶 (持仓状态持久化)
STATE_BUCKET="${STATE_BUCKET:-gs://forecastlab-prod-signals/v0305-e1}"

# 完整镜像地址
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${IMAGE_TAG}"

# ─────────────────────────────────────────────────────────────
# Step 0: 前置检查
# ─────────────────────────────────────────────────────────────
echo ""
echo "=== FcstLabPro v0305 E1 部署脚本 ==="
echo "  策略: directional_filtered (decontaminated)"
echo "  变体: ${STRATEGY_VARIANT}"
echo "  模型: LightGBM (129 特征, 无污染)"
echo "  回测: CAGR 9.8%, MaxDD -12.7%, PF 1.32"
echo ""
echo "  vs v0302:"
echo "    - 无 PyTorch → 镜像更小"
echo "    - 2Gi 内存 vs 16Gi"
echo "    - 单模型 vs 双模型"
echo "    - 明确信号 (BUY/HOLD/SELL/SILENT)"
echo ""
echo "=== Step 0: 前置检查 ==="
echo "  项目: ${PROJECT_ID}"
echo "  区域: ${REGION}"
echo "  镜像: ${IMAGE_URI}"
echo "  Job:  ${JOB_NAME}"
echo "  状态: ${STATE_BUCKET}"
echo ""

command -v gcloud >/dev/null 2>&1 || { echo "❌ 请先安装 gcloud CLI"; exit 1; }

# 检查必要文件
for f in deploy/Dockerfile.v0305 deploy/docker_entrypoint_v0305.sh scripts/live_signal.py \
         experiments/weekly/weekly_bear_v0305_E1_decontam/model.joblib \
         experiments/weekly/weekly_bear_v0305_E1_decontam/config.yaml; do
    [ -f "$f" ] || { echo "❌ 缺少文件: $f"; exit 1; }
done

gcloud config set project "${PROJECT_ID}" --quiet
echo "✅ 前置检查通过"

# ─────────────────────────────────────────────────────────────
# Step 1: 构建并推送镜像
# ─────────────────────────────────────────────────────────────
if [[ "${1:-}" == "build" || -z "${1:-}" ]]; then
    echo ""
    echo "=== Step 1: 构建并推送镜像 ==="

    # 启用 API
    for api in artifactregistry run cloudscheduler; do
        gcloud services enable ${api}.googleapis.com --quiet 2>/dev/null || true
    done

    # 检查/创建 Artifact Registry 仓库
    gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" 2>/dev/null || {
        echo "  创建 Artifact Registry 仓库..."
        gcloud artifacts repositories create "${REPO_NAME}" \
            --location="${REGION}" \
            --repository-format=docker \
            --quiet
    }

    # 检查/创建 GCS 状态桶
    BUCKET_NAME=$(echo "${STATE_BUCKET}" | sed 's|gs://||' | cut -d'/' -f1)
    gsutil ls "gs://${BUCKET_NAME}" 2>/dev/null || {
        echo "  创建 GCS 状态桶: gs://${BUCKET_NAME}"
        gsutil mb -l "${REGION}" "gs://${BUCKET_NAME}" || true
    }

    # 使用 v0305 专属 Dockerfile 构建
    echo "  构建 Docker 镜像 (LightGBM only, 无 PyTorch)..."
    gcloud builds submit \
        --tag "${IMAGE_URI}" \
        --project="${PROJECT_ID}" \
        --gcs-log-dir="gs://forecastlab-prod-builds/builds" \
        --dockerfile="deploy/Dockerfile.v0305"

    echo "✅ 镜像构建完成: ${IMAGE_URI}"
fi

# ─────────────────────────────────────────────────────────────
# Step 2: 部署 Cloud Run Job
# ─────────────────────────────────────────────────────────────
if [[ "${1:-}" == "deploy" || -z "${1:-}" ]]; then
    echo ""
    echo "=== Step 2: 部署 Cloud Run Job ==="

    # 环境变量
    ENV_VARS="PYTHONUNBUFFERED=1"
    ENV_VARS="${ENV_VARS},STRATEGY_VARIANT=${STRATEGY_VARIANT}"
    ENV_VARS="${ENV_VARS},STATE_BUCKET=${STATE_BUCKET}"
    ENV_VARS="${ENV_VARS},MODEL_VERSION=v0305-E1"
    # 邮件配置 (复用 v0302 的 SMTP 设置)
    ENV_VARS="${ENV_VARS},SMTP_HOST=smtp.qq.com"
    ENV_VARS="${ENV_VARS},SMTP_PORT=465"
    ENV_VARS="${ENV_VARS},SMTP_USER=792680027@qq.com"
    ENV_VARS="${ENV_VARS},SMTP_PASS=mlefgnksjkafbfei"
    ENV_VARS="${ENV_VARS},MAIL_TO=792680027@qq.com"

    # Gemini API Key (Secret Manager)
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

    # 获取 Cloud Run 服务账号
    SA_EMAIL=$(gcloud run jobs describe "${JOB_NAME}" --region="${REGION}" \
        --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || echo "")

    SCHEDULER_CMD="gcloud scheduler jobs"
    if gcloud scheduler jobs describe "${SCHEDULER_NAME}" --location="${REGION}" --project="${PROJECT_ID}" 2>/dev/null; then
        SCHEDULER_ACTION="update"
    else
        SCHEDULER_ACTION="create"
    fi

    ${SCHEDULER_CMD} ${SCHEDULER_ACTION} http "${SCHEDULER_NAME}" \
        --location="${REGION}" \
        --project="${PROJECT_ID}" \
        --uri="https://${REGION}-run.googleapis.com/apis/run/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run" \
        --schedule="5 0 * * *" \
        --time-zone="UTC" \
        --http-method=POST \
        --oauth-service-account-email="${SA_EMAIL:-${PROJECT_ID}@appspot.gserviceaccount.com}" \
        --quiet

    echo "✅ 调度器设置完成: ${SCHEDULER_NAME}"
    echo "  运行时间: 每天 UTC 00:05 (币安日线收盘后 5 分钟)"
fi

# ─────────────────────────────────────────────────────────────
# 完成
# ─────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "✅ FcstLabPro v0305 E1 部署完成！"
echo "============================================================"
echo ""
echo "Job 信息:"
echo "  - Job 名称: ${JOB_NAME}"
echo "  - 镜像: ${IMAGE_URI}"
echo "  - 内存: ${MEMORY} (↓ vs v0302 16Gi)"
echo "  - CPU: ${CPU} (↓ vs v0302 4CPU)"
echo "  - 状态桶: ${STATE_BUCKET}"
echo ""
echo "策略信息:"
echo "  - 变体: ${STRATEGY_VARIANT}"
echo "  - 标签: directional_filtered (RSI<45 & <SMA50 → 21天 ≥4%)"
echo "  - 止盈: +4% | 到期: 21天 | Regime: 63d收益≤-10%→静默"
echo "  - PnL 回测: CAGR=9.8%, MaxDD=-12.7%, PF=1.32"
echo ""
echo "手动触发:"
echo "  gcloud run jobs execute ${JOB_NAME} --region ${REGION}"
echo ""
echo "查看日志:"
echo "  gcloud logging read \\"
echo "    'resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${JOB_NAME}\"' \\"
echo "    --limit=50"
echo ""
echo "查看持仓状态:"
echo "  gsutil cat ${STATE_BUCKET}/signal_state.json | python3 -m json.tool"
echo ""
echo "暂停调度:"
echo "  gcloud scheduler jobs pause ${SCHEDULER_NAME} --location=${REGION}"
echo ""
echo "并行运行: v0302 + v0305-E1 对比观察"
echo ""
