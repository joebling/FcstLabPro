# Dashboard 弱耦合优化方案 (LightGBM × 周期研判)

**创建日期**: 2026-06-09
**作者**: code-puppy (sam) + Qiu 讨论
**状态**: 已实施 (2026-06-10, dashboard 展示层弱耦合: perfmon切片 + overview banner + signals RR色带)
**关联**: `src/dashboard/`, `docs/design/dashboard_architecture.md`

---

## 一、问题背景

当前 dashboard 上有两块独立模块, **视觉并列、决策隔离**:

| 模块 | 路径 | 方法 | 输出 |
|------|------|------|------|
| LightGBM 预测模型 | `/signals` `/perfmon` `/overview` 部分 | 监督学习 (walk-forward, T+21) | 离散 BUY/HOLD/SELL |
| 周期研判 | `/cycle` `/overview` 温度计 | 规则引擎 + RR rolling-2y 分位 | 顶/中/底 regime + 三层面板 |

**潜在风险**: 用户看到 RR 87% 极顶, LightGBM 照样可能给 BUY 信号, 二者不打架但也不协同, 需要用户自己脑内做 AND。早晚出错决策。

**Qiu 原始二分理解**: "前者偏微观, 后者偏宏观"。
**实际更准的表述**: 它们是 **不同 Layer** 的东西, 应该 **嵌套** 而非并列:

```
        周期研判 (Layer 4 战略层 / Regime Gate)
                    ↓ 决定能不能开
              ┌──────────┴──────────┐
        顶部区: 仓位偏空        底部区: 仓位偏多
              │                       │
              ↓                       ↓
        LightGBM (Layer 5 战术层 / 择时信号)
        在 regime 允许的方向上, 决定何时出手
```

---

## 二、三种耦合方案对比

| 方案 | 含义 | 优点 | 缺点 |
|------|------|------|------|
| 1. 保持并列 (现状) | 两块各干各的 | 简单, 不耦合 | 用户用错怪不到代码 |
| **2. 弱耦合 (本方案)** | dashboard 展示层叠加交叉视图 | 0 改模型代码, 信息量大 | 仍需用户人工决策 |
| 3. 强耦合 | `live_signal.py` 读 RR 作 hard gate | 自动化 | 需 walk-forward 重验, 高风险 |

**本方案聚焦弱耦合**, 强耦合留到 V2.0 再议。

---

## 三、核心设计原则

1. **单一真相源**: `cycle.build()` 是 regime 唯一来源 (现状 `cycle_gauge.py` 已遵守此原则), 新增组件全部复用, 不 reimplement 分位逻辑。
2. **0 改模型代码**: `live_signal.py` / `*_state.json` / `models/production/` 全不动。
3. **展示层叠加**: 所有交叉视图都在 `src/dashboard/` 内完成。
4. **数据先行**: 优化 3 (按 regime 切片战绩) 优先做, 用真实数据决定 banner 措辞激进度。

---

## 四、优化清单 (按 ROI 排序)

### 优化 1: 总览页加 "Coherence Banner" (一致性条)

**位置**: `/overview` 页顶部, 在周期温度计和持仓研判之间。

**逻辑**: 把 `cycle.build()["regime"]["key"]` × `ledger.position(model)["last_signal"]` 做交叉, 四种状态:

| 周期 regime | LightGBM signal | banner 文案 | 颜色 |
|---|---|---|---|
| 顶部 | BUY | 冲突 · 建议人工降级为 HOLD 或减半仓位 (周期高位逆风) | rose |
| 顶部 | SELL/HOLD | 协同 · 顺势离场 | emerald |
| 底部 | BUY | 协同 · 强信号 (双重确认) | emerald (大字) |
| 底部 | SELL | 冲突 · 周期低位建议持币 | amber |
| 中性 | * | 中性 · 按模型走 | slate |

**UI 示例**:

```
+--------------------------------------------------+
|   周期-信号不一致                                 |
| 周期: 顶部区 (RR 87)  ×  模型: BUY (e20c)         |
| 建议人工降级为 HOLD, 或减半仓位 (周期高位逆风)    |
| [查看周期研判 ->] [查看类似情境历史战绩 ->]       |
+--------------------------------------------------+
```

**实现成本**: 新增 `src/dashboard/data/coherence.py` (~50 行) + 改 `templates/pages/overview.html` 插入组件。

**预估 LoC**: ~80
**价值**: 最高 (立刻防错决策)

---

### 优化 2: signals 页历史信号叠 RR regime 色带

**位置**: `/signals` 页历史信号时间线图表。

**做法**: 价格曲线背景按 RR regime 染色:
- 浅红背景: RR 顶部期 (>=70)
- 浅绿背景: RR 底部期 (<=30)
- 无色: 中性期

**示意**:

```
价格曲线
   ^
   |     [浅红背景: RR 顶部期]
   |
   |              ↑ ← BUY 信号在顶部期, 后续 -8% 套牢
   |
   |  [浅绿背景: RR 底部期]
   |
   |      ↑ ↑ ← BUY 信号在底部期, 后续 +35% 大赚
   v
```

**技术依据**: `cycle_core.replay_dual()` 已能输出每个历史时点的 RR 分位, 数据全有, 只需 chart.js 多画两层半透明背景。

**洞察价值**: 一眼看出 "LightGBM 在 RR 顶部期的胜率是否真的更差", 是优化 1 banner 建议的 **实证依据**。

**实现成本**: 改 `pages/signals.py` + 模板 + `static/charts.js`。

**预估 LoC**: ~60
**价值**: 中 (实证依据)

---

### 优化 3: perfmon 页按 regime 切片战绩 (研究价值最高, 建议先做)

**位置**: `/perfmon` 页, 在现有汇总下方新增分组表。

**做法**: `ledger.trade_history()` 当前汇总全样本胜率/均盈, 按 RR regime 切片重算:

| Regime | 交易数 | 胜率 | 均盈 | 总贡献 |
|---|---|---|---|---|
| 顶部期开仓 (RR>=70) | 8 | 25% | -3.2% | -25.6% (噪音/亏损源) |
| 中性期开仓 | 23 | 52% | +1.1% | +25.3% |
| 底部期开仓 (RR<=30) | 5 | 80% | +6.8% | +34.0% (Alpha 集中区) |

**为什么这是研究价值最高的一步**:
- 直接回答 "LightGBM Alpha 是否集中在某个 regime"
- 决定优化 1 banner 措辞应该多激进 (如果数据均匀, banner 不该做; 如果数据分化大, banner 该激进)
- 是手册 §2.3 "Regime 依赖" 的真实数据校验

**实现成本**: 改 `src/dashboard/data/ledger.py` (新增 regime 切片函数, 复用 `core.position_pct()` 把每笔 trade 的 entry_date 映射到当时的 RR 分位) + 改模板。

**预估 LoC**: ~100
**价值**: 最高 (研究价值)

---

### 优化 4: 新增 `/coherence` 研究子页 (可选, 后置)

**触发条件**: 优化 1+2+3 跑通后再考虑。

**内容**:
- 散点图: x=RR 分位, y=信号后 21 天收益 (LightGBM 目标窗口)
- 不同 regime 下信号 IC 横切面 (补充 walk-forward IC 的截面视角)

**为什么后置**: YAGNI 原则, 先看优化 3 出来的切片表能不能满足需求。

---

## 五、实施顺序 (3 个独立 commit)

> 2026-06-10 实施记录: 三项核心优化已合并为一次 dashboard 展示层改动；仍保持 0 改模型代码、0 写回信号 state。
> `/perfmon` 增加按开仓日 RR regime 切片，`/overview` 增加周期×信号一致性 banner，`/signals` 增加 RR 顶/底色带和表格徽章。


| # | 改动 | 文件 | 预估 LoC | 价值 | 建议顺序 |
|---|------|------|---------|------|---------|
| 3 | perfmon 按 regime 切片 | `ledger.py` + 模板 | ~100 | 最高 (研究) | **第一步** |
| 1 | overview Coherence Banner | 新增 `coherence.py` + 模板 | ~80 | 最高 (决策) | 第二步 |
| 2 | signals 页 RR 色带 | `pages/signals.py` + 模板 + js | ~60 | 中 (实证) | 第三步 |
| 4 | `/coherence` 研究页 | 新建 page + 模板 | 待定 | 待定 | 后置, 看 1-3 效果 |

**为什么 3 先做**: 数据先行。如果切片表显示 "顶部期 BUY 其实胜率也不差", 那优化 1 的 banner 文案就该温和很多, 甚至不该做。

---

## 六、不做清单 (反向边界)

1. **不在 banner 里"自动降级"信号** (即把 BUY 改 HOLD 写回 state)
   → 那就成强耦合了, 跟 LightGBM 训练假设不一致, 必须 walk-forward 重验。
2. **不把 RR regime 加进 LightGBM 特征**
   → 同上, 训练 OOS 都得重做, 是 V2.0 的工作。
3. **不 redesign cycle 页**
   → 已经够好, 别动。
4. **不写新 markdown 报告解释一致性**
   → overview banner 一句话能讲清, 别整文档。

---

## 七、复用性检查 (DRY)

| 数据 | 唯一来源 | 复用方式 |
|------|---------|---------|
| RR 分位 / regime key | `cycle.build()` | coherence.py 直接调用 |
| 历史 RR 分位序列 | `core.position_pct()` | perfmon 切片 + signals 色带共用 |
| 当前 LightGBM 信号 | `ledger.position(model)` | coherence.py 复用 |
| 历史交易 | `ledger.trade_history()` | perfmon 切片复用 (新增 regime 参数) |

**无重复实现, 无新数据源, 完全在现有数据栈上叠加。**

---

## 八、明天决策时的关键问题

1. 优化 3 (perfmon 切片) 的数据出来后, 顶部期/底部期的胜率分化够明显吗?
   - 分化大 -> 优化 1 banner 激进版 (建议人工降级)
   - 分化小 -> 优化 1 banner 温和版 (只提示状态, 不给动作)
   - 无分化 -> 砍掉优化 1, 只做 2+3
2. 优化 2 的色带视觉是否过于花哨? 替代方案: 只在信号点上加 RR 分位标签 (mini badge)。
3. 是否需要把 banner 同步到每日邮件? (本方案不涉及, 但邮件复用 ledger 同一数据源, 加起来不难)

---

## 九、附录: 相关代码位置

- `src/dashboard/data/cycle.py` - 周期研判整合层 (regime gate)
- `src/dashboard/data/cycle_core.py` - 分位引擎 (rolling-2y V1.2)
- `src/dashboard/data/cycle_gauge.py` - 温度计 (已复用 cycle.build, DRY 范例)
- `src/dashboard/data/ledger.py` - 生产持仓 + 真实战绩
- `src/dashboard/pages/overview.py` - 总览页组装
- `src/dashboard/templates/pages/overview.html` - 总览页模板
- `docs/plans/rolling_vs_expanding_audit_20260609.md` - V1.2 分位升级背景

