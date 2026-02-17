#!/usr/bin/env bash
# =============================================================================
# FcstLabPro v0215 — 设置 VM 定期任务 (cron)
# 每天北京时间 08:00 (UTC 00:00) 运行
# =============================================================================
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# 加载本地 .env 文件（如果有）
# ─────────────────────────────────────────────────────────────
if [ -f "$(dirname "$0")/../.env" ]; then
    set -a
    source "$(dirname "$0")/../.env"
    set +a
fi

# 配置变量
PROJECT_ID="${GCP_PROJECT_ID:-forecastlab-prod}"
ZONE="asia-east1-a"
VM_NAME="fcstlabpro-signal-vm"
IMAGE_URI="asia-east1-docker.pkg.dev/${PROJECT_ID}/fcstlabpro/fcstlabpro-0215:latest"

echo ""
echo "============================================================"
echo "🚀 设置 VM 定期任务"
echo "============================================================"
echo ""

# Step 1: 在 VM 上创建运行脚本
echo "=== Step 1: 在 VM 上创建运行脚本 ==="
gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --tunnel-through-iap --command="
    # 创建运行脚本
    cat > /home/\$USER/run_fcstlabpro.sh << 'EOF'
#!/bin/bash
# FcstLabPro 每日运行脚本
set -e

echo \"==============================================\"
echo \"🔮 FcstLabPro 每日任务 - \$(date '+%Y-%m-%d %H:%M:%S')\"
echo \"==============================================\"

# 拉取最新镜像
echo \"📥 拉取最新镜像...\"
sudo docker pull asia-east1-docker.pkg.dev/forecastlab-prod/fcstlabpro/fcstlabpro-0215:latest

# 运行容器（包含环境变量）
echo \"🚀 运行容器...\"
sudo docker rm -f fcstlabpro-daily 2>/dev/null || true
sudo docker run --name fcstlabpro-daily \\
    -e SMTP_HOST=smtp.qq.com \\
    -e SMTP_PORT=465 \\
    -e SMTP_USER=792680027@qq.com \\
    -e SMTP_PASS=mlefgnksjkafbfei \\
    -e MAIL_TO=792680027@qq.com \\
    -e GEMINI_API_KEY=AIzaSyBi6wGbbnbbYJrclYqAQeeCe-HozwVyqyg \\
    asia-east1-docker.pkg.dev/forecastlab-prod/fcstlabpro/fcstlabpro-0215:latest

# 清理
echo \"🧹 清理完成\"
sudo docker rm -f fcstlabpro-daily 2>/dev/null || true

echo \"✅ 任务完成\"
EOF

    # 赋予执行权限
    chmod +x /home/\$USER/run_fcstlabpro.sh
"
echo "✅ 运行脚本已创建"

# Step 2: 设置 cron 任务
echo ""
echo "=== Step 2: 设置 cron 任务 ==="
gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --tunnel-through-iap --command="
    # 备份当前 crontab
    crontab -l > /tmp/crontab_backup.txt 2>/dev/null || true
    
    # 添加 cron 任务（每天 UTC 00:00 = 北京时间 08:00）
    (crontab -l 2>/dev/null; echo \"0 0 * * * /home/\$USER/run_fcstlabpro.sh >> /home/\$USER/fcstlabpro_cron.log 2>&1\") | crontab -
    
    # 验证
    echo \"当前 crontab 配置：\"
    crontab -l
"
echo "✅ cron 任务已设置"

echo ""
echo "============================================================"
echo "✅ 设置完成！"
echo "============================================================"
echo ""
echo "📅 运行时间：每天 UTC 00:00（北京时间 08:00）"
echo ""
echo "🧪 手动测试："
echo "  gcloud compute ssh ${VM_NAME} --zone=${ZONE} --tunnel-through-iap --command='/home/\$USER/run_fcstlabpro.sh'"
echo ""
echo "📜 查看 cron 日志："
echo "  gcloud compute ssh ${VM_NAME} --zone=${ZONE} --tunnel-through-iap --command='tail -f /home/\$USER/fcstlabpro_cron.log'"
echo ""
echo "❌ 删除 cron 任务："
echo "  gcloud compute ssh ${VM_NAME} --zone=${ZONE} --tunnel-through-iap --command='crontab -r'"
echo ""
