"""Dashboard 数据读取层 — 按领域拆分.

  signals     — 信号 archive / 最新信号 / 双模型对比 (paper)
  market      — OHLCV + 外部数据 (FGI/funding/多空比/持仓量/宏观)
  models      — active.yaml / manifest / 回测指标

均为只读, 调 src/performance 复用回填闭环。
"""
from __future__ import annotations

from pathlib import Path


def load_display_ohlcv():
    """加载用于展示的 OHLCV — 优先 data/live/ (实时落点), 缺失回退 data/raw/ (训练基准).

    遵 lesson_0602 铁律: dashboard 是 live 展示层, 应读 data/live/ (每日 pipeline
    的实时下载落点)。本地开发 / 全新 checkout 没有 live (.gitignore) 时回退到
    data/raw/ 基准, 保证不崩 (会显示陈旧, 但有 price_date 标注)。

    Returns
    -------
    (df, source) : df 为 DatetimeIndex 的 OHLCV; source 为 'live' / 'baseline'。
    """
    from src.performance.backfill import load_ohlcv
    from src.serving.paths import BASELINE_OHLCV_PATH, LIVE_OHLCV_PATH

    if Path(LIVE_OHLCV_PATH).exists():
        return load_ohlcv(LIVE_OHLCV_PATH), "live"
    return load_ohlcv(BASELINE_OHLCV_PATH), "baseline"
