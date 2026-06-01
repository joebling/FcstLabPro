# Phase 2.5 特征工程战略

> **状态**: 🟢 活动主文档
> **前置阅读**:
>   - `docs/lessons/lesson_0601_data_governance_regime_shift.md` ⚠️ **必读** (数据治理铁律由来)
>   - `docs/plans/feature_engineering_roadmap.md` (Phase 1-4 全局)
>   - `docs/ops/OPS_MANUAL.md` §2-§3 (实验规范)

---

## 0. TL;DR

**Phase 2.5 = 在 2020-2025 锁定基准上, 用 BGeo 长历史指标 (≥ 12 年) 给 weekly bear 模型寻找
正交 alpha**, 通过 7 个并行 sub-experiment (E19-PUELL/SOPR-NEW/MVRV-EXT/ADDRESS/STABLE/AVIV/DERIV-SHORT)
验证. 每 sub ≤ 1.5h, 全部跟 E1 baseline (Kappa 0.3480) 对比, 门槛 Kappa ≥ 0.3654 (+5%).

**核心约束**:
- 慢变量必须 short-horizon 转换 (raw level 禁进特征集)
- 候选指标必须通过 `audit_bgeo_nan.py` 数据卫生检 (cov ≥ 95%, stale ≤ 90d)
- 基准数据 sha256 锁定, 任何变动必先验证 E1 bit-exact

---

## 1. 数据源真实画像 (CMD vs BGeo)

### 1.1 数据源对比

| 维度 | CMD (`crypto-market-data`) | BGeo (`bgeometrics.github.io`) |
|---|---|---|
| **文件数** | 29 JSON | 437 JSON (419 可解析) |
| **历史长度** | 全部 2022-12-03 起 (3.5 年) | 2010-07 ~ 2026, 不等 |
| **schema** | `{data: [...], ...}` (dict) | `[[ts, val], ...]` (list-of-pairs) |
| **链上长历史** | 🔴 无 (全 2022+) | 🟢 极强 (239 个 2012+, 14 年) |
| **衍生品** | 🟢 强 (funding/OI/liq/taker) | 🟡 部分 (OI 2020-08+) |
| **定位** | 衍生品 + 短历史链上备份源 | **Phase 2.5 主战场** |

### 1.2 BGeo 历史长度分布 (419 可解析 JSON)

| 起始年份 | 指标数 | 占比 |
|---|---|---|
| ≤ 2012 | **239** | 57% |
| 2013-2014 | 78 | 19% |
| 2015-2017 | 21 | 5% |
| 2018-2020 | 23 | 5% |
| 2021-2022 | 26 | 6% |
| 2023+ | 32 | 8% |

### 1.3 CMD 的真实价值

CMD 是 "**衍生品 + 短历史链上的备份源**":

- ✅ **liquidations (long/short)** — 唯一公开源 (BGeo 无, Binance API 无历史)
- ✅ **funding_rates / open_interest** — 2022+ 高质量
- ✅ **taker_buy_sell_ratio** — 短期资金流向
- ❌ **链上长历史** — 全部 < 4 年, 远不如 BGeo
- ❌ **exchange_netflow, miner_netflow** — 信号未必比 BGeo 长历史替代品强

---

## 2. 联合特征空间

> **总量**: 29 CMD + 437 BGeo raw JSON = 466 文件; 去重 + audit 后实际可用约 80-120 个.

### 2.1 矩阵概览 (代表性指标)

| 类别 | 长历史源 (≥ 2017, 推荐) | 短历史源 (2022+, NaN-aware) |
|---|---|---|
| **周期 Valuation** | `puell_multiple_data` (2012), `mvrv_data` (2012), `mvrv_zscore_*`, `aviv` (2010), `lth_nupl` (2013) | CMD `btc_mvrv_ratio` |
| **SOPR 家族** | `sopr_data`, `lth_sopr`, `sth_sopr`, `cdd`, `cdd_terminal_ajusted` (全 2012+) | — |
| **Address (HODL Waves)** | `address_*` 12 档 (2012+), `addresses_active` (2010), `realized_cap` (2011) | — |
| **Stablecoin** | `stablecoin_usdt/dai/pax/usdc/busd` (2017+) | CMD `stablecoin_exchange_netflow` (2022+) |
| **Funding Rate** | BGeo `funding_rate.json` (2023-07+) ❌ 短, 且 schema 不兼容 daily reindex (audit coverage 0%) | CMD `btc_funding_rates` (2022-12+) |
| **Open Interest** | (BGeo `open_interest_futures_btc_price` 是 BTC 价格副轴, ❌ 禁用; 见 §3 铁律) | CMD `btc_open_interest` (2022-12+) |
| **Taker Buy/Sell** | — | CMD `btc_taker_buy_sell_ratio` (2022+) |
| **Liquidations** | — | CMD `btc_long/short_liquidations` (2022+) ⚠️ **唯一源** |
| **Coinbase Premium** | — | CMD `btc_coinbase_premium_index` (2022+) |
| **Exchange Flow** | (BGeo `inflow_exchanges_btc` 已停 2024-06, 不可用) | CMD `btc_exchange_netflow`, `whale_ratio` (2022+) |

### 2.2 数据分级标准 (audit 实测)

候选指标通过 `scripts/audit_bgeo_nan.py` 在 2020-2025 BTC 基准日历上 align 后分级:

| 等级 | 定义 | 实验策略 |
|---|---|---|
| **L0: 严格 0 NaN** | align 后 0 NaN + 0 前导 null + stale ≤ 90d | (理论等级, BGeo 实测 0 个) |
| **L1: 高覆盖** | align cov ≥ 95% 且 stale ≤ 90d | 加入特征集, ffill_then_drop 不因偶发缺口大量丢行 (但 rolling 派生仍按窗口自然丢前置: `zscore_90` 丢 89 行, `slope_30` 丢 29 行) |
| **L2: 中覆盖** | align cov 70-95% 且 stale ≤ 90d | NaN-aware (改 builder) 或截断, CMD 全部 |
| **L3: 不可靠** | stale > 90d 或 cov < 70% | 不用 |

**关键事实** (来自 `data/external/onchain/nan_audit.json`):
- 严格 L0 在 BGeo 不存在 (所有指标都有 10-20 align-NaN, 由周末/季度边界造成)
- **L1 + ffill_then_drop 是实际工作面**
- `stale_d` 是关键维度: BGeo 大量起始早的指标已停更 200+ 天, 必须 stale ≤ 90d 才可用

### 2.3 同族变体去重规则 (遵守 OPS_MANUAL §4.1 剪枝原则)

> **背景**: BGeo 同一指标有大量变体 (`mvrv_*` 16 个, `hw_age_*` **47 个**, `address_*` 34 个).
> 直接全推入会造成严重共线性 + 违反 "全量特征 >100 欠拟合" 原则.

**统一筛选规则** (适用所有 sub-experiment):

1. **仅取 canonical 版本** — 优先 `_data` 后缀 (`mvrv_data`, `sopr_data`, `puell_multiple_data`),
   丢弃 `_tmp` / `_bg` / `_all` / `_btc_price` / `_latest` 变体
2. **同族变换限 1-2 个主要派生** — 如 mvrv 16 个选 5: `data`, `365dma`, `diff`, `zscore_data`, `btc_price`
3. **address_* 按仓位档位代表性取** — 34 个选 4-5: `address_01_1` (散户), `_10_100` (中户),
   `_100_1000` (大户), `_10k_1k` (鲸鱼), `addresses_active` (总活跃)
4. **hw_age_* (HODL Waves)** — 47 个选 3-5 跨越热-冷仓: `1m / 6m / 1y / 2y / 5y+`
5. **同族选择决策必须写进 sub config description**, 例如:
   ```yaml
   experiment:
     description: |
       E19-MVRV-EXT: 从 BGeo mvrv_* 16 个变体中按 §2.3 规则选 5 个 canonical:
       data, 365dma, diff, zscore_data, btc_price
   ```

---

## 3. 数据治理铁律

| 规则 | 值 | 依据 |
|---|---|---|
| 基准 `data.start` | `'2020-01-01'` 锁定 | lesson_0601 §3 (regime shift) |
| 基准 `data.end` | `'2025-12-31'` 锁定 | lesson_0601 §3 (避免泄漏未来) |
| BTC csv sha256 | `004bf0706559e0a79a4361c9a0db27d5acb07d72556499df0e081879017c7858` (必填 `expected_sha256`) | runner.py §B 校验 |
| BTC csv expected_rows | 必填 `expected_effective_rows: 2192` | 同上 |
| **Onchain features availability lag** | 默认 `shift(1)` (t 日决策不可使用 t 日链上数据) | Layer 0 未来函数防护 |
| **BGeo `*_btc_price.json` 全系列禁止作特征** | 实测 68 个该后缀文件全部 = BTC close (ratio ≈ 0.998), 是绘图副轴数据 | 数据泄漏 + 与 OHLCV 共线 |
| Builder 改动 | 必须先跑 E1 bit-exact 复现, diff > 1e-12 立即回滚 | OPS_MANUAL §5.3 |

---

## 4. 设计原则 (7 条)

1. **小步快跑**: 每个 sub-experiment ≤ 1.5h, 失败立即停止
2. **L1 优先**: 长历史 BGeo 实测可用指标先做, 数据治理风险最低
3. **正交假设**: 每 sub 覆盖不同 alpha 来源 (周期 / 行为 / 结构 / 高频)
4. **公平基准**: 全部 2020-2025, 跟 E1 baseline (Kappa 0.3480) 对比
5. **门槛**: Kappa ≥ E1 × 1.05 = **0.3654** 才考虑下一步
6. **⚠️ 慢变量纪律**:
   - **raw level 禁止直接进特征集**
   - 任何 >30 天周期指标必须先做 short-horizon 转换:
     `zscore_30/90`, `slope_7/30`, `momentum_7`, `percentile_rank_180`
   - **依据**: E18a (LTH/STH +36 特征) Kappa -6.8%, 因为周期级慢变量 (>180d)
     与 weekly bear (T=21) 任务尺度严重错配, ma_30/slope_30 衰生后仍过慢
   - **例外**: 仅 "作为 regime 标记" 需要原始 level 时 (如 `mvrv_zscore < -2` 代表极深熟市),
     允许例外, 需在 sub config 明示
7. **🔒 数据卫生硬阻塞** (audit 驱动):
   - 任何 BGeo 候选指标必须先过 `scripts/audit_bgeo_nan.py`, 达标:
     - `coverage ≥ 95%` (与 BTC 基准 align 后)
     - `stale_d ≤ 90` (最后数据距今 ≤ 90 天)
     - `align_NaN < 30`
     - `leading_nulls_after_2020 = 0`
   - 不达标拒绝, 不写进 sub config. 结果入库 `data/external/onchain/nan_audit.json`

---

## 5. Sub-Experiments 矩阵 (7 个并行)

### 5.1 E19-PUELL ⭐ 优先级 1

| 字段 | 值 |
|---|---|
| 假设 | Puell Multiple (Charles Edwards 经典周期 indicator) 提供 "周期顶/底" 信号 |
| 数据源 | BGeo `puell_multiple_data.json` (2012-2025, 14 年, L1: cov 99.5%, stale 2d) |
| 新增特征 | 1 × 5 = 5 (`zscore_30/90`, `slope_7/30`, `momentum_7`), **不含 raw** |
| 时间预算 | 30 min |
| 优势 | 单一指标快速验证, 经典机构信号, 长历史 |

### 5.2 E19-SOPR-NEW ⭐ 优先级 2

| 字段 | 值 |
|---|---|
| 假设 | SOPR (Spent Output Profit Ratio) + CDD (Coin Days Destroyed) 是 "实现盈利/亏损" 行为信号, 跨周期稳定 |
| 数据源 | BGeo 5 个: `sopr_data`, `lth_sopr`, `sth_sopr`, `cdd`, `cdd_terminal_ajusted` (全 2012+, L1: cov 99.3-99.5%, stale ≤ 2d) |
| 新增特征 | 5 × 5 = 25 (`zscore_30/90`, `slope_7/30`, `momentum_7`), **不含 raw** |
| 时间预算 | 45 min |
| 关联 | SOPR 顶层 + CDD 与 E18a 失败的 LTH/STH NUPL 完全独立信息维度 |
| 风险 | `lth_sopr`/`sth_sopr` 与 LTH/STH 同源, 可能也是慢变量 (#6 衍生应能缓解) |

### 5.3 E19-MVRV-EXT

| 字段 | 值 |
|---|---|
| 假设 | MVRV Z-Score 多种 representation 在不同周期阶段强弱不同 |
| 数据源 | BGeo 4 个 (§2.3 筛选): `mvrv_data`, `mvrv_365dma`, `mvrv_diff`, `mvrv_zscore_data` (全 L1: cov 99.5%, stale 2d). ⚠️ `mvrv_btc_price` 实测 = BTC close (ratio 0.998), 不可用 (§3 铁律) |
| 新增特征 | 4 × 5 = 20, **不含 raw**. **例外**: `mvrv_zscore_data` 保留 raw level 作 regime 标记 (config 明示) |
| 时间预算 | 45 min |
| 关联 | E18a 用过 LTH/STH MVRV 但没用过总体 MVRV variants |

### 5.4 E19-ADDRESS ⭐ 优先级 3 (HODL Waves)

| 字段 | 值 |
|---|---|
| 假设 | 不同档位地址数变化代表 "散户/中户/机构/鲸鱼" 行为分化, 提供 holder 结构信号 |
| 数据源 | BGeo 5 个: `address_01_1`, `address_10_100`, `address_100_1000`, `addresses_active`, `realized_cap` (2010-2012 起, L1: cov 99.1-99.5%, stale 2-36d) |
| 新增特征 | 5 × 5 = 25 (`zscore_30/90`, `slope_30`, `pct_chg_30`, `momentum_7`), **不含 raw** |
| 时间预算 | 45 min |
| 优势 | 真实 holder 结构, 跟价格/链上活动正交; `realized_cap` 是 Glassnode 旗舰指标 |

### 5.5 E19-STABLE

| 字段 | 值 |
|---|---|
| 假设 | 稳定币供给变化代表 "待入场购买力" (Lyn Alden 论点) |
| 数据源 | BGeo 5 个: `stablecoin_usdt`, `stablecoin_dai`, `stablecoin_pax`, `stablecoin_usdc`, `stablecoin_busd` (全 L1: cov 99.5%, stale 2d) |
| 新增特征 | 5 × 5 = 25 (`zscore_30/90`, `slope_7/30`, `pct_chg_30`), **不含 raw** |
| 时间预算 | 45 min |
| 风险 | BUSD 2023-02 后停发新铸, 流通量数据仍刷新但信号可能衰减 |

### 5.6 E19-AVIV (单点扩展)

| 字段 | 值 |
|---|---|
| 假设 | AVIV (Active Value Index Verified) 是 ChainExposed 派的 "活跃 BTC 价值" 周期 indicator, 跨多个周期峰底 |
| 数据源 | BGeo `aviv.json` (2010-2026, **16 年**, L1: cov 99.7%, stale 1d) |
| 新增特征 | 1 × 5 = 5 (`zscore_30/90`, `slope_7/30`, `momentum_7`) |
| 时间预算 | 30 min |
| 优势 | BGeo 最长历史指标之一, 跨 4 个减半周期 |

### 5.7 E19-DERIV-SHORT (NaN-aware 改造前置)

| 字段 | 值 |
|---|---|
| 假设 | 衍生品高频信号 (funding/OI/taker/liq) 提供短期风险溢价 |
| 数据源 | CMD 6 个 (L2): `btc_funding_rates`, `btc_open_interest`, `btc_taker_buy_sell_ratio`, `btc_long_liquidations`, `btc_short_liquidations`, `btc_coinbase_premium_index` (全 2022-12+) |
| 前置 | 改 `src/features/builder.py` 加 `keep_nan_features` 选项 (LightGBM 原生支持 NaN) — §7 ⛔ 硬阻塞 |
| 新增特征 | 6 × 5 = 30, **不含 raw** (衍生品本身已高频, 但 `funding/OI` 的 `ma_7/zscore_90` 比 raw 更稳) |
| 时间预算 | 1.5h (含改 builder + bit-exact 测试 + 跑) |
| 风险 | 2020-2022 全 NaN (占基准 48.7%), 模型可能学到 "NaN = 早 regime / 非 NaN = 晚 regime" 而非真信号 |
| **基准修订** | ⚠️ **必须用 2022-12-03 起同窗 E1 baseline 对比**, 不可直接对比 2020-2025 E1 (否则上述 regime proxy 风险无法控制). 具体: 重跑 `exp_v0305_E1_decontam` 但锁 `data.start: '2022-12-03'`, 命名 `e1-baseline-2022q4`, 用此作 DERIV-SHORT 的对照组 |

---

## 6. 执行顺序与决策

### 6.1 推荐执行顺序

```
E19-PUELL (30 min, 最稳)
    ├─ Kappa ≥ 0.365: 进 E19-SOPR-NEW (验证全新长历史方向)
    │                       ├─ 成功 → E19-MVRV-EXT (验证家族扩展)
    │                       │             └─ 成功 → E19-ADDRESS (验证 HODL 结构)
    │                       │                           └─ 成功 → E19-AVIV / E19-STABLE
    │                       └─ 失败 → E19-AVIV (单点最长历史 16 年终极测试)
    └─ Kappa < 0.348: 失败 → 跳过所有慢变量 sub
                                ↓
                       直接 E19-DERIV-SHORT (短历史高频, 完全不同尺度)
                                ↓
                       仍失败 → 转 Phase 3 剪枝
```

**关键决策点**:
- **PUELL + SOPR 任一成功** → BGeo 长历史方向有 alpha, 继续展开
- **PUELL + SOPR 全失败** → 慢变量在 weekly bear 系统性无效, 必须换高频
- **DERIV-SHORT 失败** → Phase 2.5 整体结束, 转 Phase 3

### 6.2 决策树 (基于 E1 baseline Kappa = 0.3480)

| 单个 sub Kappa | 行动 |
|---|---|
| ≥ 0.40 | 🟢 强 alpha, 立即 promote 候选, 进入 ensemble + interaction 探索 |
| 0.365 ~ 0.40 | 🟢 弱 alpha 达门槛, 继续展开 (加 interactions) |
| 0.348 ~ 0.365 | 🟡 持平, 视计算成本决定是否保留 |
| < 0.348 | 🔴 拒绝, 此方向噪声 > 信号, 终止 |

---

## 7. 工程就绪状态

### 7.1 已就绪 ✅

| 项 | 位置 |
|---|---|
| 数据治理事件归档 | `docs/lessons/lesson_0601_data_governance_regime_shift.md` |
| Loader sha256 + effective_rows 校验 | `src/data/loader.py` |
| Runner 透传 expected_sha256 | `src/experiment/runner.py` |
| BGeo 11 指标拉取脚本 | `scripts/download_onchain_bgeo.py` |
| `_load_onchain_csv` / `_load_onchain_series` helper | `src/features/external.py` |
| **Audit 脚本** | `scripts/audit_bgeo_nan.py` |
| **Audit 结果库** | `data/external/onchain/nan_audit.json` |

### 7.2 Wave 2 启动前待办

- [ ] `scripts/download_bgeo_long_history.py` (扩展支持 puell/mvrv/sopr/cdd/address/aviv/stablecoin 系列)
- [ ] 所有 v0601+ config 强制加 `expected_sha256` (CI 检查)
- [ ] `src/features/external.py` short-horizon 衍生 helper (§4 #6 依赖):
  - `zscore_N`, `slope_N`, `momentum_N`, `pct_chg_N`, `percentile_rank_N`
- [ ] **可选**: 扩充 audit 范围, 扫 200+ BGeo 长历史指标, 生成完整 L1 可用清单 (供 Phase 3 用)

### 7.3 E19-DERIV-SHORT 专属前置 ⛔ 硬阻塞

- [ ] `src/features/builder.py` 加 `keep_nan_features: list[str]` 选项
- [ ] LightGBM 验证: 含 NaN 列训练正常, 不一致行不被 drop
- [ ] ⛔ **硬阻塞**: E1 bit-exact 复现测试 (OPS_MANUAL §5.3), 任一 metric diff > 1e-12 立即回滚 builder 修改

---

## 8. 验收准则

### 8.1 每个 sub-experiment 必含

- `meta.json` 含 `data.sha256`, `data.effective_rows`, `data.effective_start/end`
- `metrics.json` 含 `kappa/f1/precision/recall/accuracy`
- `fold_metrics.csv` 至少 50+ folds (init_train=800, oos_window=63 默认)
- `report.md` 包含跟 E1 baseline 的对比表
- `feature_importance.csv` 显示新增特征排名分布

### 8.2 反 over-fitting 纪律

**禁止**:
- ❌ sub 失败后反复调超参数让它 "看起来更好"
- ❌ 减少 `init_train` 让 fold 数变化重测
- ❌ 改 `oos_window` 让 metrics 涨

**允许**:
- ✅ 失败 sub 单独写一段 CONCLUSION 段落 (本文 §5 对应 sub 下), 然后**关闭**该方向
- ✅ 成功 sub 进入下一阶段 (加 interactions, ensemble 等)

---

## 9. 已知失败方向 (避免重复试)

- **LTH/STH 6 核心指标** (E18a, 165 features, Kappa 0.3244 vs E1 0.3480, -6.8%): 周期级慢变量 (>180d) 与 weekly bear (T=21) 尺度严重错配. **教训沉淀为 §4 设计原则 #6**. 详见 `docs/plans/archive/` + `onchain_lth_sth_feature_plan.md` §7.
- **Miner 系列** (miner_balance / out_flows / reserves / sell_presure): BGeo 矿工数据全部停更 200+ 天, 不可用. 未来如有 CryptoQuant 等公开源可重启.

---

*维护原则: 每个 sub-experiment 完成后, 在本文档 §5 对应 sub 下加 CONCLUSION 段落.
文档保持单一权威性, 重大决策历史见 `git log docs/plans/phase2.5_feature_landscape_v0601.md`.*
