"""Dashboard 数据读取层 — 按领域拆分.

  signals     — 信号 archive / 最新信号 / 双模型对比 (paper)
  market      — OHLCV + 外部数据 (FGI/funding/多空比/持仓量/宏观)
  models      — active.yaml / manifest / 回测指标

均为只读, 调 src/performance 复用回填闭环。
"""
from __future__ import annotations

from pathlib import Path


def load_display_ohlcv():
    """加载用于展示的 OHLCV — 优先 data/live/ (实时落点), 缺失回退 data/raw/ 基准.

    核心逻辑在 src.performance.backfill.load_live_ohlcv (单一真相源, DRY)。
    本函数额外返回 source 标签供需要区分 live/baseline 的调用方。

    Returns
    -------
    (df, source) : df 为 DatetimeIndex 的 OHLCV; source 为 'live' / 'baseline'。
    """
    from src.performance.backfill import load_live_ohlcv
    from src.serving.paths import LIVE_OHLCV_PATH

    source = "live" if Path(LIVE_OHLCV_PATH).exists() else "baseline"
    return load_live_ohlcv(), source
