"""Dashboard 数据读取层 — 按领域拆分.

  signals     — 信号 archive / 最新信号 / 双模型对比 (paper)
  market      — OHLCV + 外部数据 (FGI/funding/多空比/持仓量/宏观)
  models      — active.yaml / manifest / 回测指标

均为只读, 调 src/performance 复用回填闭环。
"""
