# 周期研判页 (`/cycle`) 设计文档

> 版本: v1.0 (2026-06-09)
> 维护: FcstLabPro 核心架构组
> 关联代码: `src/dashboard/data/{cycle,topping,bottoming,cycle_core}.py`,
>           `src/dashboard/templates/pages/cycle.html`,
>           `src/dashboard/templates/partials/playbook_{top,bottom}.html`
> 实证依据: `docs/reports/btc_topping_ic_analysis_20260608.html`,
>           `docs/reports/btc_bottoming_ic_analysis_20260608.html`

---

## 1. 一句话概述

`/cycle` 是 FcstLabPro dashboard 的 **唯一周期研判入口**。它用一个**单标尺 regime gate**
判断 BTC 当前处于周期的哪一段，再路由到唯一的**自适应三层面板** (Layer A/B/C)，
给出**一个研判 + 一个动作 + 一个仓位倾向**——为用户的"币本位高抛低吸、攒更多 BTC"目标服务。

设计哲学：**决策型而非全景型**。屏幕上不堆指标买家秀，每个数都得能直接转化为动作。

---

## 2. 设计演进：从"两套剧本打架"到"单一自适应面板"

### 2.1 旧形态的痛点

最初实现是 `/topping` + `/bottoming` 两个并列页：
- 各自有完整 Layer A/B/C 三层面板
- 各自给出"危险等级"/"机会等级"两套独立判定
- nav 上"逃顶研判"和"抄底研判"并列展示

**问题**：用户在任一时刻只能处于周期的一端，但 UI 让人**同时看两套结论**。当 RR 处中段时，两端都给"不太危险/不太机会"的暧昧研判，造成**决策瘫痪**——"到底听哪一套？"

更糟的是底部页有个"休眠"灰条 (`dormant`)，专门用来说"当前不在底部区，本页休眠"。等于
用第二个页面告诉用户"别看本页"，纯属信息噪音。

### 2.2 方案 D：彻底溶解二元

经过 A/B/C/D 四个备选方案权衡（详见 git commit `968149e`），选定 **方案 D · 单一自适应光谱**：

- **删除** `/topping` 和 `/bottoming` 两个页面（含模板、route、charts.js 死代码）
- **保留**两份数据引擎 (`topping.build()` / `bottoming.build()`) 作为指标计算库
- **保留**两份 Jinja partials (`playbook_top.html` / `playbook_bottom.html`) 作为面板组件
- `/cycle` 用 regime gate 决定**当前激活哪一端的 partial**，永远只渲染一个
- 删除"休眠"灰条概念——周期中段就是中段，明确说"持有不动"即可

**结果**：屏幕上不再有"另一套剧本"的任何痕迹。一个页、一个研判、一个动作。

---

## 3. 总体架构

```
┌──────────────────────────────────────────────────────────────┐
│                      /cycle 单一页面                          │
│                                                              │
│   ┌─────────────────────────────────────────────┐            │
│   │  regime gate (RR expanding 历史分位)         │            │
│   │  0 ─────── 30 ──────────── 70 ─────── 100   │            │
│   │  └底部区┘      └中性区┘      └顶部区┘        │            │
│   └──────────────┬──────────────────────────────┘            │
│                  │                                            │
│        ┌─────────┴─────────┐                                 │
│        ▼         ▼         ▼                                 │
│   底部区        中性区     顶部区                              │
│   ↓             ↓          ↓                                 │
│   playbook_     "持有     playbook_                          │
│   bottom        观望"     top                                │
│   (抄底剧本)    (HODL)    (逃顶剧本)                          │
│                                                              │
│   每个 partial 都是 Layer A + Layer B + Layer C 三卡         │
│                                                              │
│   ┌─────────────────────────────────────────────┐            │
│   │  双向历史回放 (一张图看顶/底两端何时亮过灯)     │            │
│   └─────────────────────────────────────────────┘            │
└──────────────────────────────────────────────────────────────┘
```

**关键架构特征**：
1. **单一标尺**：只用 Reserve Risk (RR) 的 expanding 历史分位定义周期位置
2. **单一 gate**：纯阈值路由，无任何模型/打分/投票
3. **自适应面板**：partial 复用，根据 regime 渲染对应那套
4. **三层结构强制对称**：顶部/底部都是 A (主信号) → B (确认) → C (技术触发)
5. **数据层 DRY**：通用分位引擎/技术面/回放抽到 `cycle_core.py`

---

## 4. 核心概念

### 4.1 Layer A/B/C 三层精英制

灵感来自机构 quant 的"主信号 + 确认 + 触发"体系。每层职责严格分离：

| 层级 | 职责 | 是什么 | 不是什么 |
|------|------|--------|----------|
| **Layer A** | 主信号 | **决定是否警报**的唯一指标 | 不是"投票一员" |
| **Layer B** | 确认 | A 警报后，多个独立估值类指标**互验** | 不能独立触发警报 |
| **Layer C** | 触发 | 技术面右侧/破位的**择时扳机** | 不能脱离 A/B 单独成立 |

**铁律**：A 没警报 → B/C 都灰色（顶部）/ 不计入决策（底部）。这是为了对抗
"指标买家秀 → 凑齐了就买/卖"的民间陷阱。

### 4.2 Expanding 历史分位 (Point-in-Time)

**所有阈值都是分位，不是绝对值。** 原因：
- BTC 周期之间结构变化大（早期 MVRV 飙到 8，2021 才到 4），固定阈值会过期
- 分位口径在 cycle 之间保持可比

**Point-in-Time 强制**：每个点的分位**只用 ≤当日数据**计算（`cycle_core.expanding_pct`）。
这是 Layer 0 数据完整性铁律，防未来函数。研究脚本 `bottoming_indicator_ic.py` 与展示层
`cycle_core.expanding_pct` **同口径**（刻意不跨层 import，保持解耦但逻辑严格一致）。

### 4.3 Regime Gate

`src/dashboard/data/cycle.py` 中两个常量：

```python
TOP_ZONE = 70.0     # RR 分位 >= 此值 = 顶部区
BOTTOM_ZONE = 30.0  # RR 分位 <= 此值 = 底部区
```

| RR 分位 | regime | 激活 partial | 仓位倾向 |
|---------|--------|--------------|----------|
| `>= 70` | 顶部区 | `playbook_top.html` | 倾向把 BTC 换成稳定币 |
| `(30, 70)` | 中性区 | "持有观望" 简卡 | 持有不动 (HODL) |
| `<= 30` | 底部区 | `playbook_bottom.html` | 倾向把稳定币换回 BTC |

**为什么是 70/30？** 兼顾"灵敏度"与"假信号率"。20/80 太迟，40/60 太频繁切。
70/30 在 BTC 2018-2025 实证中正好能区分出 4 个周期的高/低段。

---

## 5. 文件清单与职责

```
src/dashboard/
├── data/
│   ├── cycle.py            # ← 整合层：regime gate + 路由
│   ├── topping.py          # 顶部指标引擎 + 危险分级
│   ├── bottoming.py        # 底部指标引擎 + 机会分级
│   └── cycle_core.py       # 共享内核 (DRY)
│                           #   - load_series / load_onchain (数据加载)
│                           #   - expanding_pct / latest_pct (分位引擎)
│                           #   - layer_c_signals(direction) (技术面)
│                           #   - replay_history / replay_dual (历史回放)
├── pages/
│   └── cycle.py            # FastAPI handler: ctx = cycle.build()
├── templates/
│   ├── pages/cycle.html    # 页面骨架：regime 卡 + HERO + partial + 回放图
│   └── partials/
│       ├── playbook_top.html       # 顶部三卡 + 撤退状态机
│       └── playbook_bottom.html    # 底部三卡 + FGI 警告 + 避坑 + 接回状态机
└── static/
    └── charts.js           # renderCycle() 渲染双向点灯图
```

**职责边界 (SOLID)**：
- `cycle_core` 不知道"顶/底"语义，只暴露 `direction: "top"|"bottom"` 参数
- `topping`/`bottoming` 只生产数据 dict，不渲染
- `cycle.py` 只 gate + 路由，不计算指标
- partials 不读数据，只渲染传入的扁平 context

---

## 6. 数据流

```
data/raw/btc_binance_BTCUSDT_1d.csv    (Layer 0: 价格)
data/external/onchain/*.csv             (Layer 0: 链上指标)
data/external/fear_greed_index.csv      (Layer 0: 情绪)
            │
            ▼
   cycle_core.load_series / load_onchain
            │
            ▼
   ┌────────┴────────┐
   ▼                 ▼
topping.build()   bottoming.build()
   │ (顶部 ctx)    │ (底部 ctx)
   └────────┬──────┘
            ▼
       cycle.build()
       ├─ rr_pct = top["rr_pct"]
       ├─ regime = TOP_ZONE/BOTTOM_ZONE 路由
       ├─ active_verdict = top.verdict OR bot.verdict OR "持有观望"
       └─ hist = replay_dual(RR, 70, 30)
            │
            ▼
   pages/cycle.py → templates/pages/cycle.html
            │
            ▼
   regime gate 卡 → HERO 卡 → partial → 双向回放图
            │
            ▼
   charts.js: FcstCharts.renderCycle()
```

**关键调用约束**：
- `cycle.build()` **复用** `topping.build()` 和 `bottoming.build()` —— 即使当前只激活
  一端，另一端的引擎也会跑（轻量纯计算，不值得加 lazy 优化的复杂度）
- 所有 onchain CSV 文件缺失/损坏时 `load_series` 静默返回 `None`，上游优雅降级
  （`available: False` 渲染兜底信息）

---

## 7. 三层指标详解

### 7.1 顶部 (`topping.py`)

| 层级 | 指标 | 阈值 | 说明 |
|------|------|------|------|
| **A** | Reserve Risk | RR 分位 ≥85 警示，≥95 极危 | **唯一 \|t\|≥2 真 alpha** (IC 报告) |
| **B** | LTH-MVRV (首选) | ≥85 分位 = 高位 | 90d IC -0.296 |
| **B** | LTH-SOPR | ≥85 分位 = 高位 | 长持获利 |
| **B** | LTH-NUPL | ≥85 分位 = 高位 | 长持未实现盈亏 |
| **B** | MVRV-Z | ≥85 分位 = 高位 | 经典估值 |
| **B** | Puell | ≥85 分位 = 高位 | 矿工营收 |
| **C** | 跌破 SMA50 | 触发 = 收盘价 < 50日均 | 趋势破位 |
| **C** | 周线 MACD 转负 | 触发 = MACD 柱 < 0 | 中期动能反转 |
| **C** | 吊灯止损触发 | 触发 = 收盘 < `chand22` (22 期最高 - 3×ATR22) | 跟踪止损 |

**危险分级 (`topping._classify`)**：

| 等级 | 条件 | 动作 | 应减批次 |
|------|------|------|----------|
| 安全 | RR < 70 | 满仓 HODL | 0 |
| 警示 | RR ≥ 70 | 停止加仓, 盯 Layer C | 0 |
| 危险 | RR ≥ 85 且 B 高位计数 ≥ 2 | 减第 1 批 (~30%) | 1 |
| 极危 | RR ≥ 95 且 B 高位计数 ≥ 3 | 减第 2 批; C 触发则清第 3 批 | 2-3 |

### 7.2 底部 (`bottoming.py`)

| 层级 | 指标 | 阈值 | 说明 |
|------|------|------|------|
| **A** | Reserve Risk | RR 分位 ≤15 深度机会, ≤30 关注 | 事件级 180d 超额 +12.4%/命中 75% |
| **B** | AVIV (首选) | ≤15 分位 = 低位 | 事件 180d +10.5% |
| **B** | MVRV-Z | ≤15 分位 = 低位 | 事件 180d +6.6% |
| **AVOID** | LTH-NUPL | (展示分位 + 红色警告) | **事件级 -35.7%: 左侧首日接飞刀** |
| **AVOID** | NUPL | (展示分位 + 红色警告) | **事件级 -19.3%: 左侧首日接飞刀** |
| **特判** | 恐惧贪婪指数 | FGI ≤20 弹"极恐警告" | 实证: 极恐多在左侧下跌途中 |
| **C** | 站上 SMA50 | 触发 = 收盘价 > 50日均 | 右侧确认 |
| **C** | 周线 MACD 转正 | 触发 = MACD 柱 > 0 | 中期动能反转 |
| **C** | 放量突破前高 | 触发 = 收盘 > `H20` 且成交量 > 1.3×20日均 | 强右侧 |

**机会分级 (`bottoming._classify`)**：

| 等级 | 条件 | 动作 | 已接回批次 |
|------|------|------|------------|
| 观望 | RR > 30 | HODL | 0 |
| 关注 | RR ≤ 30 (或 A 极低但 B 未共振) | 备好稳定币, 盯 C | 0 |
| **机会区间** | RR ≤ 15 且 B 低位 ≥ 2, 但 **C 未触发** |  严禁左侧抄底, 等 C | 0 |
| 右侧确认 | RR ≤ 15 且 B ≥ 2 且 C ≥ 1 | 用稳定币分批接回 | 1-3 |

---

## 8. 顶部 vs 底部的关键不对称

这是设计中**最容易被对称性诱惑写错的地方**。两端逻辑结构相似 (Layer A/B/C)，但
**成本结构完全不同**：

| 维度 | 逃顶 | 抄底 |
|------|------|------|
| 错错后果 | **踏空** (仅机会成本) | **接飞刀** (真亏本金) |
| Layer C 角色 | 加速触发（早一点减仓没事） | **强制右侧**（不右侧不接） |
| AVOID 名单 | 不存在 | **存在** (LTH-NUPL / NUPL) |
| FGI 特判 | 不存在 | **存在** ("恐惧 ≠ 底部" 警告) |
| 警告色 | warn (黄) | **warn (红字加粗 + bg-rose)** |

**底部专属的"机会区间 vs 右侧确认"分级**：即使 A/B 都深度低估，如果 C 没触发，
分级停在"机会区间"，HERO 卡显示红色警告横条 **"别接飞刀: 深度低估 ≠ 见底"**。
这是直接从手册 §4.2 致命陷阱清单来的——历史上极度低估后价格常继续下跌数月。

---

## 9. 历史回放可视化

`cycle_core.replay_dual()` 在同一条 RR 分位曲线上标两种点：

- **红三角** = 该日 RR 分位 ≥ TOP_ZONE (历史上的顶部区)
- **绿三角** = 该日 RR 分位 ≤ BOTTOM_ZONE (历史上的底部区)
- **灰虚线** = BTC 价格 (右轴)

**目的**：让用户一眼验证"这套规则在历史上亮的灯是不是和真实顶/底大致对得上"。
是 self-audit 工具，不是预测。

抽稀逻辑 (`_subsample`)：约 `hist_points=120` 个采样点 + **强制保留最后一个点**
（否则图尾会缺最新数据，是个隐蔽 bug）。

前端在 `charts.js::renderCycle()` 用 Chart.js 渲染，自定义 y 轴网格颜色
（30/70 这两条线用黄色 `#f59e0b` 高亮 regime 边界）。

---

## 10. 设计决策记录

按时间倒序，每条记录一个"为什么这样做"：

### 10.1 (2026-06-09) ahr999 **不接入** Layer A
- **背景**：从 fuckbtc.com 参考看板学到 ahr999 定投指数，写了纯公式实现
- **IC 验证**：单因子 90d IC=-0.321/\|t\|=1.83 (第二强，但未达 \|t\|≥2 门槛)
  条件分位 30d: 6 事件 83% 命中 +14.8% 超额 (强)
- **致命发现**：ahr999 vs RR Spearman **ρ=0.910 (冗余级)**，本质同一信号的公式差异
- **决策**：不接进 Layer A (双倍计票 RR, 违反 SOLID 单一职责)
  保留作 (a) Layer 0 容灾备份 (纯公式零 API, RR 断供时顶上)
        (b) 未来可选 dashboard 附属并列展示, 不入 regime gate
- **教训写入**：未来添加任何"看似新"的指标，必须先跑共线性 + 双门槛
  (单因子 IC \|t\|≥2 且 vs 已有 ρ<0.7 才算新 alpha)
- **决策**: `repo:decisions` drawer 160, commit `5b200b0`

### 10.2 (2026-06-09) 方案 D：删除 `/topping` 和 `/bottoming`
- **背景**：两 tab 并列产生"双结论打架 → 决策瘫痪"
- **方案 D**：单一自适应光谱，由 regime gate 路由到唯一面板
- **删除**：`pages/topping.py`, `pages/bottoming.py`, `templates/pages/topping.html`,
  `templates/pages/bottoming.html`, `charts.js::renderTopping/Bottoming`,
  `cycle.py` 的 `dormant` 字段, `cycle.html` 的休眠灰条与失效链接
- **保留**：`data/topping.py`, `data/bottoming.py` (引擎), partials (cycle 复用)
- **commit**: `968149e`

### 10.3 (历史) 三层精英制 + Layer A 唯一 RR
- 实证依据：`docs/reports/btc_topping_ic_analysis_20260608.html`
  Reserve Risk 是唯一 \|t\|≥2 的真 alpha，其他都是 regime 依赖的"有时有效"
- 决策：Layer A 只放 RR，不引入"投票打分"。其他高 IC 指标（LTH-MVRV/MVRV-Z 等）
  归入 Layer B 作互验，**不能独立触发警报**

### 10.4 (历史) 全程 expanding 分位 + Point-in-Time
- 拒绝绝对阈值（MVRV<1=底、Puell<0.5=底）的民间传说
- 全程 `expanding(min_periods=1).apply(...)` 严格 point-in-time，防未来函数
- 研究层和展示层同口径但不跨层 import（手册架构约束）

---

## 11. YAGNI 边界：我们**故意不做**的事

为了保持"决策型"哲学不被稀释，以下功能**有人提过但被刻意拒绝**：

| 拒绝的功能 | 理由 |
|-----------|------|
| 在 Layer A 加多个指标投票 | 违反"主信号唯一性"，回到民间陷阱 |
| 接 ahr999 入 Layer A | ρ=0.91 与 RR 冗余 (§10.1) |
| 接预测市场跌破概率 | 无历史可回测, 过不了 IC 验证门槛 |
| 矿机表/STRC/MSTR mNAV | 对币本位周期择时 KPI 是噪音, YAGNI |
| 多周期相关性 (vs 黄金/纳指) | 同上 |
| 当前 BTC 价格 fallback 多源链 | dashboard 不直接 fetch 价格, 走每日 cron 下载 |
| Layer 4 组合层 (vol targeting/Sharpe) | 用户目标是币本位攒币, 不是 USD Sharpe |
| Layer C 自动下单 | dashboard 是只读展示, 不下单 |

---

## 12. 扩展指南：如何"正确地"添加新指标

任何添加新指标到 Layer A/B 的 PR **必须通过以下检查**才能合并：

### 12.1 IC 双门槛 (硬要求)
新指标必须同时满足：

1. **单因子 IC \|t\| ≥ 2** (h=90d 非重叠采样)
2. **vs 已有 Layer A/B 全部指标 Spearman ρ < 0.7** (避免冗余)

操作：
```bash
# 1. 把新指标加进 INDICATORS dict
vim scripts/research/topping_indicator_ic.py
# 2. 跑底部 IC (会包含顶部 + 条件分位 + 全样本)
python scripts/research/bottoming_indicator_ic.py
# 3. 跑共线性检查 (单写, 见 commit 5b200b0 中 ahr999 的例子)
```

### 12.2 数据层契约 (Layer 0)

- CSV 必须 `date,value` 两列, date 升序
- 必须有每日自动更新机制 (cron 或下载脚本)
- 若依赖外部 API，必须有 fallback 或备份计算方式 (避免 reserve_risk 断供事故重演)

### 12.3 文档要求

- 在 `topping.py` / `bottoming.py` 模块 docstring 更新指标清单
- 在 IC 报告 (`docs/reports/btc_*_ic_analysis_*.html`) 追加验证结果
- 在本文档 §10 添加决策记录条目（**包括如果决定不接的理由**）

### 12.4 修改 regime gate 阈值的额外约束

如果想动 `TOP_ZONE` / `BOTTOM_ZONE`：

- 必须用至少 2 个完整 BTC 周期回测验证 (>= 8 年数据)
- 必须报告 false positive rate 和 false negative rate 变化
- 必须更新本文档 §4.3 的"为什么是 70/30"

---

## 13. 经验教训 (来自这次设计迭代)

| 教训 | 一句话总结 |
|------|-----------|
| **双结论打架 = 决策瘫痪** | UI 给用户两套并列研判，比给一个错的研判还糟 |
| **看似新指标常常冗余** | ahr999 vs RR ρ=0.91，先做共线性再决定接不接 |
| **对称性是陷阱** | 顶/底逻辑结构对称但成本不对称，照搬必出事 |
| **休眠 UI 是负价值** | 用第二页面告诉用户"别看本页"，纯噪音 |
| **删代码比加代码更难也更值得** | 方案 D 删了 4 文件、改了 4 文件，是最重要的进化 |
| **Point-in-Time 不能跨层共享代码** | 研究层 vs 展示层同口径但分别实现，保解耦 |

---

## 14. 维护记录

- **2026-06-08** v0.x: `/topping` + `/bottoming` 双 tab 上线，伴随完整 IC 研究报告
- **2026-06-09**: 方案 D 落地，整合到 `/cycle` 单页 (commit `968149e`)
- **2026-06-09**: ahr999 IC 验证完成，决定不接入 (commit `5b200b0`)
- **2026-06-09**: 本设计文档 v1.0 落地

---

*本文档与代码同时更新。任何改动 `cycle.py` / `topping.py` / `bottoming.py` 的核心
决策逻辑 (阈值、分级条件、新增指标) 的 PR，必须同步修订本文档对应章节。*
