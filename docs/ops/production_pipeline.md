# 生产信号 Pipeline (run_production_pipeline.py)

单命令跑完「下载 → 校验 → 信号」全链路。参照
`EventReadiness/scripts/run_production_pipeline.py` 的声明式 Stage 模式，
但因 LightGBM 推理极轻，采用 **in-process** 调用（无 subprocess 隔离开销）。

对应 `docs/reviews/cr_0529_model_governance_vs_riskdetect.md` §B
(external data lineage / freshness gate)。

---

## 1. 链路

| Stage | 作用 | required | 失败行为 |
|-------|------|----------|----------|
| 0. preflight | 解析 active.yaml + 模型产物校验 + 判定是否依赖 FGI | — | 缺产物 fail |
| 1. download_ohlcv | Binance 日线 → `data/raw/btc_binance_BTCUSDT_1d.csv` | yes | halt |
| 2. download_fgi | FGI → `data/external/fear_greed_index.csv` (强制刷新) | yes | halt |
| 3. validate_data | OHLCV + FGI freshness 强校验 (核心) | yes | halt |
| 4. signals | 每个 active 模型 in-process 出信号 | yes | halt |

**决策 A**：数据缺失 / 过期一律 FATAL，不再静默 ffill stale FGI。

---

## 2. 新鲜度 SLA

SLA 写在 `models/production/active.yaml::data_freshness`（不硬编码）：

```yaml
data_freshness:
  ohlcv_max_stale_days: 2   # OHLCV 相对今天(UTC) 最大滞后
  fgi_max_stale_days: 2     # FGI last_date 相对 OHLCV last_date 最大滞后
```

- OHLCV 基准 = 今天 (UTC)
- FGI 基准 = OHLCV last_date（推理特征对齐到交易日）

**research / backtest 不读这里** —— gate 只作用于 live pipeline，不误伤回测。

---

## 3. 常用命令

```bash
# 标准 cron (只跑 status=live)
python scripts/run_production_pipeline.py

# 连 paper 模型
python scripts/run_production_pipeline.py --include-paper

# 看计划 (validate 仍真跑)
python scripts/run_production_pipeline.py --dry-run

# 跳过下载, 只校验+信号 (VPS 调试)
python scripts/run_production_pipeline.py --from-stage 3.validate_data

# 只跑某 stage
python scripts/run_production_pipeline.py --only-stage 3.validate_data

# shadow 账本
python scripts/run_production_pipeline.py --ledger-mode shadow
```

退出码：全绿 0，任一 required stage 失败 1。

---

## 4. VPS 测试步骤

> 仓库里 FGI 是 stale 81 天旧数据，gate 会按设计 FATAL。
> 在能联网的 VPS 上测试真实下载 + 校验通过路径。

### 4.1 先验证 gate 会拦 stale (任意环境)

```bash
python scripts/run_production_pipeline.py --dry-run --from-stage 3.validate_data
# 期望: 3.validate_data FAILED, FGI 过期 81 天 > SLA 2, exit 1
```

### 4.2 真实下载 + 校验 (VPS, 需联网)

```bash
curl -s "https://api.alternative.me/fng/?limit=2&format=json" | head
curl -s "https://api.binance.com/api/v3/ping"

python scripts/run_production_pipeline.py
```

期望：

```text
1.download_ohlcv   OK   ... 行 (end=最新)
2.download_fgi     OK   ... 行 (end=最新)
3.validate_data    OK   ohlcv: stale=0d/SLA=2d; fgi: stale<=1d/SLA=2d
4.signals          OK   e1-conservative=<SIGNAL>
```

### 4.3 若某 API 在 VPS 被墙

- Binance：用 `BINANCE_BASE_URL` 指定可用端点（downloader 支持多端点回退）。
- FGI：alternative.me 一般无地域限制；失败且无缓存会直接 FATAL（决策 A）。

```bash
BINANCE_BASE_URL="https://data-api.binance.vision" python scripts/run_production_pipeline.py
```

---

## 5. 测试覆盖

`tests/test_data_freshness.py`（8 用例）锁死决策 A：

- OHLCV / FGI 新鲜 -> 通过
- OHLCV / FGI 过期 -> DataFreshnessError
- 文件缺失 -> DataFreshnessError
- FGI 缺 fgi_value 列 -> DataFreshnessError

```bash
.venv/bin/python -m pytest tests/test_data_freshness.py -q
```

---

## 6. 与旧 run_cron_signal.py 的关系

旧 `run_cron_signal.py` 只下载 Binance、对 FGI 静默 ffill，无 freshness gate。
新 pipeline 是其超集 + 强校验。建议 cron 切到：

```bash
python scripts/run_production_pipeline.py
```

迁移完成后可考虑废弃旧 cron 脚本（待 VPS 验证通过后再删，避免一次动太多）。
