#!/usr/bin/env python3
"""启动 Performance Dashboard.

Usage:
    python scripts/serve_dashboard.py                 # 127.0.0.1:8000
    DASHBOARD_HOST=0.0.0.0 DASHBOARD_PORT=8000 ...     # env 覆盖 (慎用 0.0.0.0)

VPS 常驻请用 systemd (见 deploy/vps/fcstlab-dashboard.service)。
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn

from src.dashboard.config import HOST, PORT

if __name__ == "__main__":
    print(f"🚀 Dashboard 启动: http://{HOST}:{PORT}")
    uvicorn.run("src.dashboard.app:app", host=HOST, port=PORT, log_level="info")
