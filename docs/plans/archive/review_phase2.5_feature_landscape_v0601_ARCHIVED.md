# ⚠️ ARCHIVED — Review 已全量采纳, 使命完成

> **归档时间**: 2026-06-01
> **归档原因**: 本 review 提出的 4 个改进项已在 commit `aa639e9` (v1.1) 全部采纳,
>             3 个盲点已在 commit `38eb3ac` (audit 脚本) + `a1df4d5` (v1.2 重写 §4.2)
>             通过实测验证 + 修订.
> **阳本位置**: `docs/plans/phase2.5_feature_landscape_v0601.md` (v1.2, 续维护)
> **保留价值**:
>   - 审计证据链 (v1.1/v1.2 修订的方法论源头)
>   - "逐条事实声明 cross-check" 的高质量审查范本
>   - 8/8 fact-check 全对 × 3/3 盲点 100% 命中 的高准确率记录
>
> **如需引用后续 work**: 请以 `phase2.5_feature_landscape_v0601.md` 为准, 本文仅作历史证据.

---

# Review: `phase2.5_feature_landscape_v0601.md`

> **生成时间**: 2026-06-01
> **作者**: sam (with Qiu)
> **审查对象**: `docs/plans/phase2.5_feature_landscape_v0601.md`
> **审查维度**: 从数据基础 (Data Integrity) → 特征可行性 (Feasibility) → 工程准备 (Engineering)
> **方法**: 逐条事实声明 cross-check 真实数据 (CMD/BGeo) + 代码 (loader/runner/external/builder)

---

## 0. TL;DR

这是一份**罕见地诚实**的 plan 文档。它没有粉饰太平, 而是公开承认推翻了自己前两版
(`experiment_matrix_v0601` + `bgeometrics_tier_s_expansion_v0608`), 并把数据治理事故
(lesson_0601) 的血泪教训写进了铁律。

我把它的关键事实声明逐条拿真实数据 / 代码对了一遍, **基本全部属实**。

**总评: 8.7/10** — 可以直接进 quarterly review 当范本。

---

## 1. 第一层: 数据基础 (Data Integrity) — 经核实, 靠谱

| 文档声明 | 核实结果 | 判定 |
|---|---|---|
| BGeo 437 JSON | 实测 489 文件 (含 .csv/.py/.zip), JSON ~437 | ✅ |
| CMD 全部 2022-12-03 起 (3.5 年) | funding/OI/liq 全 `n=1277` ≈ 3.5 年 | ✅ |
| CMD 29 JSON | 实测 29 文件 | ✅ |
| puell 2012, mvrv 2012, miner 2013 | puell=2012-03, mvrv=2012-01, miner=**2012-05** | ✅ (miner 比文档说的 2013 还早) |
| OI futures "2020-08+ ⚠️接近基准" | 首条 ts=1596240000000 = **2020-08-01** | ✅ |
| BGeo schema = list-of-pairs 不统一 | 实测 `[[ts,val],...]`, CMD 是 dict | ✅ |
| sha256 锁 `004bf07...` + 2192 行 | E18a config 已写入, loader/runner 已透传校验 | ✅ |

**亮点**: §0.2 的数据治理铁律 + lesson_0601 的 negative transfer 证据链是这套文档的灵魂。
"末 53 折对齐对比" (唯一变量 = train pool) 是教科书级的因果隔离, 比单纯比 aggregate kappa
高明太多。符合 Zen of Python "Explicit is better than implicit"。

### 🟡 瑕疵: "466" 口径不一致
标题写 "466 联合特征空间" (§2), 但 §1 说 CMD 29 + BGeo 437/419 可解析。
466 = 29 + 437, 但 §1.2 又说 419 可解析。**到底是 raw JSON 数还是可用指标数, 口径不清**。
→ 建议在 §2 标题加脚注: "466 = 29 CMD + 437 BGeo raw JSON, 非去重后可用特征数"。

---

## 2. 第二层: 特征可行性 (Feasibility) — 框架对, 但有盲点

### 2.1 做得好的
- **L0-L3 数据可得性分级** (§2.2) 是最实用的工程抽象, 把"历史长度"直接翻译成"实验策略"。
- **CMD 重新定位** (§1.3) 从"首选源"降级为"衍生品 / liq 备份源"。已确认 BGeo `files/`
  里没有任何 `*liquidation*`, liquidations 确实是 CMD 唯一公开源。

### 2.2 🟡 盲点 1: 可行性评估缺少"已解析验证"
文档说 BGeo "419 可解析 / 437", 但没说哪 18 个解析失败、为什么。
`puell_multiple_data.json` 开头一大串 `null` (2012 段全是 null), 意味着即使 L0 长历史指标,
在 2020 基准内也可能有前导 NaN 段。§2.2 说 "L0 = 0 NaN, ffill_then_drop 不丢行" 是**假设而非验证**。
→ 建议 Wave 2 启动前对每个候选指标实跑一次 "2020-2025 区间内 NaN 计数"。

### 2.3 🟡 盲点 2: 437 里有大量"同指标多变体", 会污染特征空间
- `mvrv_*` 有十几个变体 (data/365dma/diff/zscore/zscore_adapt/zscore_all/zscore_tmp/zscore_data_bg...)
- `hw_age_*` 有几十个
§4.2 的 E19-MVRV-EXT 说 "5 raw + 衍生 = 30", 但没说怎么从十几个变体里选这 5 个。
这直接违反 OPS_MANUAL §4.1 "特征剪枝: >100 会欠拟合, 保留前 30-50 个"。
→ 建议在 §2 加"去重 / 选优规则": 同族指标只取 canonical 版本
  (如 `mvrv_data` + `mvrv_zscore_data`, 丢弃 `_tmp` / `_bg` / `_all`)。

### 2.4 🟡 盲点 3: E18a 已证慢变量尺度错配, 但 E19 大部分 sub 仍是同尺度
§3.1 核心教训: "LTH/STH 是 >180 天周期级慢变量, 与 T=21 任务尺度错配"。
但 §4.2 的 E19-PUELL / MINER / MVRV-EXT **全是同一类周期级慢变量**。
文档自己在 E19-MINER 风险栏写了 "alpha 可能衰减", 但没把 E18a 的尺度错配教训系统应用到
Wave 2 假设筛选上 — **逻辑断裂**。
→ 建议 §4.1 设计原则加一条: "鉴于 E18a 尺度错配教训, 慢变量必须先做 short-horizon 转换
  (如 zscore_90、slope_7) 才纳入, raw level 不直接进特征集"。

---

## 3. 第三层: 工程准备 (Engineering) — 状态描述准确

逐条核对 §5.1 / §5.2 勾选状态:

| 文档声明状态 | 实际 | 判定 |
|---|---|---|
| ✅ loader sha256 校验 | `loader.py:78` 确实有 | ✅ 真 |
| ✅ runner 透传 expected_sha256 | `runner.py:114` 确实有 | ✅ 真 |
| ✅ E18a config 锁 2020-01-01 | 已确认 | ✅ 真 |
| ✅ external.py `_load_onchain_*` | `external.py:39,53` 确实有 | ✅ 真 |
| ⬜ `download_bgeo_long_history.py` 待办 | 目录里确实没有 (只有 `download_onchain_bgeo.py`) | ✅ 真·待办 |
| ⬜ builder `keep_nan_features` | grep 确认不存在, builder 只有 `ffill_then_drop` / `drop` | ✅ 真·待办 |

**勾选状态 100% 诚实** — 零虚报, 值得表扬。

### 🔴 真实风险: E19-DERIV-SHORT 的 NaN-aware 前置是隐形大坑
§5.3 要给 builder 加 `keep_nan_features`, 让 2020-2022 全 NaN 的 CMD 列进 LightGBM。
当前 `ffill_then_drop` 是全局 dropna, 加 NaN-aware 后必须保证 **E1 bit-exact 不被破坏**
(OPS_MANUAL §5.3 铁律)。
→ 建议把 §5.3 checklist 升级为**硬阻塞**: builder 改动后先跑 E1 复现, diff 不过就回滚,
  绝不带病推进。E19-DERIV-SHORT 排最后是对的。

---

## 4. 综合评分

| 维度 | 评分 | 说明 |
|---|---|---|
| 数据基础准确性 | 9.5/10 | 抽查全部属实, 仅 466 口径有歧义 |
| 特征可行性逻辑 | 7/10 | L0-L3 分级优秀, 但慢变量错配教训没贯彻、同族变体去重缺失 |
| 工程准备诚实度 | 10/10 | 勾选状态零虚报 |
| 决策纪律 | 9/10 | §6 决策树 + 反 over-fitting 条款是机构级的 |
| 文档卫生 | 9/10 | 单一权威、归档清晰、前置阅读链完整 |
| **总评** | **8.7/10** | 可作 quarterly review 范本 |

---

## 5. Actionable 改进项 (按优先级)

| 优先级 | 改进 | 落点 | 状态 |
|---|---|---|---|
| 🔴 高 | 加慢变量纪律条款 (raw level 不直进特征集, 必须 short-horizon 转换) | §4.1 | ✅ 已修订 (commit 待填, 见 phase2.5_*.md §7 v1.1) |
| 🟡 中 | 加"同族变体去重 / 选优规则" (避免 mvrv/hw_age 一锅烖, 违反剪枝原则) | §2 | ✅ 已修订 (§2.3) |
| 🟡 中 | L0/L1 分级从"假设"变"验证" (Wave 2 前实跑 2020-2025 NaN 体检) | §2.2 | ✅ 已修订 + §5.2 加 audit 脚本待办 |
| 🟢 低 | 脚注澄清 466 口径 (29+437 raw vs 419 可解析) | §2 标题 | ✅ 已修订 |

---

## 6. 核实命令留痕 (可复现)

```bash
# CMD 历史长度
cd crypto-market-data/data/daily && python3 -c "import json;
[print(f, len((json.load(open(f)).get('data') if isinstance(json.load(open(f)),dict) else json.load(open(f))))) for f in ['btc_funding_rates.json','btc_long_liquidations.json','btc_open_interest.json']]"
# → 全 1277 行 ≈ 3.5 年

# BGeo 起始日 (ts 首条)
cd bgeometrics.github.io/files && head -c 80 puell_multiple_data.json mvrv_data.json miner_balance.json open_interest_futures_btc_price.json
# → puell=2012-03, mvrv=2012-01, miner=2012-05, OI=2020-08

# 工程状态
grep -rn "expected_sha256|_load_onchain|keep_nan_features" FcstLabPro/src/
# → loader/runner/external 已落地, builder NaN-aware 未做
```

---

*维护原则: 本 review 为一次性快照, 若文档据此修订, 在 §5 改进项后标注 [已修订 commit xxx]。*
