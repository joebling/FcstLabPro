"""Dashboard 配置 — 路径/端口 (env 可覆盖)."""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

HOST = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("DASHBOARD_PORT", "8000"))

# 生产数据根 (与 pipeline / run_daily_nodock.sh 一致, 默认 /opt/fcstlabpro)。
# 持仓账本 (真实交易历史) 在 ${FCST_DATA_DIR}/state/{model}_state.json。
DATA_DIR = Path(os.environ.get("FCST_DATA_DIR", "/opt/fcstlabpro"))
STATE_DIR = DATA_DIR / "state"
