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
| 0. preflight | 解析 active.yaml + 模型产物校验 + 判定是否依赖 FGI / LLM / 邮件 | — | 缺产物 fail |
| 1. download_ohlcv | Binance 日线 → `data/raw/btc_binance_BTCUSDT_1d.csv` | yes | halt |
| 2. download_fgi | FGI → `data/external/fear_greed_index.csv` (强制刷新) | yes | halt |
| 3. validate_data | OHLCV + FGI freshness 强校验 (核心) | yes | halt |
| 4. signals | 每个 active 模型: 信号 → JSON → (LLM) → (邮件) | yes* | halt |

**决策 A**：数据缺失 / 过期一律 FATAL，不再静默 ffill stale FGI。

\* stage 4 内部：**推理失败 → halt**；但 JSON/LLM/邮件 是输出侧
(required=False 语义)，单个失败不阻断 (信号本身已生成)。
LLM 需 `GEMINI_API_KEY`，邮件需 `SMTP_USER`+`SMTP_PASS`，缺凭据自动跳过。

信号摘要格式: `e1-conservative=SILENT+json+llm+mail` (后缀表示完成的输出环节)。

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

## 2.5 数据保存路径 (单一来源)

下载的数据落到项目内固定路径，**下载 / 特征 / 校验三方读的是同一份文件**：

| 数据 | 保存路径 | 写入者 | 读取者 |
|------|----------|--------|--------|
| OHLCV | `data/raw/btc_binance_BTCUSDT_1d.csv` | downloader | features + freshness gate |
| FGI | `data/external/fear_greed_index.csv` | `src/data/external.py` | `src/features/external.py` + freshness gate |

FGI 路径在 `src/data/external.py` 写死 (按文件位置算 PROJECT_ROOT，与 cwd 无关)：

```python
CACHE_DIR = PROJECT_ROOT / "data" / "external"
cache_path = CACHE_DIR / "fear_greed_index.csv"
```

pipeline 与 freshness gate 的常量都指向同一处，闭环对齐：

```python
# run_production_pipeline.py / src/serving/data_freshness.py
FGI_PATH = PROJECT_ROOT / "data" / "external" / "fear_greed_index.csv"
```

> ⚠️ `download_fear_greed_index(cache=True)` 默认吃 12h 缓存; pipeline 的
> download_fgi stage 传 `cache=False` 强制刷新, 不会被旧缓存骗过 freshness gate。

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
新 pipeline 是其超集 + 强校验。

### VPS 部署 (run_daily_nodock.sh 已成点火瓦壳)

`deploy/vps/run_daily_nodock.sh` 已瘦身为点火瓦壳 (路 B)：
只负责 `source .env` + 前置检查 + 线程设置，编排全部委托给 pipeline:

```bash
exec "${VENV_PYTHON}" scripts/run_production_pipeline.py --include-paper "$@"
```

crontab 入口不变，仍指向 `run_daily_nodock.sh`。

**语义变化** (路 B 后)：
- 模型清单 / 变体从 `active.yaml` 读 (单一真相源)，
  不再读 `MODEL_NAMES` / `STRATEGY_VARIANT` 环境变量。
- 输出目录默认 `/opt/fcstlabpro`，由 `FCST_DATA_DIR` 控制
  (本地开发设 `FCST_DATA_DIR=/tmp/fcst` 即可, 不污染生产)。
- state → `${FCST_DATA_DIR}/state/{model}_state.json`
- 信号 JSON → `${FCST_DATA_DIR}/signals/{model}/signal_{date}.json`

### 故障注入测试 (验证闸门真的会拦)

⚠️ 别先砸数据再跑整脚本 —— download stage 会把数据重新拉新，把你砸的旧数据覆盖掉。
正确做法: 用 `--from-stage` 跳过下载，只测校验段：

```bash
cp data/external/fear_greed_index.csv /tmp/fgi_backup.csv
head -n -90 /tmp/fgi_backup.csv > data/external/fear_greed_index.csv

python scripts/run_production_pipeline.py --from-stage 3.validate_data
# 期望: 3.validate_data FAILED, exit 1

cp /tmp/fgi_backup.csv data/external/fear_greed_index.csv   # 恢复
```

迁移完成后可考虑废弃旧 `run_cron_signal.py`。


---

## 7. LLM 策略分析 (可选, 多 provider)

stage 4 的 LLM 环节支持多 provider, 全部走环境变量, **零硬编码 key**。
provider 实现在 `src/llm/analyst.py`, 用 urllib 无额外依赖。

### provider=gemini (默认)

```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=xxxxx
# GEMINI_MODEL=gemini-2.0-flash   # 可选
```

### provider=anthropic (Anthropic Messages API 格式, 含腾讯 tokenhub 网关)

例: DeepSeek via 腾讯 tokenhub

```bash
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-xxxxx                       # 不要提交到 git!
LLM_BASE_URL=https://tokenhub.tencentmaas.com/
LLM_MODEL=deepseek-v4-pro
```

请求打到 `${LLM_BASE_URL}/v1/messages`, 同时带 `x-api-key` 和
`Authorization: Bearer` 两个头 (兼容不同网关)。

### 启用判定

pipeline preflight 按 provider 检测 key:
- gemini → 看 `GEMINI_API_KEY`
- 其他 → 看 `LLM_API_KEY` 或 `ANTHROPIC_API_KEY`

缺 key → `enable_llm=False`, 自动跳过 (不阻断信号)。

### 连通性自测

```bash
LLM_PROVIDER=anthropic LLM_API_KEY=sk-xxx \
LLM_BASE_URL=https://tokenhub.tencentmaas.com/ LLM_MODEL=deepseek-v4-pro \
python -c "from src.llm.analyst import _resolve_provider,_DISPATCH; \
p,c=_resolve_provider(); print(_DISPATCH[p]('测试','说连接成功',c))"
```

> ⚠️ **安全**: key 只放 `.env` (已 gitignore)。切勿写进源码/文档/commit。
> 若 key 不慎泄露, 立即去对应平台后台轮换。
