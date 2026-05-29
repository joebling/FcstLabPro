"""Dashboard 配置 — 路径/端口 (env 可覆盖)."""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# performance 产物根目录 (与 build_performance.py / pipeline 一致)
PERF_DIR = Path(
    os.environ.get("FCST_DATA_DIR", str(PROJECT_ROOT / "data" / "live"))
) / "performance"

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

# 数据新鲜度阈值: 日更, 超过此小时数未更新 = stale
STALE_THRESHOLD_HOURS = float(os.environ.get("DASHBOARD_STALE_HOURS", "26"))

HOST = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("DASHBOARD_PORT", "8000"))
