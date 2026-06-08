"""生产 serving 层数据路径 — 单一真相源 (Single Source of Truth).

为什么存在: lesson_0602 把「实时下载」从 data/raw/ 切到 data/live/, 但读取端
(data_freshness / run_production_pipeline / live_signal / build_signal_json) 各自
硬编码了路径常量, 出现「下载写 live, 校验读 raw」的精神分裂 → freshness gate
误报过期 / 推理吃旧基准。

铁律 (lesson_0602 §4):
  - data/raw/  = 不可变训练基准 (sha 锁定, 只读)  → 训练 / 复现专用
  - data/live/ = 实时下载落点 (可变, .gitignore) → 生产 live 链专用
  - 两者永不混用。

本模块只导出生产 live 链该用的路径。研究态 (run_experiment / backtest)
不应 import 这里 — 它们走 config 里的 data/raw/ 基准。
"""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ── 实时下载落点 (生产 live 链唯一应读写的 OHLCV/FGI) ──────────────────────
LIVE_DIR = PROJECT_ROOT / "data" / "live"
EXTERNAL_DIR = PROJECT_ROOT / "data" / "external"

LIVE_OHLCV_PATH = LIVE_DIR / "btc_binance_BTCUSDT_1d.csv"
# FGI 仍落在 data/external/ (外部数据区, 非训练基准), 保持现状。
FGI_PATH = EXTERNAL_DIR / "fear_greed_index.csv"

# ── 不可变训练基准 (仅供需要时显式引用; live 链勿用) ──────────────────────
BASELINE_OHLCV_PATH = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"
