"""Performance tracking 层 (Layer P) — 预测→真实结果回填闭环.

只读 signal_ledger archive + 真实 OHLCV, 计算实现结果与指标。
绝不反向影响信号生成 (避免 look-ahead 污染)。

模块:
  maturity   — 标签成熟度门控 (从 config.label.T 推导, 防漂移)
  backfill   — 单条信号回填实现结果
  aggregate  — 批次聚合 + 滚动指标 (命中率/实现收益/Rank IC)
  cache      — 进程内 TTL 缓存 (对齐 RiskDetect)
  service    — dashboard 入口: 实时算 + 缓存 (无中间 JSON 产物)

真相源单一 = data/signals/archive/ (类比 RiskDetect 的 Postgres)。
dashboard 请求时实时回填聚合, 不预生成文件。
详见 docs/design/performance_tracking.md。
"""
