# ⚠️ ARCHIVED — BGeometrics Tier S 链上指标扩展计划 (Phase 2.6)

> **归档日**: 2026-06-01
> **归档原因**: 该文档定位为 "Phase 2.5 完成后的增量扩展" (Phase 2.6), 但实际上:
>   1. **BGeo 才是主场**: BGeo 437 个 JSON 远超 CMD 29 个, 是 Phase 2.5 主体而非扩展
>   2. **Tier S 只列了 8 个**: 但 BGeo 实际有 50+ 个值得试的长历史指标
>   3. **启动条件依赖 CMD 路线胜出**: 但 CMD 本身数据范围不足, 该启动条件不合理
>
> **接替文档**: `docs/plans/phase2.5_feature_landscape_v0601.md`
>
> **保留价值**:
>   - §3 BGeo Tier S 具体指标说明 (sopr_data, nvts 等) 仍有参考价值
>   - §10 启动检查清单 (含 2026-06-01 新增的数据基准校验) 已上移到新文档
>
> **参考**: `docs/lessons/lesson_0601_data_governance_regime_shift.md`

---

# BGeometrics Tier S 链上指标扩展计划 (Phase 2.6)

> **生成时间**: 2026-06-01
> **作者**: sam
> **前置阅读**:
>   - [`onchain_lth_sth_feature_plan.md`](./onchain_lth_sth_feature_plan.md) — Phase 2.5 LTH/STH 计划
>   - [`experiment_matrix_v0601.md`](./experiment_matrix_v0601.md) — Phase 2.5 实验矩阵
>   - [`feature_engineering_roadmap.md`](./feature_engineering_roadmap.md) — Phase 1-4 全局
> **触发条件**: Phase 2.5 Wave 1-2 完成且至少一个数据源显著
> **状态**: 待 Phase 2.5 完成后启动

---

## 0. TL;DR

1. **Phase 2.5 调研盲区**: 只看了 11 个 JSON, 实际 BGeometrics CDN 有 **489 个**, 漏掉约 8-10 个核心独立链上指标。
2. **本计划范围**: 扩展引入 **Tier S 8 个指标族** (SOPR/Puell/NVT/CDD/RHODL/F&G/funding/OI), 全部已在 BGeo CDN 验证可达。
3. **关键设计**: 启动条件依赖 Phase 2.5 结果——只在 LTH/STH 路线证明有效后启动，避免重复投入失败方向。

---

## 1. 背景：Phase 2.5 调研盲区

### 1.1 发生了什么

Phase 2.5 调研时（详见 `onchain_lth_sth_feature_plan.md` §1.2），重点放在了 MVRV/NUPL/SOPR 三族的 LTH/STH 拆分上，**默认认为 CDN 主要就是这些**。

实际上 `ls files/ | wc -l` 显示 **489 个 JSON**，主题覆盖：

| 主题 | 文件数 | Phase 2.5 覆盖率 |
|---|---|---|
| MVRV 系列 | 19 | 5/5 核心 ✅ |
| NUPL 系列 | 10 | 3/3 核心 ✅ |
| SOPR 系列 | 11 | **2/3 ⚠️ 漏 sopr_data** |
| Puell | 3 | **0/1 ❌** |
| NVT (Willy Woo) | 20 | **0/3 ❌** |
| CDD / VDD | 6 | **0/2 ❌** |
| RHODL | 6 | **0/2 ❌** |
| Hash / Miner | 17 | **0/5 ❌** |
| Fear & Greed | 3 | **0/1 ❌** |
| Funding / OI | 7 | **0/2 ❌** (重复 CMD 但口径不同) |
| 宏观 (M2/FedFunds/SP500) | 16 | 0/4 ❌ (Phase 4 计划) |
| HODL Waves | 32 | 0/8 ❌ (本计划候选) |
| Address 分类 | 34 | 0/4 ❌ (本计划候选) |
| ETF flows | 8 | 0/2 ❌ (Phase 4 计划) |
| Realized Cap | 44 | 0 ❌ (派生品多) |

### 1.2 为什么漏掉这些

Phase 2.5 围绕 "LTH/STH 行为分化" 这一**单一假设**展开。但其他 Tier S 指标代表**完全不同的链上信息维度**:

| 维度 | 代表指标 | 跟 LTH/STH 的关系 |
|---|---|---|
| **矿工经济** | Puell, hashrate, miner_sell_presure | 完全独立 (供给端 vs 需求端) |
| **网络估值** | NVT, NVTadj90 | 完全独立 (估值 vs 持有者) |
| **持币者行为** | CDD, VDD, RHODL | 部分重叠 (但口径不同) |
| **市场情绪** | F&G | 完全独立 (情绪 vs 链上) |
| **衍生品** | funding, OI | 独立 (但 CMD 已覆盖, BGeo 口径作 ablation) |

**结论**: 这些是真正能提升 Bear 模型 Kappa 的独立 alpha 源, 不该被遗漏。

---

## 2. Tier S 指标矩阵 (8 个)

### 2.1 完整清单

| # | 指标 | URL | 信息维度 | 历史 | 优先级 |
|---|---|---|---|---|---|
| 1 | `sopr_data` | `charts.bgeometrics.com/files/sopr_data.json` | 全市场 SOPR (vs LTH/STH SOPR 已有) | 2012+ | 🔴 S |
| 2 | `puell_multiple_data` | `puell_multiple_data.json` | 矿工收入/365MA (周期顶/底经典) | 2012+ | 🔴 S |
| 3 | `nvts` (Willy Woo) | `nvts.json` | Network Value to Trans Signal | 2014+ | 🔴 S |
| 4 | `nvtadj90` | `nvtadj90.json` | NVT 90日调整 (平滑) | 2014+ | 🔴 S |
| 5 | `cdd` | `cdd.json` | Coin Days Destroyed (老钱激活) | 2010+ | 🔴 S |
| 6 | `rhodl_1m` | `rhodl_1m.json` | Realized HODL Ratio 1月 | 2012+ | 🔴 S |
| 7 | `fear_greed_data` | `fear_greed_data.json` | F&G 情绪指标 | 2018+ | 🔴 S |
| 8 | `funding_rate` (BGeo) | `funding_rate.json` | BGeo 口径 funding | 2019+ | 🟡 A |

### 2.2 Tier A 候选 (4 个, 视 Tier S 结果决定)

| 指标 | 原因 |
|---|---|
| `hashrate` | 链上健康 + 矿工产能 |
| `miner_sell_presure` | 矿工抛压（跟 puell 互补）|
| `miner_out_flows` | 矿工净流出（跟 CMD miner_netflow 比较）|
| `vdd_multiple` | Value Days Destroyed (CDD 的价值加权版)|

### 2.3 Tier B 候选 (视全局决定)

- **HODL Waves 时间分布族** (~8 个时间段): 持币年龄分布，长尾持有者行为
- **Address 持币量级分布** (~6 类: <0.01, 0.01-0.1, 0.1-1, 1-10, 10-100, 100+ BTC): 巨鲸 vs 散户分布
- **`mvocdd_data`**: MV/OCDD 比值，CDD 的另一种归一化
- **`realized_cap`** / **`terminal_price`**: 已实现市值 / 终端价格

---

## 3. 特征设计（每指标 6 衍生 + 8 交互 ≈ 56 特征）

### 3.1 基础衍生（每指标 6 个，跟 Phase 2.5 一致）

```
ext_{name}            — raw
ext_{name}_ma_7       — 7 日均
ext_{name}_ma_30      — 30 日均
ext_{name}_change_7   — 7 日环比
ext_{name}_change_30  — 30 日环比
ext_{name}_slope_30   — 30 日斜率
```

8 个 Tier S × 6 = **48 基础特征**

### 3.2 跨指标交互（8 个，体现"链上叙事"）

```python
ext_puell_x_cdd            = puell * cdd              # 矿工压力 + 老钱出货 (顶部)
ext_rhodl_x_nvts           = rhodl_1m * nvts          # 周期顶部双重确认
ext_fg_x_sopr              = fear_greed * sopr        # 情绪 + 实际抛售
ext_miner_capitulation     = (puell < 0.5).astype(int) # 矿工投降信号 (底部)
ext_extreme_fear           = (fear_greed < 25).astype(int)
ext_extreme_greed          = (fear_greed > 75).astype(int)
ext_cdd_spike              = cdd / cdd.rolling(90).mean()  # 异常激活
ext_nvts_above_band        = (nvtadj90 > nvtadj90_high).astype(int)  # 超买区
```

→ **总计 ~56 特征**（vs Phase 2.5 的 44）

### 3.3 不做的事（YAGNI）

- ❌ 用 BGeo `_btc_price` 合并文件 (有 BTC price 双轴, 我们只要指标值)
- ❌ 用 `_dma/_sma/_ema` 文件 (自己算更可控)
- ❌ 用 `_heatmap` 文件 (3D 数据, 不适合 LightGBM)
- ❌ 用 `_latest` 文件 (单行, 没历史)
- ❌ 把 hashrate 30sma + raw + ema 三版本都加 (raw + 自衍生足够)

---

## 4. 实验路线图

### 4.1 实验设计

继续 Phase 2.5 的 E22+ 编号:

| ID | 名称 | 新增 | 对照 | 主回答 |
|---|---|---|---|---|
| **E22** | `v0608_E22_bgeo_tier_s` | Tier S 8 指标 + 交互 (56 特征) | 优胜者 from Phase 2.5 | Tier S 独立贡献? |
| **E23** | `v0608_E23_integrated_full` | Phase 2.5 优胜 + Tier S | E22, Phase 2.5 优胜 | 是否互补? |
| **E24** | `v0608_E24_tier_a_add` *(条件)* | E23 + Tier A 4 指标 | E23 | Tier A 边际贡献? |
| **E25** | `v0608_E25_pruned` | E23/E24 + Phase 3 剪枝 | E23 | 减肥后是否还行? |

### 4.2 启动条件

**强约束**: 只在以下情况启动:

```python
if Phase 2.5 优胜实验 (E18b/E19c/E20).Kappa >= E1.Kappa * 1.05:
    → 路线证明有效, 启动 Phase 2.6 (E22+)
elif Phase 2.5 全部失败:
    → 链上数据本身没价值, 跳过 Phase 2.6, 转 Phase 3 剪枝路线
else:
    → 介于之间, 跑一个 minimal E22 验证 Tier S 是否独立有效
```

### 4.3 时间预算

| 步骤 | 单次 | 累计 |
|---|---|---|
| 扩展 `download_onchain_bgeo.py` 加 Tier S 8 个 | 15 min | 15 min |
| VPS 拉数据 + 验证 + commit | 15 min | 30 min |
| `src/features/external.py` 新增 builder | 1 h | 1.5 h |
| 写 E22 config | 10 min | 1.7 h |
| 跑 E22 | 30 min | 2.2 h |
| 决策点 + 写报告 | 30 min | 2.7 h |
| (条件) E23/E24/E25 | 2 h | ~5 h |

---

## 5. 跟现有基础设施的复用

### 5.1 已就绪 (Phase 2.5 完成)

✅ **下载脚本** `scripts/download_onchain_bgeo.py` — 加 Tier S 8 个名字到 `CORE_INDICATORS` 即可
✅ **数据落地结构** `data/external/onchain/{indicator}.csv` — 同 schema
✅ **健康检查** `healthcheck.json` — 同机制
✅ **特征模块** `src/features/external.py` — 新增 `build_bgeo_tier_s_features` 即可
✅ **License 评估** — 同 Phase 2.5 (free API 模式)
✅ **生产管道三级降级** — 同 §5.4 Phase 2.5
✅ **CDN 可达性** — 之前 probe 已验证 (11/11 全绿)

### 5.2 唯一新工作量

```python
# scripts/download_onchain_bgeo.py 改动: 几行
TIER_S_INDICATORS = [
    "sopr_data", "puell_multiple_data",
    "nvts", "nvtadj90",
    "cdd", "rhodl_1m",
    "fear_greed_data", "funding_rate",
]

# 兼容旧调用:
CORE_INDICATORS = CORE_INDICATORS  # LTH/STH 6 个不变
ALL_INDICATORS = CORE_INDICATORS + TIER_S_INDICATORS + CANDIDATE_INDICATORS
```

```python
# src/features/external.py
def build_bgeo_tier_s_features(df, cache_dir=...):
    # 加载 8 个 csv → join → 衍生 6 个 × 8 = 48 → 交互 8 → 总 56
```

---

## 6. 验收标准（同 Phase 2.5）

| 指标 | 门槛 |
|---|---|
| **Kappa OOS** | ≥ Phase 2.5 优胜者 × 1.03 |
| **F1 OOS** | ≥ Phase 2.5 优胜者 × 1.03 |
| **Walk-forward fold** | ≥ 8 |
| **Paired t-test** | p < 0.1 |
| **PnL Sharpe** | ≥ Phase 2.5 优胜者 |
| **Top-30 importance** | Tier S 新特征占 ≥ 8/30 |

**未达标**: 进入反面教材库, 不 promote。

---

## 7. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| **Tier S 跟 LTH/STH 高度共线** (rhodl 跟 lth_mvrv 都反映持有者) | 🟡 中 | E22 独立跑, 看相关性矩阵; E23 验证互补性 |
| **特征数 ~250 → 欠拟合** | 🟡 中 | 配合 Phase 3 剪枝 (E25); 必要时 LightGBM 用更深树 |
| **F&G 仅 2018+ → 早期 NaN** | 🟢 低 | fillna + `_isna` 指示, 或限制起始年份 |
| **funding_rate (BGeo) 跟 CMD 口径冲突** | 🟢 低 | 二选一; 默认用 CMD (Binance 主流)|
| **HODL Waves 维度爆炸** (8 时间段 × 6 衍生 = 48) | 🔴 高 | 只作 Tier B 候选, 不放 E22; 若进入则用 PCA 降维 |

---

## 8. 跟 plan 体系的关系

```
Phase 1 ✅ (P0 清污, 已完成)
   ↓
Phase 2.5 (LTH/STH 6 指标 + cmd 12 指标)        ← experiment_matrix_v0601.md
   ↓
Phase 2.6 (BGeo Tier S 8 指标)                   ← 本文档
   ↓
Phase 3 (剪枝)                                    ← feature_engineering_roadmap §3
   ↓
Phase 4 (宏观/ETF/HODL Waves/Address 等)         ← feature_engineering_roadmap §4
```

**严格依赖关系**: Phase 2.6 **不能** 跳过 Phase 2.5。

---

## 9. 不做的事 (YAGNI)

| 方向 | 理由 |
|---|---|
| HODL Waves 32 文件全加 | 维度爆炸; 留作 Phase 4 专题 |
| Address 分类 34 文件 | 同上 |
| 宏观 (M2/FedFunds/SP500) | Phase 4 专题 (跨资产) |
| ETF flows | Phase 4 专题 (2024+ 短历史) |
| Realized Cap 44 个文件 | 大部分是派生品, 信息含量低于 raw cap |
| BGeo 端 `funding_rate` 跟 CMD 二选一 | 选 CMD (主流 + 已在 Phase 2.5 验证) |
| 重复定义 Tier S 算法 | 直接用 BGeo 数据, 不自己算 |

---

## 10. 决策检查清单

启动 Phase 2.6 前确认:

### 10.1 业务上下文检查
- [ ] Phase 2.5 Wave 1-2 完成 (E18a/E18b/E19c/E20 至少 4 个)
- [ ] Phase 2.5 优胜实验已 promote 或明确决策方向
- [ ] 优胜者 Kappa ≥ E1 × 1.05 = 0.3654 (生产基准)

### 10.2 数据基准检查 (2026-06-01 新增, 参考 lesson_0601)
- [ ] **`data.start: '2020-01-01'`** 锁定, 不准改为 2018
- [ ] `data.end: '2025-12-31'` 锁定, 不准扩到 2026+
- [ ] BTC csv 实际 sha256 与上次实验一致 (避免被默默扩充)
- [ ] E1 baseline 能复现 Kappa = 0.3480 ± 0.001 (sanity check)

### 10.3 技术检查
- [ ] `scripts/download_onchain_bgeo.py` 仍正常工作
- [ ] `data/external/onchain/healthcheck.json` 最新一次拉取全绿
- [ ] git working tree clean
- [ ] 准备好 ~5h 时间块
- [ ] 准备好 "Tier S 全失败" 的预案 (跳到 Phase 3 剪枝)

---

## 11. 启动命令模板（条件触发后）

```bash
# Step 1: 扩展下载脚本 + 拉数据
.venv/bin/python scripts/download_onchain_bgeo.py --indicators \
    sopr_data puell_multiple_data nvts nvtadj90 cdd rhodl_1m \
    fear_greed_data funding_rate

# Step 2: VPS 上 commit 数据
git add data/external/onchain/{sopr_data,puell_multiple_data,nvts,nvtadj90,cdd,rhodl_1m,fear_greed_data,funding_rate}.csv
git commit -m "data: 落地 BGeometrics Tier S 8 个核心指标 (Phase 2.6)"

# Step 3: 跑 E22
.venv/bin/python scripts/run_experiment.py \
    --config configs/experiments/weekly/v0608_E22_bgeo_tier_s.yaml \
    --overwrite

# Step 4: 决策报告
.venv/bin/python scripts/compare_experiments.py \
    --ids weekly_bear_v0305_E1_decontam \
          {phase_2.5_winner} \
          v0608_E22_bgeo_tier_s \
    --output docs/reports/phase_2.6_e22_decision.md
```

---

## 12. 后续延展（不在本计划内）

- **Phase 2.7**: HODL Waves 完整族 (8 个时间段, 独立 ablation)
- **Phase 2.8**: Address 持币量级分类 (whale 行为)
- **Phase 4**: 宏观 (M2/FedFunds/SP500) + ETF flows (2024+ 短历史, 但市场结构变化大)

→ 视 Phase 2.6 结论决定优先级。

---

*维护: Phase 2.5 完成后启动本计划; 启动时更新 §4.1 状态; 完成后归档到 `docs/plans/archived/` 并更新 `feature_engineering_roadmap.md`*
