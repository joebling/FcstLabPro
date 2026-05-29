#!/bin/bash
# FcstLabPro 信号生成 + 邮件发送自动化脚本
#
# 模型清单从 models/production/active.yaml 驱动 (不再硬编码模型名/variant)。
# 路径全部相对于脚本位置, 不再写死 /Users/qiubling/...
set -euo pipefail

# 脚本所在目录的上级 = 项目根
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# 优先用项目内 .venv, 否则回退系统 python
if [ -x "${PROJECT_ROOT}/.venv/bin/python" ]; then
    PY="${PROJECT_ROOT}/.venv/bin/python"
else
    PY="$(command -v python3)"
fi

echo "=== FcstLabPro 信号生成 (active.yaml 驱动) ==="
echo "  项目根: ${PROJECT_ROOT}"
echo "  解释器: ${PY}"

# 全部交给 run_cron_signal.py (它从 active.yaml 解析模型 + 下载数据 + 发邮件)
# 默认只跑 status=live; 加 --include-paper 连 paper 一起跑
exec "${PY}" "${PROJECT_ROOT}/scripts/run_cron_signal.py" "$@"
