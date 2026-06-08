# Performance Tracking 设计方案

> **日期**: 2026-05-29
> **作者**: sam (code-puppy)
> **参考**: RiskDetect `app/services/perf/sellers.py` + `partials/perf_sel.html`
>           的 "Score Batch Detail (Last 30)" 表格
> **关联**: `docs/reviews/cr_0529_model_governance_vs_riskdetect.md` §9 (monitoring)
> **现状基线**: `src/serving/signal_ledger.py`

---

## 0. 一句话结论

FcstLabPro 已经能记录「我预测了什么」(signal_ledger)，但**没有闭环**
「这个预测后来对没对」。RiskDetect 那张表的灵魂不是好看，而是它把
**预测 → 真实结果**闭环了：每个打分批次等标签成熟后回填算 AUC / 命中率。

**要做的核心是补上这条回填闭环**，而不是先去画页面。

---

## 1. 先看 RiskDetect 凭什么做得好

拆解 `Score Batch Detail (Last 30)` 这张表，它有 4 个值得抄的设计决策：

### 1.1 「批次」是第一公民

每行 = 一个 `score_date` 批次，不是单条预测。聚合到批次级别后：
- 行数可控 (Last 30)，人眼可扫
- 每批有分布 (critical/high/medium/low 计数 + C+H%)
- 趋势一眼可见 (批次按日期倒序)

### 1.2 标签成熟度门控 (`AUC_MIN_LAG_DAYS = 60`)

**这是最关键的设计**。它不会拿「还没到结果的预测」去算准确率：

```python
# 只评 60 天前的批次 —— 给"执法动作"时间真正发生
WHERE s.score_date <= CURRENT_DATE - (:lag || ' days')::interval
```

未成熟的批次在表里显示 `⏳`，而不是误导性的数字。**FcstLabPro 必须照搬这个思路**：
预测窗口 T=21 天，那 21 天内的信号根本没法判定对错。

### 1.3 双指标：排序能力 + 实际命中

- **AUC**: 模型区分好坏的排序能力 (连续概率层面)
- **Critical Term%**: 高危预测里真正出事的比例 (决策层面)

两个指标一个看「模型聪不聪明」，一个看「拍板准不准」。互补。

### 1.4 常量单一真相源 + 防漂移注释

```python
# AUC_MIN_LAG_DAYS 被 bad_cases/candidates.py 复用,
# 不许各自重定义 —— drift here = silently inconsistent numbers
AUC_MIN_LAG_DAYS = 60
```

DRY 不是口号，是「同一个口径只能有一个出处」。

---

## 2. FcstLabPro 的现状缺口

| RiskDetect 有 | FcstLabPro 现状 | 缺口 |
|---|---|---|
| 批次聚合表 | signal_ledger 单条记录 | ❌ 无批次/历史聚合视图 |
| 标签成熟门控 (60d lag) | 无 | ❌ 无成熟度概念 |
| AUC 回填 | 无 | ❌ 预测从不回填结果 |
| 命中率 (Term%) | history.win_rate (仅 paper) | 🟡 有但只在 paper、不分批 |
| 防漂移常量 | 无 | ❌ T/lag 散落各处 |
| Web 表格 | 无 (纯 JSON) | 🟡 可选，非核心 |

**核心缺口一句话**：信号写进 archive 后就「死」在那了，没有任何机制回来问
「2026-05-01 那批 BUY 信号，21 天后 BTC 到底涨没涨？」

---

## 3. 设计方案

### 3.1 分层 (严守项目 Layer 0-5 纪律)

```text
Layer 0  数据层   —— OHLCV 真实未来价格 (回填的真相来源)
─────────────────────────────────────────────
新增: Layer P (Performance) —— 介于 serving 与 reporting 之间
  P.1  outcome 回填   signal_ledger archive + 未来价格 → 实现结果
  P.2  批次聚合       按 score_date / model 聚合 + 成熟度门控
  P.3  指标计算       hit_rate / realized_return / IC / (可选 AUC)
  P.4  报告产物       JSON + 可选 flat HTML 表格
```

**关键纪律**: Layer P 只读 signal_ledger archive + 真实 OHLCV，
**绝不**反向影响信号生成 (否则就成了 look-ahead 污染)。

### 3.2 成熟度门控 (照搬 RiskDetect 精髓)

预测窗口是 T 天 (E1/E8 都是 21)，所以：

```python
# src/performance/maturity.py
from src.serving.active_config import load_active_models

# 单一真相源: 成熟滞后 = 标签窗口 T + 执行延迟 buffer
# T 从 model config 读, 不硬编码 (防漂移)
def maturity_lag_days(model_cfg: dict) -> int:
    T = model_cfg["label"]["T"]          # 21
    exec_buffer = 1                       # t close → t+1 open
    return T + exec_buffer                # 22
```

- 批次 `score_date > today - lag` → 状态 `PENDING` (显示 ⏳)
- 否则 → `MATURE`，可计算实现结果

### 3.3 回填逻辑 (P.1)

```python
# src/performance/backfill.py
def backfill_outcomes(model_name: str, ohlcv: pd.DataFrame) -> list[dict]:
    """对每条 archive 信号, 算 T 天后的实现结果."""
    records = load_archive(model_name)          # signal_ledger archive
    out = []
    for rec in records:
        d = rec["date"]
        if not is_mature(d, model_name):
            out.append({**slim(rec), "status": "PENDING"})
            continue
        entry = ohlcv.loc[d, "open_next"]        # t+1 open (执行假设一致)
        exit_ = ohlcv.loc[d + T, "close"]
        realized_ret = exit_ / entry - 1
        out.append({
            **slim(rec),
            "status": "MATURE",
            "realized_return": realized_ret,
            # 信号方向对了吗? BUY 且涨 = hit
            "hit": int((rec["signal"] == "BUY") == (realized_ret > 0)),
        })
    return out
```

**执行假设必须与 PnL 回测一致** (`next_open`)，否则 live 和 backtest 数字对不上。

### 3.4 批次聚合 + 指标 (P.2 / P.3)

```python
# src/performance/aggregate.py  ——  对标 RiskDetect batches()
def batches(model_name: str, limit: int = 30) -> list[dict]:
    rows = backfill_outcomes(model_name, load_ohlcv())
    by_date = groupby(rows, "date")
    out = []
    for d, recs in sorted(by_date, reverse=True)[:limit]:
        mature = [r for r in recs if r["status"] == "MATURE"]
        out.append({
            "score_date": d,
            "n_signals": len(recs),
            "n_buy": sum(r["signal"] == "BUY" for r in recs),
            # 成熟批次才有这些, 否则 None → 页面显示 ⏳
            "hit_rate": pct(mean(r["hit"] for r in mature)) if mature else None,
            "avg_realized_return": mean(r["realized_return"] for r in mature)
                                   if mature else None,
            "status": "MATURE" if mature else "PENDING",
            "model_hash": recs[0]["provenance"]["model_hash"],  # 切版追溯
        })
    return out
```

加一个 **rolling IC** (符合机构手册 §2.3 的 Rank IC 门槛):

```python
# 把每批的 (signal_prob, realized_return) 累积, 算 Spearman
# 这是手册要求的 Rank IC, 直接对齐已有统计准则
rolling_rank_ic(probs, returns)   # 复用 scripts/ic_analysis_corrected.py 逻辑
```

### 3.5 防漂移常量 (照搬 RiskDetect 的注释纪律)

```python
# src/performance/constants.py
# ⚠️ 成熟度滞后从 model config 的 label.T 推导, 不在此硬编码。
# 任何需要"标签成熟"概念的地方 (回填/聚合/报告) 必须 import maturity_lag_days,
# 不许各自 +21 +22 —— drift here = 各页面数字静默不一致。
EXEC_BUFFER_DAYS = 1   # t_close signal → t+1_open execute
```

---

## 4. 产物结构

```text
data/live/performance/
  {model_name}/
    batches.json          # Last N 批次聚合 (页面/邮件直接吃)
    outcomes.csv          # 全量回填明细 (审计 + 重算)
    summary.json          # 滚动 hit_rate / IC / realized Sharpe
reports/performance/
  {date}.html             # 可选: flat HTML + Chart.js (对标那张表)
```

### batches.json 示例 (对标 Score Batch Detail)

```json
[
  {
    "score_date": "2026-05-01",
    "n_signals": 1,
    "n_buy": 1,
    "hit_rate": 100.0,
    "avg_realized_return": 0.038,
    "rolling_ic_30": 0.041,
    "status": "MATURE",
    "model_hash": "98c85910"
  },
  {
    "score_date": "2026-05-20",
    "n_signals": 1,
    "n_buy": 0,
    "hit_rate": null,
    "avg_realized_return": null,
    "status": "PENDING"
  }
]
```

---

## 5. 可选: Web 表格 (对标 perf_sel.html)

按 Walmart 规则: 简单 BQ/信息类 → flat HTML + HTMX + Tailwind + Chart.js。
本场景数据量小、读多写少，**flat HTML 单文件即可**，不需要 FastAPI。

抄 RiskDetect 那张表的 3 个交互细节:
1. **in-cell data bar** (`--bar` CSS 变量按列最大值归一) —— 分布一眼可见
2. **成熟度三态显示**: `⏳` (PENDING) / `—` (无数据) / 彩色数字 (有结果)
3. **颜色门槛对齐手册**: IC ≥ 0.02 绿 / hit_rate ≥ 55% 绿 (用 Walmart 色板)

> 颜色用 Walmart 色: green.100=#2a8703 (达标) / spark.140=#995213 (警示) /
> red.100=#ea1100 (差)。WCAG AA 对比度。

---

## 6. 实施优先级 (增量, 不破坏现有)

| 阶段 | 任务 | 价值 | 依赖 |
|---|---|---|---|
| **P-1** | `maturity.py` + `backfill.py` (回填闭环) | 🔴 核心 | signal_ledger (已有) |
| **P-2** | `aggregate.py` (批次表 JSON) | 🔴 核心 | P-1 |
| **P-3** | rolling IC 接入 (复用现有 ic 脚本) | 🟠 对齐手册 | P-2 |
| **P-4** | flat HTML 报告页 | 🟡 体验 | P-2 |
| **P-5** | 接入 pipeline (每日自动回填) | 🟡 自动化 | P-2 |

**P-1 + P-2 就能回答最重要的问题**:「我的 live 信号到底准不准」。
P-4 的页面是锦上添花。

---

## 7. 为什么这样设计能方便迭代模型

这正是你的核心诉求。闭环建好后:

1. **新模型 shadow 验证有了客观标尺**: 不再靠回测自夸，
   而是 shadow 跑一段 → 看 live batches.json 的 hit_rate / IC 是否真的更好。
2. **切版影响可追溯**: 每批带 `model_hash`，换模型后能直接对比
   「换版前后 30 批的实现结果」，而不是凭感觉。
3. **回测 vs 实盘 gap 可量化**: backfill 用和 PnL 回测一致的执行假设，
   实现 return 与回测 return 的系统性偏差 = 成本/滑点/regime 漂移的真实代价。
4. **promotion gate 可加硬门**: 未来可要求「challenger 的 live IC ≥ primary」
   才允许晋升 —— 把 cr_0529 §5 的 shadow gate 落到实处。

---

## 8. YAGNI 边界 (明确不做)

| 不做 | 原因 |
|---|---|
| 数据库 (Postgres) | 信号量极小 (每天每模型 1 条)，文件系统够用 |
| 实时 streaming 监控 | daily 模型，每日批处理足矣 |
| SHAP / 可解释性面板 | 另一个独立议题，不混入 perf tracking |
| 多资产对比表 | 当前只 BTC，先做扎实 |
| FastAPI 服务 | 读多写少 + 数据量小，flat HTML 更轻 |

---

## 9. 与现有代码的衔接点

- **输入**: `src/serving/signal_ledger.py` 的 archive (已在写, 带 provenance)
- **真相**: `data/raw/btc_binance_BTCUSDT_1d.csv` (回填用的未来价格)
- **复用**: `scripts/ic_analysis_corrected.py` 的 Rank IC 计算逻辑
- **配置**: `models/production/active.yaml` (拿 active 模型列表) +
  各 model `config.yaml` 的 `label.T` (推导成熟度滞后)
- **执行假设**: 与 `scripts/pnl_backtest_v0305.py` 的 `next_open` 对齐

---

*本方案保存于 docs/design，等 owner review 后再决定是否进入实施。*
*实施时严格遵循 experiment_sop.md 的复现守门 + 增量提交纪律。*
