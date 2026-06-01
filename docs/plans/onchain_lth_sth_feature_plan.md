# 链上 LTH/STH 特征工程计划 (Phase 2.5)

> **生成时间**: 2026-06-01
> **作者**: sam
> **前置阅读**:
>   - [`feature_engineering_roadmap.md`](./feature_engineering_roadmap.md) — 全局 Phase 1-4 规划
>   - [`cr_0522_feature_engineering.md`](../reviews/cr_0522_feature_engineering.md) — 7 大问题诊断
> **关联实验**:
>   - `experiments/weekly/v0529_E17_with_external/` — Phase 2 第一次尝试（funding+macro，反面教材）
>   - 待生成: `v0601_E18_onchain_lth_sth`

---

## 0. TL;DR (3 句话)

1. **Phase 2 原计划被 CoinMetrics 付费墙拦了**（`CapRealUSD` 是 paid metric），单一 MVRV 路线走不通。
2. **改道 BGeometrics CDN**（已实测 11/11 HTTP 200，每天 04:06 GMT 实时更新），转向 **6 个 LTH/STH 链上原生指标**，14 年历史、训生产同源。
3. 本计划负责把这 6 个指标 + 衍生 → ~40 个特征，跑 **E18 对照 E1 baseline**，**预算 3 小时**，预期 Kappa 提升 +3-8%。

---

## 1. 背景：Phase 2 路线变更原因

### 1.1 原 Phase 2 假设（feature_engineering_roadmap §2.2）

```
数据源 = CoinMetrics Community API (免费)
字段   = CapMrktCurUSD (MV) + CapRealUSD (RV)
公式   = MVRV ratio = MV / RV
特征数 = 12 (ext_mvrv_*)
```

### 1.2 实测拦截点（2026-06-01 调研）

| 阶段 | 发现 | 影响 |
|---|---|---|
| 第一次尝试 | CoinMetrics `CapRealUSD` 返回 403 | RV metric 是 paid tier |
| 第二次切换 | bitcoin-data.com z-score | ✅ HTTP 200，但**只有 4 年历史**（2022-06+），且跟 bgeometrics csv 在 2023-10-07 后**永久裂开** |
| 第三次深挖 | bgeometrics GitHub repo | ✅ 5462 行 15 年历史，但 **csv 停更 2025-09**，且自己内部 5 个口径并存（自相矛盾）|
| **第四次发现 ⭐** | **bgeometrics LTH/STH 指标族** | ✅ 14 年历史 + **每天实时更新 + GitHub Pages CDN 免费稳定** |

**结论**：单一 MVRV z-score 路线**正式放弃**。MVRV ratio 留作辅助，主线转向 **LTH/STH 行为分类指标**。

### 1.3 为什么 LTH/STH 比单一 MVRV 信息量更大

LTH (Long-Term Holder, 持币 ≥ 155 天) vs STH (Short-Term Holder, < 155 天) 是 Glassnode/CoinMetrics 行业标准分类，行为金融学背书。

| 信号组合 | 解读 | 周期意义 |
|---|---|---|
| LTH MVRV 高 + STH MVRV 低 | 老钱账面盈利 + 新钱深套 | **派发期顶部** ⚠️ |
| LTH MVRV 低 + STH MVRV 低 | 全员深套 | **底部恐慌** ✅ |
| LTH NUPL > 0.75 | 老钱"狂喜区" | 历史顶部前兆 |
| STH SOPR < 1 | 散户割肉 | 恐慌底部 |
| LTH SOPR < 1 | 老钱割肉 | 极罕见，2018/2022 大底 |

**核心优势**（相对单一 MVRV）：
1. ✅ **6 个独立维度**（vs 1 维）
2. ✅ **原生链上指标**（直接基于 UTXO age，无 z-score 窗口选择问题）
3. ✅ **理论意义明确**（行为分化 = 周期信号）
4. ✅ **同 14 年历史 + 每日更新**

---

## 2. 数据源决策矩阵

### 2.1 候选源对比（已实测）

| 源 | 频率 | 历史 | LTH/STH | License | 生产可用 | 决策 |
|---|---|---|---|---|---|---|
| **bgeometrics CDN** | 每天实时 | 2012-01+ | ✅ 完整 | 私有但 free API 模式鼓励使用 | ✅ HTTP 200 已验证 | ⭐ **采用** |
| **bgeometrics REST API** (`api.bgeometrics.com`) | 实时 | 同上 | ⚠️ 需查 endpoint | Free tier | ✅ 0.59s 响应 | 🟡 备用 |
| **bitcoin-data.com API** | 实时 | 2022-06+ | ⚠️ 部分 | Free tier | ✅ | 🟡 单点验证用 |
| `crypto-market-data` repo | 实时 | 2022-12+ | ❌ 没有 | CC BY 4.0 | ✅ | ❌ 无 LTH/STH |
| CoinMetrics free | 实时 | 2010+ | ❌ paid | Free tier limited | ❌ | ❌ paid wall |
| Glassnode | 实时 | 全 | ✅ | $39/月+ | 💰 | ❌ 付费 |

### 2.2 选定方案：bgeometrics CDN 双通道

```
主通道 (生产):
  https://charts.bgeometrics.com/files/{indicator}.json
  - 每天 04:06 GMT 自动更新
  - GitHub Pages CDN, 全球可达
  - 11 个核心 JSON 实测全绿

备用通道 (容错):
  https://bitcoin-data.com/v1/{endpoint}/last
  - REST API, 单点查询
  - 主通道挂了 fallback
```

### 2.3 License 评估结论

| 维度 | 评估 |
|---|---|
| `LICENSE.md` 表面文字 | "can not be copied and/or distributed without express permission" |
| 实际使用预期 | `bitcoin_api.html` 明确写 **"On-Chain API Free"** + "subscription is available for premium" |
| 网站官方 JS 用同 URL | `fetch('https://charts.bgeometrics.com/files/' + metric + '.json')` |
| 我们的用途 | 内部研究 + 模型生产推理（不重新分发数据）|
| **判定** | ✅ **符合预期使用方式**，不违反 license。如未来商业化部署对外服务 → 礼貌邮件确认 |

---

## 3. 特征矩阵设计 (~40 特征)

### 3.1 数据集（11 个 JSON → 6 个核心 + 5 个候选）

| 文件 | 起始 | 行数 | 角色 |
|---|---|---|---|
| `lth_mvrv.json` | 2012-01-01 | 5253 | 🔴 核心 |
| `sth_mvrv.json` | 2013-01-02 | 4886 | 🔴 核心 |
| `lth_nupl.json` | 2013-01-01 | 4882 | 🔴 核心 |
| `sth_nupl.json` | 2013-01-01 | 4882 | 🔴 核心 |
| `lth_sopr.json` | 2012-01-01 | 5249 | 🔴 核心 |
| `sth_sopr.json` | 2012-01-01 | 5249 | 🔴 核心 |
| `aviv.json` | 2010-07-19 | 5789 | 🟡 候选 (最长历史) |
| `reserve_risk.json` | 2012-01-01 | 5101 | 🟡 候选 |
| `mvrv_data.json` | 2012-01-01 | 5253 | 🟡 候选 (raw MVRV ratio) |
| `mvrv_zscore_data.json` | 2012-01-01 | 5253 | 🟡 候选 (z-score 现役口径) |
| `nupl_data.json` | 2013-01-01 | 4886 | 🟡 候选 |

### 3.2 特征族设计（6 核心指标 × ~6 衍生 + 8 交互 ≈ 44 特征）

每个核心指标 (lth_mvrv/sth_mvrv/lth_nupl/sth_nupl/lth_sopr/sth_sopr) 衍生 6 个：

```
ext_{indicator}              — 原始值 (T-0)
ext_{indicator}_ma_7         — 7 日均值 (短期平滑)
ext_{indicator}_ma_30        — 30 日均值 (中期平滑)
ext_{indicator}_change_7     — 7 日环比变化 (短期动量)
ext_{indicator}_change_30    — 30 日环比变化 (中期动量)
ext_{indicator}_slope_30     — 30 日线性斜率 (趋势加速度)
```

→ 6 × 6 = **36 个基础特征**

### 3.3 LTH/STH 行为分化特征 (8 个交互)

这才是 LTH/STH 框架的真正价值——单看 lth 或 sth 都不如**对比**有信息量：

```python
ext_mvrv_lth_sth_diff       = lth_mvrv - sth_mvrv          # 派发期检测
ext_mvrv_lth_sth_ratio      = lth_mvrv / (sth_mvrv + 1e-6) # 相对比率
ext_nupl_lth_sth_diff       = lth_nupl - sth_nupl          # 情绪分化
ext_nupl_lth_sth_ratio      = lth_nupl / (sth_nupl + 1e-6)
ext_sopr_lth_sth_diff       = lth_sopr - sth_sopr          # 抛压分化
ext_lth_capitulation        = (lth_sopr < 1.0).astype(int) # 老钱割肉信号
ext_sth_panic               = (sth_sopr < 1.0).astype(int) # 散户恐慌
ext_lth_euphoria            = (lth_nupl > 0.75).astype(int) # 老钱狂喜
```

→ **8 个交互特征**

### 3.4 不做的事（YAGNI）

明确**不**纳入本计划（避免过度拟合 + 维度爆炸）：

- ❌ Z-score 风格的滚动百分位（前期调研发现"窗口选择"陷阱很深）
- ❌ aviv/reserve_risk 进入 E18（留到 E18 验证有效后做 E18.5 ablation）
- ❌ raw MVRV ratio 进入 E18（已被 LTH/STH MVRV 维度覆盖）
- ❌ STH/LTH realized price（价格类，跟现有 price 特征高度共线）
- ❌ 4 日/100 日等额外 MA 窗口（仅 ma_7/30 已够，多了引入噪音）

---

## 4. 实验路线图

### 4.1 实验设计（对照隔离 LTH/STH 净贡献）

| ID | Config Name | 特征集 | 目的 |
|---|---|---|---|
| **E1** (baseline) | `weekly_bear_v0305_E1_decontam` | 原始 124 特征 | 基线 |
| **E18a** | `v0601_E18a_onchain_core6` | E1 + 6 核心 LTH/STH (36 特征) | 隔离"6 指标基础值"贡献 |
| **E18b** | `v0601_E18b_onchain_full` | E1 + 6 核心 + 8 交互 (44 特征) | 隔离"行为分化"附加贡献 |
| **E18c** *(可选)* | `v0601_E18c_onchain_extras` | E18b + aviv + reserve_risk | 验证候选指标是否值得加 |

**对照逻辑**：
- E18a vs E1 → 单指标价值
- E18b vs E18a → 交互特征价值
- E18c vs E18b → 额外候选价值（如无显著提升则不加）

### 4.2 验收标准（机构级门槛）

| 指标 | 门槛 | 来源 |
|---|---|---|
| **Kappa OOS** | ≥ E1 × 1.05 (相对提升 ≥5%) | 实战门槛 |
| **F1 OOS** | ≥ E1 × 1.05 | 实战门槛 |
| **Walk-forward fold ≥ 8** | 必须 | `OPS_MANUAL §2.3` |
| **Paired t-test on Kappa** | p < 0.1 | `OPS_MANUAL §2.3` |
| **PnL Sharpe** | ≥ E1 | `OPS_MANUAL §2.3` |
| **特征重要性** | LTH/STH 类特征占 top-20 ≥ 5 个 | 否则说明模型没用上 |

**如果未达标**：
- 不 promote
- 写 `experiments/weekly/v0601_E18*/CONCLUSION.md` 说明负面发现
- 跟 E17 一样进入"反面教材库"

### 4.3 时间预算（总 ~3 小时）

| 步骤 | 预估 |
|---|---|
| 1. 写 `scripts/download_onchain_bgeo.py` (下载 + CSV 化) | 30 min |
| 2. 在 VPS 上首次拉数据 + git commit | 10 min |
| 3. 在 `src/features/external.py` 新增 `build_onchain_lth_sth_features` | 45 min |
| 4. 写 E18a + E18b config | 15 min |
| 5. 跑 E18a + E18b (LightGBM, walk-forward) | 30 min |
| 6. 写 `experiments/weekly/v0601_E18*/CONCLUSION.md` 对比报告 | 30 min |
| **合计** | **~2.5h** |

如果 E18b 显著 → 走 promotion SOP（额外 1h）。

---

## 5. 生产数据管道设计

### 5.1 拉取脚本（`scripts/download_onchain_bgeo.py`）

```python
# 伪代码
INDICATORS = ["lth_mvrv", "sth_mvrv", "lth_nupl", "sth_nupl",
              "lth_sopr", "sth_sopr"]

def download_one(name: str) -> pd.DataFrame:
    url = f"https://charts.bgeometrics.com/files/{name}.json"
    data = requests.get(url, timeout=30).json()
    df = pd.DataFrame(data, columns=["ts", "value"])
    df["date"] = pd.to_datetime(df["ts"], unit="ms").dt.normalize()
    return df.set_index("date")[["value"]].rename(columns={"value": name})

# 输出: data/external/onchain/{indicator}.csv
```

### 5.2 调度集成

```bash
# 加入现有 daily cron 流程 (deploy_v0305.sh)
# 在 weekly_signal.py --download 步骤前插入:
python scripts/download_onchain_bgeo.py --cache-dir data/external/onchain/
```

### 5.3 健康监测（防数据源静默挂掉）

| 检查项 | 阈值 | 动作 |
|---|---|---|
| HTTP status != 200 | 任一失败 | 报警 + fallback 上次缓存 |
| 末条日期 < 今天 - 2 天 | 数据 stale | 报警 (不阻塞推理) |
| 文件大小 < 上次 × 0.5 | 内容异常 | 拒绝写入 + 保留旧缓存 |
| SHA256 跟上次完全一样 | 数据未更新 | warn (不阻塞) |

放在 `scripts/download_onchain_bgeo.py` 内部，写入 `data/external/onchain/healthcheck.json`。

### 5.4 离线/降级策略

```
正常: 用 charts.bgeometrics.com CDN
降级 1: CDN 失败 → 用 bitcoin-data.com API (单 endpoint)
降级 2: API 也失败 → 用本地缓存最近一份 (最多 stale 7 天)
降级 3: 缓存 stale > 7 天 → live_signal halt + 报警
```

---

## 6. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| **数据源单点依赖**（bgeometrics 挂了）| 🔴 高 | 5.4 三级降级策略 |
| **License 灰色地带** | 🟡 中 | 内部研究 OK；商业部署前邮件确认 |
| **历史回填 vs 实时口径漂移** | 🟡 中 | 一次性回填后每天增量；SHA256 校验防静默替换 |
| **过拟合 LTH/STH 阈值**（如 sopr<1 这种）| 🟡 中 | 阈值特征仅作辅助；连续值作主信号 |
| **CDN 数据格式变更** | 🟢 低 | 拉取脚本带 schema 校验，异常拒绝写入 |
| **特征数从 124 → 168 引入欠拟合** | 🟡 中 | 用 `feature_importance` 验证；必要时配合 Phase 3 剪枝 |
| **训练集时间错位**（LTH SOPR 从 2012-01 vs 现有特征从 2018-01）| 🟢 低 | 用 `inner join`，损失早期 LTH 数据无影响 |

---

## 7. 跟现有项目的兼容性

### 7.1 文件落点（不破坏现有结构）

```
data/external/onchain/                  ← 新增目录
  ├─ lth_mvrv.csv
  ├─ sth_mvrv.csv
  ├─ ... (6 个)
  └─ healthcheck.json

scripts/
  ├─ download_onchain_bgeo.py           ← 新增
  └─ probe_bgeometrics_cdn.sh           ← 已有 (探测脚本)

src/features/
  └─ external.py                         ← 在现有文件新增 build_onchain_lth_sth_features

configs/experiments/weekly/
  ├─ v0601_E18a_onchain_core6.yaml      ← 新增
  └─ v0601_E18b_onchain_full.yaml       ← 新增
```

### 7.2 不动的代码

- ❌ 不改 `src/features/market_structure.py`（Phase 1 重命名后稳定）
- ❌ 不改 `src/features/technical.py`
- ❌ 不改 `src/models/`
- ❌ 不改 production E1/E8 model（实验隔离）

### 7.3 跟 Phase 3 剪枝的关系

- 本计划新增 ~44 特征 → 总数 124 → ~168
- 若 E18 successful → 先 promote E18，再做 Phase 3 剪枝（在更大 base 上剪）
- 若 E18 failed → 不影响 Phase 3 推进

---

## 8. 决策检查清单

实施前确认：

- [ ] CDN probe 全绿（已 ✅ 2026-06-01）
- [ ] 已 git commit `scripts/probe_bgeometrics_cdn.sh`（已 ✅ commit 4602d50）
- [ ] 当前生产模型 E1/E8 bit-exact 守门绿
- [ ] 已通读 `feature_engineering_roadmap.md` Phase 1-4 全局
- [ ] 已对齐 `OPS_MANUAL.md` §2-§3 实验规范
- [ ] 准备好被否定的心理（E17 反面教材殷鉴在前）

---

## 9. 时间节点

| 节点 | 目标 | Deadline |
|---|---|---|
| T+0 | 本 plan 评审通过 | 2026-06-01 |
| T+1 | 下载脚本 + 数据落地 + 特征模块完成 | 2026-06-02 |
| T+2 | E18a/E18b 训练完成 + 对比报告 | 2026-06-03 |
| T+3 | 决策: promote / 继续 ablation / 归档 | 2026-06-04 |

---

## 10. 后续延展（不在本计划内）

- **LTH/STH Momentum** (HTML 文档提到的衍生指标族)
- **Bitcoin Cycle Analytics** (Profitable Days, LTH/STH Absorption Rate)
- **Realized Price 系列**（lth_realized_price, sth_realized_price）
- **真衍生品 OI / Funding** (`sync_binance_oi_ls.py` 启用)
- **跨资产** (BTC dominance, ETH/BTC ratio)

→ 视 E18 结论与 Phase 3 优先级决定。

---

## 7. 阶段结论 (2026-06-01 更新)

### 7.1 E18a 实验结果 (公平基准 2020-2025)

| 实验 | features | kappa | f1 | precision | recall |
|---|---|---|---|---|---|
| E1 baseline (复现 ✅ bit-exact) | 129 | **0.3480** | 0.4161 | 0.4085 | 0.4240 |
| E18a (+36 LTH/STH 衰 生) | 165 | 0.3244 | 0.3929 | 0.3970 | 0.3889 |
| **差额** | +36 | **-6.8%** | -5.6% | -2.8% | -8.3% |

**门槛**: Kappa ≥ E1 × 1.05 = 0.3654 → **未达标**.

### 7.2 判定: LTH/STH 路线 在 weekly bear 任务上 ⚠️ 无显著 alpha

- LightGBM feature importance: 36 个特征 0 个废, top-50 占 10/50 (按比例分布)
- `ext_lth_sopr_ma_30` 排 #8 (top-10), 但整体 precision/recall 轻微下降
- **推测原因**: LTH/STH 是周期级慢变量 (>180 天), 跟 weekly bear (T=21) 锁定错配.
  经 ma_30 / slope_30 衰生后更慢, 在持续 bear 期发出大量假信号。

### 7.3 后续路线

按 plan 决策树 (experiment_matrix_v0601.md §4):

- ⛔ **E18b/E18c 暂停** (在 LTH/STH base 上加交互/extras 不可能挤上去)
- ⛔ **Phase 2.6 (Tier S) 启动条件未满足** (需首个路线显著)
- ✅ **转 Wave 2: E19 (crypto-market-data 12 个 Tier 1 衡量)** —
  衡量品质独立 (Glassnode/CryptoQuant 口径), 含 funding/OI 真实数据,
  应优于 LTH/STH 慢变量

### 7.4 LTH/STH 未被育拓的窗状 (备查)

并未证明 LTH/STH 本身不灵, 仅表明在现有 (T=21, X=4%) 任务 + 现有 LightGBM 决策阶下不灵.
值得后续探索的场景:

- **Monthly bear** (T=63 或更长) — 时间尺度匹配慢变量
- **Bull market filter** — 仅用 LTH NUPL 提供 regime 输入, 不作为分类特征
- **Regime-conditional model** — 跟 200d MA 配合, 在 bull regime 启用 LTH/STH
- **As probability calibration input** — 不参与训练, 作为后置过滤

### 7.5 数据基础设施 (Phase 2.5 遗产)

虽然 E18a 失败, 但本阶段建立的基础设施仍然有效:

- ✅ `scripts/download_onchain_bgeo.py` — 11 个 BGeo 指标拉取脚本
- ✅ `data/external/onchain/*.csv` — 11 个指标 + healthcheck.json (已 commit)
- ✅ `src/features/external.py` 新增 `_load_onchain_csv` / `_load_onchain_series` helper
- ✅ `build_lth_sth_core_features` / `build_lth_sth_interactions` builders
- ✅ `docs/plans/bgeometrics_tier_s_expansion_v0608.md` (Phase 2.6 待启动)

→ Tier S 实验 (E22+) 可在未来其它任务 (monthly/bull) 中复用.

---

*维护: 本计划随 E18 实验进展更新；归档触发条件 = 实验完成 + CONCLUSION.md 写完。*
*2026-06-01: §7 阶段结论新增, 标记 E18 路线在 weekly bear 任务终止.*
