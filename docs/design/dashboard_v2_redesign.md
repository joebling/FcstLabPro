# Dashboard 重新设计 (V2) — 借鉴 QuantDinger

> **日期**: 2026-05-29
> **作者**: sam (code-puppy)
> **参考**: QuantDinger (github, 商业级 self-hosted 量化 OS)
> **取代**: V1 单页 performance 表 (`dashboard_architecture.md`)
> **不变**: 后端纯展示层 + 实时算+TTL缓存 + 真相源 = archive/OHLCV/external

---

## 0. 为什么要重做

V1 dashboard 只有「一张 performance 表 + 5 个 KPI」，确实太单薄。
QuantDinger 的 dashboard 给了三个值得学的东西：

1. **侧边栏多页导航** — 不是一锅烩在单页，按功能分页 (Dashboard / 分析 / 设置)
2. **信息密度高但有层次** — KPI 卡片行 + 多个图表卡片网格，一眼看全貌
3. **专业视觉语言** — 渐变主卡片、图标、环形图、日历热力图、彩色涨跌

但 QuantDinger 是**重量级商业产品** (多券商实盘 + Postgres/Redis + 多租户计费 +
13 个 AI agent + 多语言)。**我们绝不照抄那个体量** — 那违反 YAGNI。
我们抄的是**设计语言和信息架构**，不是它的功能广度。

---

## 1. 边界：抄什么，不抄什么

### ✅ 抄 (设计语言 / 信息架构)

| QuantDinger 元素 | 我们怎么用 |
|---|---|
| 侧边栏多页导航 | 分 4 页: 总览 / 信号 / 市场 / 模型 |
| 渐变主 KPI 卡 + 卡片网格 | 总览页顶部 KPI 行 |
| 环形图 (Strategy Allocation) | 信号分布 / regime 占比 |
| Profit Calendar 日历热力图 | 信号日历 (哪天发了 BUY/SILENT + 实现盈亏) |
| Drawdown Curve / 时序图 | 价格+信号叠加图、IC 时序 |
| 涨跌红绿 + 图标语言 | 全站统一 (用 Walmart 色) |

### ❌ 不抄 (超出单人 BTC 信号项目)

| QuantDinger 功能 | 为什么不要 |
|---|---|
| 多券商实盘下单 | 我们不下单, 只发信号 |
| Postgres + Redis | 文件足够, 信号量极小 |
| 多用户 / RBAC / 计费 | 单人自用 |
| 13 个 AI agent roster | 我们就 2 个模型 |
| 指标 IDE / 策略编辑器 | 研究在 CLI/notebook 做 |
| 实时 KLine 交易图表 | 日线信号, 不需要盘口 |

**一句话**: 抄它的「皮相」(布局/视觉/信息密度)，不抄它的「骨架」
(实盘/数据库/多租户)。后端依然是纯展示层 + 文件真相源。

---

## 2. 我们手里有什么数据 (决定能做几页)

盘点现有数据源 (都是文件, 无需新增采集)：

| 数据源 | 路径 | 能驱动什么 |
|---|---|---|
| 信号 archive | `data/signals/archive/{model}/*.json` | 信号历史、回填实现结果 |
| OHLCV | `data/raw/btc_binance_BTCUSDT_1d.csv` | 价格图、信号叠加 |
| 持仓状态 | `data/live/{model}_state.json` | 当前持仓、浮盈 |
| Paper trading | `data/live/paper_trading/*.json` | 双模型对比、共识 |
| FGI | `data/external/fear_greed_index.csv` | 市场情绪 |
| Funding rate | `data/external/funding_rate_BTCUSDT.csv` | 资金费率 |
| Long/short ratio | `data/external/long_short_ratio_BTCUSDT.csv` | 多空比 |
| Open interest | `data/external/open_interest_BTCUSDT.csv` | 持仓量 |
| Macro factors | `data/external/macro_factors.csv` | 宏观 |
| active.yaml + manifest | `models/production/` | 模型谱系、角色、状态 |
| performance (Layer P) | 实时算 (已建) | 命中率、IC、实现收益 |

**结论**: 数据足够撑起 4 个有内容的页面，不是硬凑。

---

## 3. 页面架构 (4 页)

```text
┌─ 侧边栏 ──────┐  ┌─ 主内容区 ───────────────────────────┐
│ 📊 总览        │  │  当前页内容 (KPI 行 + 卡片网格)         │
│ 📡 信号        │  │                                        │
│ 📈 市场        │  │                                        │
│ 🤖 模型        │  │                                        │
│ ─────────     │  │                                        │
│ 模型: [E1 ▼]  │  │                                        │
└──────────────┘  └────────────────────────────────────────┘
```

### 页 1: 📊 总览 (Overview)

**一眼看全貌**，对标 QuantDinger Dashboard 首页。

- **KPI 行** (渐变主卡 + 普通卡):
  - 最新信号 (BUY/SILENT + 渐变主卡, 最醒目)
  - 当前价格 (+ 今日涨跌)
  - 命中率 (近 30 成熟信号)
  - Rank IC
  - 当前 regime (牛/熊/震荡)
  - 模型状态 (primary live / challenger paper)
- **信号日历** (对标 Profit Calendar): 当月每天标 BUY🟢/SILENT⚪ + 实现盈亏色块
- **价格 + 信号叠加图** (Chart.js): 价格线 + BUY 标记点
- **信号分布环形图**: BUY vs SILENT 占比

### 页 2: 📡 信号 (Signals)

**信号的完整生命周期**，把 V1 的表升级。

- 当前信号大卡 (信号/价格/regime/reason/持仓/浮盈)
- 信号实现明细表 (= V1 那张, 命中率/实现收益/三态)
- 双模型对比 (E1 vs E8 共识, 来自 paper_trading)
- IC / 命中率时序图

### 页 3: 📈 市场 (Market)

**市场环境上下文**，这是 V1 完全没有的。

- 价格 + 成交量图
- FGI 情绪计 (环形/仪表盘, 含分类 Fear/Greed)
- 资金费率时序
- 多空比 + 持仓量
- regime 判定历史 (牛熊切换时间线)

### 页 4: 🤖 模型 (Models)

**模型治理可视化**，把 active.yaml/manifest 摆出来。

- 模型卡 (primary / challenger): 名称/角色/variant/status/hash
- 回测指标 (CAGR/Sharpe/MaxDD/Kappa, 来自 metrics/pnl_metrics)
- 模型谱系 (来源实验、git commit、晋升时间, 来自 manifest)
- 数据新鲜度门状态 (OHLCV/FGI stale 检查)

---

## 4. 技术架构 (后端不变, 前端升级)

### 4.1 维持的原则

- **纯展示层**: 只读, 不碰模型, 不下单, 不影响信号生成
- **实时算 + TTL 缓存**: 沿用 `src/performance/cache.py`
- **真相源 = 文件**: archive / OHLCV / external / models
- **无前端构建**: Tailwind + Chart.js + HTMX 走 CDN

### 4.2 目录结构演进

```text
src/dashboard/
  app.py                 # FastAPI (不变)
  config.py              # 配置 (不变)
  data/                  # 新增: 数据读取层 (按领域拆)
    signals.py           #   信号 archive 读取 + 聚合
    market.py            #   OHLCV + external 读取
    models.py            #   active.yaml + manifest 读取
    performance.py       #   调 src/performance (已有)
  routes/
    pages.py             # ★ 4 页路由
    partials.py          # ★ HTMX 局部 (图表/表格刷新)
  templates/
    base.html            # ★ 加侧边栏导航
    pages/
      overview.html      #   总览
      signals.html       #   信号
      market.html        #   市场
      models.html        #   模型
    partials/            # 可复用 fragment (KPI卡/图表/表格)
      kpi_card.html
      signal_table.html
      price_chart.html
      ...
  static/
    app.css              # ★ 扩展: 侧边栏/卡片/渐变样式
    charts.js            # 新增: Chart.js 封装 (DRY)
```

**行数纪律**: 每个 data/*.py 和 template < 200 行。拆分而非堆积。

### 4.3 复用现有资产

- `src/performance/` — 回填闭环 + 缓存, 直接用
- `src/serving/active_config.py` — 读 active.yaml
- 不重复造轮子: OHLCV 读取复用 `src/performance/backfill.load_ohlcv`

---

## 5. 视觉规范 (QuantDinger 蓝紫渐变 + WCAG AA)

> **决策 (owner)**: 采用 QuantDinger 的蓝紫渐变科技风, 不用 Walmart 色系。
> 这是个人自用项目的 dashboard, 不是 Walmart 交付物, 可以走更酷的风。

| 元素 | 色值 |
|---|---|
| 主渐变 (主卡/按钮) | `#4f46e5` → `#7c3aed` (indigo→violet) |
| 主色 | indigo.600 `#4f46e5` |
| 强调/高亮 | violet.500 `#8b5cf6` |
| 涨/成功/BUY | emerald.500 `#10b981` |
| 跌/错误 | rose.500 `#f43f5e` |
| 警示 | amber.500 `#f59e0b` |
| 背景 | slate.50 `#f8fafc` |
| 卡片 | white + slate.200 边框 |
| 文字 | slate.800 `#1e293b` / slate.500 次级 |
| 侧边栏 | white, 当前页 indigo 左边框 + 浅 indigo 背景 |

- 涨跌不只靠红绿 (配 ▲▼ 箭头) → 色盲友好
- 对比度 ≥ 4.5:1
- 渐变只用于最重要的主卡 (最新信号), 避免滥用

---

## 6. 实施顺序 (增量, 每页可独立验证)

| 步 | 任务 | 验证 |
|---|---|---|
| **R-1** | 拆 data 层 (signals/market/models/performance) + 单测 | pytest |
| **R-2** | base.html 加侧边栏 + 4 页骨架路由 | 4 页都能打开 |
| **R-3** | 总览页 (KPI 行 + 信号日历 + 叠加图 + 环形图) | 浏览器看 |
| **R-4** | 信号页 (升级 V1 表 + 双模型对比 + IC 图) | 浏览器看 |
| **R-5** | 市场页 (价格/FGI/funding/多空比) | 浏览器看 |
| **R-6** | 模型页 (卡片 + 指标 + 谱系 + 新鲜度门) | 浏览器看 |
| **R-7** | charts.js 抽公共图表逻辑 (DRY) | 重构后回归 |
| **R-8** | 更新 DASHBOARD_GUIDE + 部署验证 | VPS |

**R-1 + R-2 是地基** (数据层 + 导航壳)，之后每页独立做、独立提交。

---

## 7. YAGNI 边界 (明确不做)

| 不做 | 原因 |
|---|---|
| 数据库 | 文件够 |
| 用户系统 | 单人 |
| 实时 KLine / WebSocket | 日线信号 |
| 实盘下单按钮 | 只发信号 |
| 指标/策略编辑器 | 研究在 CLI |
| AI agent roster | 就 2 个模型 |
| 多语言 i18n | 单人用中文 |
| 移动端专门优化 | 自己 SSH 隧道看, 桌面为主 |

---

## 8. 与 V1 的关系

- V1 的 performance 表 → 并入「信号页」, 不丢
- V1 的 `data_access.py` → 重构为 `data/` 子模块 (按领域拆)
- V1 的实时算+缓存 → 完全保留
- V1 的 systemd 部署 → 不变

**V1 不是白做**: 它的后端闭环 (Layer P) 是这次的数据基石之一。
这次是「前端从单页扩成多页 OS 风格」，后端只是按领域拆得更干净。

---

*本方案保存于 docs/design，等 owner review 后再决定实施范围与优先级。*
*实施时严格遵循增量提交 + 每页独立验证。*
