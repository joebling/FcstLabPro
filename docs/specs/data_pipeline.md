# FcstLabPro 数据链路文档

> 最后更新：2026-05-22 · 覆盖范围：E1 / E8 双生产模型
> 最近变动：§10.1 修复 train↔serve 列错位 P0 隐患（新增 `feature_cols.json` 列序校验）
> 配套阅读：[`models/production/SUMMARY.md`](../../models/production/SUMMARY.md) · [`deploy/README.md`](../../deploy/README.md)

---

## 0. TL;DR

- **数据源**：1 个**必需**（Binance Klines）+ 1 个**实际在用**（Alternative.me FGI）。其他 7 个外部源已编码但当前生产**未启用**。
- **FGI 贡献**：在 E1/E8 里提供约 **5% feature importance**，`ext_fgi_std_14` 在 E1 排 #5。**不可移除**。
- ⚠️ **名称地雷**：模型 #1 特征 `funding_rate_14` **不是真实资金费率**，是 `market_structure.py` 里用 `close.pct_change().rolling()` 计算的 OHLCV 派生代理。同理 `open_interest_*` / `stablecoin_inflow_proxy` 也是 proxy。
- **训练↔推理同源**：训练和推理共享同一份 `src/data/`、`src/features/`、`src/labels/` 代码 —— **没有 train/serve skew**。
- **E1 与 E8 的数据链路完全相同**，差异仅在 `src/labels/` 模块（`directional_filtered` vs `touch_filtered`）。
- **隐藏关键依赖**：`signal_state.json`（GCS 持久化的持仓状态），丢失会导致下一次推理误判持仓。
- **模型实际输入**：**129 列特征**（5 个特征集生成 137 列 → drop 4 个 glob 模式 → 129 列）。

---

## 1. 总体架构

```
                        ┌──────────────────────────────────────┐
                        │              外部数据源 (Sources)        │
                        └──────────────────────────────────────┘
                                            │
        ┌──────────────────────────────────────┼───────────────────────────────────┐
        ▼                                   ▼                                   ▼
  Binance REST API                  Alternative.me                       (未启用 · 研究遗留)
  /api/v3/klines                    /fng/                                Yahoo macro (DXY/VIX/...)
  必需 · OHLCV 日线                   重要 · ~5% importance                Binance Futures FR / LS Ratio
        │                                   │                                   │
        ▼                                   ▼                                   ×
  data/raw/btc_*_1d.csv             data/external/fear_greed_index.csv
  (CSV, ~2330 行)                   (12h 缓存, ~2300 行)
        │                                   │
        └───────────────────┬───────────────┘
                            ▼
              ┌─────────────────────────────┐
              │   src/data/loader.py        │  load_csv() · 校验 OHLCV
              └─────────────────────────────┘
                            ▼
              ┌─────────────────────────────┐
              │ src/features/builder.py     │  build_features() · 共享代码
              │   ├─ technical              │
              │   ├─ volume                 │  → 137 列特征 → drop_features →
              │   ├─ flow                   │  → 129 列输入模型
              │   ├─ market_structure       │  ⚠️ 含 funding_rate/oi/cvd 代理特征
              │   └─ external_fgi           │  ← 加载 data/external/fear_greed_index.csv
              └─────────────────────────────┘
                            │
        ┌───────────────────┴────────────────────────┐
        ▼                                        ▼
  ┌────────────────┐                  ┌──────────────────┐
  │  训练时           │                  │  推理时            │
  │  src/labels/     │                  │  (不生成标签,       │
  │  + splitter      │                  │   纯前向预测)        │
  │  Walk-Forward    │                  │  live_signal.py    │
  │  → model.joblib  │  ── 晋升 ────→   │  → BUY/HOLD/SELL  │
  └─────────────────┘                  └─────────────────┘
                                                  │
                                                  ▼
                                   ┌──────────────────────────┐
                                   │  生产编排 (Cloud Run Job) │
                                   │  deploy/docker_entrypoint │
                                   │  8 步：see §5             │
                                   └──────────────────────────┘
```

---

## 2. 数据源清单

### 2.1 必需（缺了直接挂）

| 源 | API | 字段 | 更新频率 | 落地位置 | 失败兜底 |
|---|---|---|---|---|---|
| **Binance Klines** | `GET https://api.binance.com/api/v3/klines` | `open/high/low/close/volume/quote_volume/trades` | 每日 UTC 00:00 | `data/raw/btc_binance_BTCUSDT_1d.csv` | 容器内若 API 不可用，回退到镜像内打包的旧 CSV，继续推理 |

实现：`src/data/downloader.py::download_binance_klines()`，分页 1000 条/次，自动续接到当前时间。

### 2.2 重要（提供 ~5% 特征重要性，则降级使用但不能移除）

| 源 | API | 字段 | 更新频率 | 落地位置 | 失败兑底 |
|---|---|---|---|---|---|
| **Alternative.me FGI** | `GET https://api.alternative.me/fng/` | `fgi_value` (0-100) + `fgi_class` | 每日 1 次 | `data/external/fear_greed_index.csv` | 12h 缓存；API 挂了用旧缓存；缓存也没有→`ext_fgi*` 全列 NaN，`ffill().dropna()` 后行数减少 |

**生产贡献验证**（基于 promote 时的一次性快照）：

| 模型 | ext_fgi 总 importance (split) | 占比 | 最高排名特征 |
|---|---|---|---|
| E1 | 74 / 1501 | **4.93%** | `ext_fgi_std_14` 排 **#5** |
| E8 | 71 / 1390 | **5.11%** | `ext_fgi_ma30` 排 **#14** |

> ⚠️ **不能从 `model.joblib` 直接复现这些数字**（训练时 ndarray 输入导致 Booster 内部特征名是 `Column_0..128` 占位符）。推荐复现路径：读 `models/production/{name}/feature_importance.csv`（新 promote 后由 `promote_model.py` 冗余复制）+ `feature_cols.json`（供列序交叉验证）。老模型补 promote 后也会有。
>
> P0 隐患状态：已修复，见 §10.1。

**实现**：`src/data/external.py::download_fear_greed_index()` + `src/features/external.py::build_external_fgi_features()`。

### 2.3 已编码但**生产未启用**

> ⚠️ 这些源在代码里有 downloader，但 E1/E8 的 `features.sets` 配置里没用 `external_macro` / `external_fr` 之类的全量 external 特征集。**不要被代码迷惑。**

| 源 | 用途 | 实验编号 | 当前状态 |
|---|---|---|---|
| Yahoo Finance (DXY/VIX/NDX/SPX/Gold/TNX) | 宏观因子 | E11/E12 | 实验劣化，未采用 |
| Binance Futures Funding Rate | 资金费率 | E10/E12 | 实验劣化，未采用 |
| Binance Futures Long/Short Ratio | 情绪 | 未单独实验 | 仅有 downloader |
| CoinGecko (`external_coingecko.py`) | 备用 OHLCV | 实验残留 | 推理路径未引用 |
| External Tier2 (`external_tier2.py`) | 链上指标 (15KB) | 实验残留 | 推理路径未引用 |

**结论**：生产真正用了 **2 个真实外部数据源**：Binance Klines + Alternative.me FGI。其余是研究遗留物。

### 2.4 ⚠️ 名称地雷：伪装成外部数据的 OHLCV 代理特征

`market_structure` 特征集里有几个特征**名称让人以为接了外部 API，实际是 OHLCV 派生**：

| 生产特征名 | 人们以为的来源 | 实际计算 | 在生产的重要性 |
|---|---|---|---|
| `funding_rate_{7,14,24}` | Binance Futures fundingRate API | `close.pct_change().rolling(w).mean() * 100` | **`funding_rate_14` 是 E1 和 E8 的 #1 特征！** |
| `open_interest_{7,14,24}` | Binance Futures openInterest API | `volume.rolling(w).sum()` | E8 中等 |
| `stablecoin_inflow_proxy` | 链上稳定币流入 | `-close.pct_change(7) * volume.rolling(7).mean()` | 低 |
| `cvd*` | 交易所 taker buy/sell delta | `sign(close - open) * volume` 累计 | E1 中等 |

**只要看到这些特征名称主动疑问一下是不是真实数据**。详见 `src/features/market_structure.py`。

真实的 Binance Futures funding rate **确实被下载了**（`data/external/funding_rate_BTCUSDT.csv`），但只被 `external_fr` / `external_macro` 特征集调用，而这些特征集**不在** E1/E8 的 `features.sets` 里。看到 `ext_funding_rate_*` 才是真的。

---

## 3. 数据契约（Schema）

### 3.1 `data/raw/btc_binance_BTCUSDT_1d.csv`

| 列名 | 类型 | 时区 | 说明 |
|---|---|---|---|
| `date` (index) | `datetime64[ns]` | **UTC, naive** | K 线开盘时间 |
| `open` | `float64` | — | |
| `high` | `float64` | — | |
| `low` | `float64` | — | |
| `close` | `float64` | — | 收盘价（=次日 open，因 1d 周期） |
| `volume` | `float64` | — | 基础资产成交量 (BTC) |
| `quote_volume` | `float64` | — | 计价资产成交量 (USDT) |
| `trades` | `int` | — | 成交笔数 |

**校验位置**：`src/data/loader.py::load_csv()` —— 强制小写列名 + 必需列 `{open,high,low,close,volume}` + 去重 + 排序。

### 3.2 `data/external/fear_greed_index.csv`

| 列名 | 类型 | 说明 |
|---|---|---|
| `date` (index) | `datetime64[ns]` | UTC, naive |
| `fgi_value` | `int` | 0-100 |
| `fgi_class` | `str` | "Extreme Fear" / "Fear" / "Neutral" / "Greed" / "Extreme Greed" |

### 3.3 `data/live/signal_state.json`（持仓状态，运行时写）

```json
{
  "in_position": false,
  "entry_date": null,
  "entry_price": null,
  "days_held": 0,
  "last_signal_date": "2026-05-21",
  "last_signal": "HOLD",
  "last_reason": "...",
  "last_regime": "非熊市",
  "last_regime_detail": "63d 滚动收益 = +8.5% (threshold=-10%)",
  "history": [
    {"date": "...", "signal": "...", "price": ..., ...}
  ]
}
```

**Schema 来源**：`scripts/live_signal.py::PositionState` dataclass。

**持久化路径**：
- 本地：`data/live/signal_state.json`
- Cloud Run：`/tmp/state/signal_state.json` ↔ GCS `gs://${STATE_BUCKET}/signal_state.json`

⚠️ **每模型独立一个 state 文件**：生产里 E1 和 E8 各自的 state 在 GCS 不同前缀，避免互相覆盖。本地 launchd 脚本也是各自 `/tmp/signal_state_${MODEL_NAME}.json`。

---

## 4. 训练数据链路

### 4.1 完整流程

```
1. data/raw/btc_*.csv  ──→  load_csv()  ──→  OHLCV DataFrame
                                                    │
2. data/external/*.csv ────┐                        ▼
                           └──→  build_features(sets=[
                                    'technical',        # ~49 列 (RSI/MACD/SMA/EMA/BB/ATR/Stoch/ADX/...)
                                    'volume',           # ~28 列 (OBV/VWAP/MFI/CMF/vol_sma/...)
                                    'flow',             # ~27 列 (taker buy/sell, flow ratio/...)
                                    'market_structure', # ~48 列 ⚠️ 含 funding_rate/oi/cvd 代理
                                    'external_fgi'      # 10 列 (ext_fgi + ma7/14/30 + change_7d/14d + std_14 + extreme*2 + divergence)
                                 ])
                                       │
                                       ▼   137 列原始特征 (5 个集合有少量重叠列被去重)
                           drop_features=[
                             'rsi_*',           # 去 RSI 污染 (与 directional/touch_filtered 的标签过滤同源)
                             'price_vs_sma_*',  # 去 SMA 污染
                             'sma_cross_10_50',
                             'sma_cross_50_200'
                           ]
                                       │
                                       ▼   129 列输入特征 (8 列被 drop)
3. src/labels/{directional|touch}_filtered.py  ──→  label 列 (0/1)
                                       │
                                       ▼
4. ffill().dropna()  ──→  剔除暖机期 + 末尾 T=21 行 (无前瞻)
                                       │
                                       ▼
5. src/data/splitter.py::walk_forward_split(
       init_train=800, oos_window=63, step=21, purge_gap=21
   )  ──→  ~32 folds
                                       │
                                       ▼
6. LightGBM (n_estimators=100, max_depth=6, lr=0.05, seed=42)
   每个 fold 训练一次 → predict OOS → 累计 OOS predictions
                                       │
                                       ▼
7. metrics.json + predictions.csv + model.joblib
                                       │
                                       ▼
8. scripts/pnl_backtest_v0305.py  ──→  pnl_metrics.json (4 个 variant)
                                       │
                                       ▼
9. scripts/promote_model.py  ──→  models/production/{name}/
```

### 4.2 关键超参（E1 = E8）

| 项 | 值 | 来源 |
|---|---|---|
| 数据时间范围 | 2018-01-01 ~ 2025-12-31 | config.yaml `data.start/end` |
| 实际可训样本 | ~2200 行 (扣 ma_window=50 暖机 + T=21 末尾) | — |
| 初始训练集 | 800 行 | config.yaml `evaluation.init_train` |
| OOS 窗口 | 63 天 | `oos_window` |
| 滚动步长 | 21 天 | `step` |
| Purge gap | 21 天 | `purge_gap` |
| 随机种子 | 42 | `seed` |
| LightGBM | 100 树, depth=6, lr=0.05, leaves=31, `auto_scale_pos_weight=True`, `n_jobs=1`（确定性） | `model.params` |

### 4.3 标签生成（E1 vs E8 的唯一差异）

| 维度 | E1 directional_filtered | E8 touch_filtered |
|---|---|---|
| **核心问题** | "21 天后收盘价 ≥ 入场价 ×(1+4%)？" | "未来 21 天**任一天最高价** ≥ 入场价 ×(1+4%)？" |
| 触发条件 | `close[t+T] / close[t] - 1 >= X` | `max(high[t+1..t+T]) >= close[t] * (1+X)` |
| 过滤条件（共同） | `RSI(14) < 45` AND `close < SMA(50)` | 同 E1 |
| 正例率（约） | 13% | 23% |
| 与策略一致性 | ❌ 标签看终点，策略止盈看路径 → 任务和回测脱节 | ✅ 标签和 `--take-profit` 同构 |
| 离线 Kappa | 0.343 | 0.751（**不要跨标签横向比！**） |
| 实现 | `src/labels/directional_filtered.py` | `src/labels/touch_filtered.py` |

> ⚠️ **触达标签的"作弊"性质**：E8 的标签结构与"路径内触达即平仓"的执行规则同构 → 分类指标天然偏高。Kappa 0.751 不代表"模型预测能力是 E1 的 2 倍"，详见 [`models/production/e8-touch/gpt_REVIEW.md`](../../models/production/e8-touch/gpt_REVIEW.md) §2.4。

---

## 5. 生产推理链路（Cloud Run Job · 每日 UTC 00:05）

**入口**：`deploy/docker_entrypoint.sh`，由 Cloud Scheduler 触发，每模型独立 Job。

```
┌─ Step 1: 下载最新数据 ──────────────────────────────────────────┐
│  src.data.downloader.download_binance_klines()                  │
│    → /app/data/raw/btc_binance_BTCUSDT_1d.csv                  │
│  src.data.external.download_fear_greed_index(cache=True)        │
│    → /app/data/external/fear_greed_index.csv                   │
│  [失败兜底] API 挂 → 用镜像内打包的旧 CSV 继续                    │
└─────────────────────────────────────────────────────────────────┘
                                  ▼
┌─ Step 2: 恢复持仓状态 (GCS) ─────────────────────────────────────┐
│  google.cloud.storage SDK:                                       │
│    bucket.blob(prefix+'/signal_state.json')                     │
│         .download_to_filename('/tmp/state/signal_state.json')   │
│  ⚠️ 镜像内未安装 gsutil，全部通过 Python SDK 操作 GCS             │
│  [失败兜底] blob 不存在 → 初始化空仓位                            │
└─────────────────────────────────────────────────────────────────┘
                                  ▼
┌─ Step 3: 运行推理 (live_signal.py) ──────────────────────────────┐
│  3a. load model.joblib + config.yaml                            │
│  3b. fetch_latest_data() → load_csv()                           │
│  3c. prepare_features() → build_features() ※ 与训练同代码        │
│  3d. model.predict_proba(X[-1:])  → bull_prob, bear_prob       │
│  3e. 决策树 (实际嵌套逻辑，非顺序步骤):                          │
│                                                                  │
│     ┌─ Regime 判定 (use_regime=True) ────────────────────────┐  │
│     │ is_bear_market(close, window=63, threshold=-10%)       │  │
│     │   ├─ 熊市 + 持仓 → SELL  (强制平仓, return)           │  │
│     │   └─ 熊市 + 空仓 → SILENT (策略静默, return)          │  │
│     └─────────────────────────────────────────────────────────┘  │
│                          │ 非熊市 (或未启用)                      │
│                          ▼                                       │
│     ┌─ 若 in_position (持仓分支) ────────────────────────────┐  │
│     │ 1) Take-Profit (use_tp=True):                          │  │
│     │      (price-entry)/entry ≥ X  → SELL                  │  │
│     │ 2) 时间到期:                                            │  │
│     │      days_held + 1 ≥ T        → SELL                  │  │
│     │ 3) 否则                       → HOLD                  │  │
│     └─────────────────────────────────────────────────────────┘  │
│                          │ 若 not in_position (空仓分支)         │
│                          ▼                                       │
│     ┌─ 模型预测 ─────────────────────────────────────────────┐  │
│     │ y = model.predict(X[-1:])                              │  │
│     │   ├─ y == 1  → BUY                                    │  │
│     │   └─ y == 0  → SILENT                                 │  │
│     └─────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ⚠️ 关键: TP 只在「持仓」分支检查; 模型预测只在「空仓+非熊市」  │
│     时才发生。空仓时永远不会评估 TP，持仓时永远不会调用模型。   │
│                                                                  │
│  3f. 更新 PositionState → 写回 /tmp/state/signal_state.json     │
└─────────────────────────────────────────────────────────────────┘
                                  ▼
┌─ Step 4: 上传状态到 GCS ────────────────────────────────────────┐
│  google.cloud.storage SDK:                                       │
│    bucket.blob(prefix+'/signal_state.json')                     │
│         .upload_from_filename('/tmp/state/signal_state.json')   │
└─────────────────────────────────────────────────────────────────┘
                                  ▼
┌─ Step 5: 生成信号 JSON (build_signal_json.py) ──────────────────┐
│  读 manifest.json → 拼模型元信息 (name, Kappa, CAGR, MaxDD…)    │
│  读 signal_state.json → 拼信号 + 持仓 + 历史                     │
│  写 /tmp/signals/signal_{model}_{date}.json                    │
└─────────────────────────────────────────────────────────────────┘
                                  ▼
┌─ Step 6: LLM 增强 (可选, enrich_llm_analysis.py) ───────────────┐
│  if GEMINI_API_KEY: 调用 Gemini 生成自然语言信号解读              │
│  失败不阻塞                                                       │
└─────────────────────────────────────────────────────────────────┘
                                  ▼
┌─ Step 7: 发送邮件 (send_signal_email.py) ───────────────────────┐
│  if SMTP_USER & SMTP_PASS: 渲染 HTML → smtplib 推送              │
│  失败不阻塞                                                       │
└─────────────────────────────────────────────────────────────────┘
                                  ▼
┌─ Step 8: 上传信号 JSON 到 GCS ──────────────────────────────────┐
│  google.cloud.storage SDK: 对 /tmp/signals/signal_*.json 循环   │
│    bucket.blob(prefix+'/signals/'+filename)                     │
│         .upload_from_filename(local_path)                       │
│  失败不阻塞                                                       │
└─────────────────────────────────────────────────────────────────┘
```

**关键环境变量**：

| 变量 | 必需 | 说明 |
|---|---|---|
| `MODEL_NAME` | ✅ | `e1-conservative` / `e8-touch` |
| `STRATEGY_VARIANT` | 默认 `conservative` | `base` / `moderate` / `conservative` → 控制 `--take-profit` / `--regime-switch` flag |
| `STATE_BUCKET` | 推荐 | GCS 桶（如 `gs://fcstlab-state/e1`），无则 stateless（每次冷启动） |
| `GEMINI_API_KEY` | 可选 | 启用 LLM 增强 |
| `SMTP_USER` / `SMTP_PASS` | 可选 | 启用邮件推送 |

---

## 6. 训练 ↔ 推理的同构保证

**这是项目的最大优势**，没人在文档里夸过，这里专门写一下：

| 环节 | 训练代码 | 推理代码 | 同构？ |
|---|---|---|---|
| 数据加载 | `src.data.loader.load_csv()` | `src.data.loader.load_csv()` | ✅ 完全相同 |
| 数据下载 | `src.data.downloader.download_binance_klines()` | 同左 | ✅ |
| 特征构建 | `src.features.builder.build_features(sets, drop_features)` | 同左 | ✅ |
| 特征顺序 | `get_feature_columns(df)` 按 DataFrame 列序 | 同左，两端都以 ndarray 传入 LightGBM | ✅ `live_signal.py:validate_feature_cols()` 启动时逐位校验 `feature_cols.json`，错位 → ValueError（§10.1） |
| 标签生成 | `src.labels.{strategy}.generate_*_labels()` | **不生成**（推理只 predict） | N/A |
| 缺失值处理 | `ffill().dropna()` | 同左 | ✅ |

**唯一的潜在风险点**：
- **暖机数据不足**：推理只拉 400 天历史（`live_signal.py::fetch_latest_data` 在线模式），但 SMA(50) + 各种 rolling 需要 ~50 天暖机 → 400 天够用。
- **数据延迟**：Binance 日线 K 在 UTC 00:00 收盘，Cloud Run 在 UTC 00:05 跑，5 分钟缓冲足够。
- **FGI 缺失**：当天 FGI 还没出 → `ffill` 用昨天的值 → 不会挂，但有 1 天滞后。

---

## 7. 数据健康检查

**主动监控**：`scripts/check_data_health.py`

```bash
python scripts/check_data_health.py
# 检查：
# 1. Binance CSV 存在 + 最新日期距今 ≤ 2 天
# 2. FGI CSV 存在 + 最新日期距今 ≤ 2 天
# 3. 列完整性 + NaN 比例
```

**被动监控**：推理脚本日志中会打印：
- `数据加载完成: btc_binance_BTCUSDT_1d.csv, 时间范围 2020-01-01 ~ 2026-05-21, 共 2333 条`
- `Regime: 63d 滚动收益 = -3.2%`
- `BUY/HOLD/SELL` + reason

建议接入 Cloud Logging 告警：
- 推理 Job 退出码 ≠ 0
- 日志含 "❌"
- 连续 2 天未触发（Scheduler 挂了）

---

## 8. 故障模式与回退

| 故障 | 影响 | 自动兜底 | 人工处置 |
|---|---|---|---|
| Binance API 限流 / 挂 | 数据无更新 | 用镜像内打包的旧 CSV 继续推理（信号会基于陈旧数据） | 重跑 Job；持续挂需切到备用源 |
| FGI API 挂 | `ext_fgi*` 全列陈旧 | 12h 缓存；超期用最旧缓存 | 接受 1-2 天滞后 |
| GCS state 丢失 | 模型不知道有持仓 | 初始化为空仓 → 可能错过 SELL | 从 `signal_*.json` 历史人工重建 state |
| Cloud Scheduler 失效 | Job 不触发 | 无 | launchd 本地脚本作 backup |
| `manifest.json` 缺字段 | `build_signal_json.py` 拼信号失败 | hardcoded fallback (`v0305`, `129 features`) | 修 manifest，重跑 |
| LightGBM 版本漂移 | 数值不一致 | Docker 锁版本 | 重新 promote 一次 |

---

## 9. 数据合规与隐私

- ✅ **公开数据源**：Binance / Alternative.me 均为公开行情/情绪数据
- ✅ **无 PII**：项目不涉及任何用户/个人数据
- ❌ **不要把 GCS bucket 设公开**：`signal_state.json` 含历史持仓动作，泄露 = 暴露策略

---

## 10. 已知技术债

| 优先级 | 问题 | 位置 |
|---|---|---|
| ✅ 已修复 (2026-05) | ~~**模型未持久化真实特征名，train↔serve 静默列错位风险**~~ —— 详见 §10.1 修复记录 | §10.1 |
| ✅ 已修复 (2026-05) | ~~`promote_model.py` 未输出 `feature_importance.csv`~~ —— 现同步复制实验目录产物 (`promote_model.py:files_to_copy`)。老模型补 promote 后有。 | `scripts/promote_model.py` |
| 🟡 中 | RSI/SMA 计算复制 3 份 | `labels/directional_filtered.py`, `labels/touch_filtered.py`, `features/technical.py` |
| 🟡 中 | `manifest.json` 里 `features.count` 是字符串 `"129 (after decontamination)"`，需 split 才能拿到数字 | `scripts/build_signal_json.py:52` |
| 🟢 低 | 推理时 `--take-profit` 用的 `X` 来自 `config.yaml` 的 label.X，逻辑上是"标签的目标涨幅"被复用为"策略的止盈幅"——巧合且合理但要标注 | `live_signal.py` |
| 🟢 低 | `external_coingecko.py` / `external_tier2.py` 是研究残留，未在生产路径调用 | `src/data/` |

详见 [`CLAUDE.md`](../../CLAUDE.md) §8.2 和 [`../cr_0308_reusability.md`](../cr_0308_reusability.md)。

### 10.1 修复记录: train↔serve 列错位 P0 (2026-05)

**问题描述**: 训练 (`runner.py:176 X = df[feature_cols].values`) 与推理 (`live_signal.py:220 .iloc[[-1]].values`) 都以 ndarray 传入 LightGBM，导致 `model.feature_names_in_ = ['Column_0', ..., 'Column_128']`，真实名（如 `ext_fgi_std_14`）从未被保存。实测列序随机打乱后 `predict_proba` 输出从 `[0.990, 0.010]` 变为 `[0.999, 0.001]`，**stderr 零警告**。

**为何换思路修复**: 原计划是训练与推理都传 DataFrame、让 sklearn 自动按 `feature_names_in_` 重排。实验后发现（见 `tests/test_lgbm_quirks.py`）**LightGBM sklearn wrapper 不遵守 sklearn 列名校验约定**——传 DataFrame 也会被当 ndarray 处理，`feature_names_in_` 仅作为标签摆设，推理时不参与对齐。所以改为显式外层校验。

**修复方案**：

| # | 文件 | 改动 |
|---|---|---|
| 1 | `src/experiment/runner.py` | 训练后额外写 `feature_cols.json`（版本 + `n_features` + 列名列表 + sha256） |
| 2 | `scripts/promote_model.py` | `files_to_copy` 增加 `feature_cols.json` + `feature_importance.csv`；manifest 嵌入 `feature_cols_sha256` 交叉验证 |
| 3 | `scripts/live_signal.py` | 新增 `validate_feature_cols()`：加载后逐位比较训练快照 → 不一致 raise `ValueError` (带错位 index) → JSON 不存在则 loud warning (向后兼容) |
| 4 | `scripts/bootstrap_feature_cols.py` (新) | 一次性脚本，按当前 config.yaml 重跑 `build_features()`、为老生产模型回填 `feature_cols.json` |
| 5 | `tests/test_feature_cols_validation.py` (新) | 6 个测试：一致通过 / 缺失警告 / 长度错 / 顺序错 / 重命名错 / sha256 结构 |
| 6 | `tests/test_lgbm_quirks.py` (新) | 4 个测试锁定 LightGBM quirk（bit-exact / 名保留 / 不校验乱顺序 / 不校验错名）——未来上游修复了会失败提醒 |

**验证**：

```bash
# 单元测试 (10/10 pass)
python -m pytest tests/test_feature_cols_validation.py tests/test_lgbm_quirks.py -v

# 端到端 smoke (正常路径 — 应当看到 "✅ 特征列序校验通过")
python scripts/live_signal.py --dry-run

# 负向验证 (篡改 JSON 后推理应 raise ValueError, exit code != 0)
# 代码见本代码提交信息里的验证脚本
```

**设计权衡记录**：

- 为什么不改 `runner.py` 用 DataFrame fit？ 实测（`test_ndarray_fit_and_dataframe_fit_are_bit_exact`）证明两者结果 bit-exact，改了无数值副作用。但也无额外收益（LightGBM 不按名校验），反而引入老模型加载时的兼容复杂度，所以本轮 scope 不动。未来重新 train 时可以顺手改，让 `feature_importance` 能直接拿到真名（§2.2 审计体验的 bonus）。
- 为什么 `feature_cols.json` 同时存 `sha256`？ 作为文件篡改检测。manifest 里复制一份 `feature_cols_sha256`，两者不一致则快照被动过。目前仅作为可审计字段，未在 `validate_feature_cols()` 里强制校验（需求不足）。
- 为什么缺失 JSON 仅 warning 不阻断？ 向后兼容老 promote 的模型。预期下一轮 promote 后所有模型都有 JSON，那时可以把警告升级为硬性报错。

---

## 11. 复现性验证

任何对 `src/data/` 或 `src/features/` 的修改后，必须验证：

```bash
# 1. 重跑 E1
python scripts/run_experiment.py --config models/production/e1-conservative/config.yaml --overwrite

# 2. 对比 predictions 必须逐行一致
diff models/production/e1-conservative/predictions.csv \
     experiments/weekly/{重跑目录}/predictions.csv

# 3. metrics.json 必须 bit-exact
diff models/production/e1-conservative/metrics.json \
     experiments/weekly/{重跑目录}/metrics.json

# E8 同理
```

**特征列序快照交叉验证**（§10.1 修复后增加）：

```bash
# 重跑后的 feature_cols.json sha256 应与生产一致。不一致 = features 代码发生了漂移。
python -c "import json; \
  prod = json.load(open('models/production/e1-conservative/feature_cols.json')); \
  new = json.load(open('experiments/weekly/{重跑目录}/feature_cols.json')); \
  assert prod['sha256'] == new['sha256'], f'特征列序变了! prod={prod[\"sha256\"][:12]}, new={new[\"sha256\"][:12]}'; \
  print('✅ feature_cols.json bit-exact')"
```
**已验证基线**（2026-03-08）：

| 模型 | Accuracy | Kappa | F1 | 状态 |
|---|---|---|---|---|
| E1 | 0.8733 | 0.3433 | 0.4142 | ✅ bit-exact |
| E8 | 0.9226 | 0.7512 | 0.7991 | ✅ bit-exact |

详见 [`CLAUDE.md`](../../CLAUDE.md) §5.3。

---

*维护者：FcstLabPro 核心组 · 反馈请提 issue 或更新本文件*
