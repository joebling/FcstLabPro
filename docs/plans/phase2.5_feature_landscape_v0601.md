# Phase 2.5 特征工程战略

> **状态**: 🟡 **方向已重定向** (2026-06-01) — 详见下方 P0 警告
> **前置阅读**:
>   - `docs/lessons/lesson_0601_pruning_alpha.md` 🚨 **第一必读** (本文档方向重定向的依据)
>   - `docs/lessons/lesson_0601_data_governance_regime_shift.md` ⚠️ 必读 (数据治理铁律由来)
>   - `docs/plans/feature_engineering_roadmap.md` (Phase 1-4 全局)
>   - `docs/ops/OPS_MANUAL.md` §2-§3 (实验规范)

---

## ⚠️ P0 警告: 本文档原始路线已被 Wave 2 实证推翻 (2026-06-01)

**原计划**: 通过 7 个 "加特征" sub-experiment (E19-PUELL/SOPR/MVRV/ADDRESS/STABLE/AVIV/DERIV-SHORT) 提升 E1 (Kappa 0.348).

**实际跑了 3 个的结果**:

| 实验 | Kappa | Δ vs E1 |
|---|---|---|
| E19-PUELL (+5 特征) | 0.326 | **-6.2%** 🔴 |
| E19-FUNDING (+16 特征) | 0.288 | **-17.1%** 🔴 |
| E18a (LTH/STH +36) | 0.324 | -6.8% 🔴 |

**根因**: E1 baseline 本身就过参数化 (129 特征里 ~100 个是噪声), 任何"加特征"都被噪声淹没。**不是新指标没信号** (puell_zscore_90 进 Top 3, fr_zscore 进 Top 10), **是 baseline 不健康**。

**剪枝路线打破僵局**:

| 实验 | n_feat | Kappa | 显著性 |
|---|---|---|---|
| **E20c (E1 剪到 28)** | 28 | **0.4290** (+27.8%) | 4-seed CV 3.21%, 强 alpha |
| **E21b (E8 剪到 81)** | 81 | **0.7717** (+1.93%) | 3.8σ 显著; research only |

**新铁律 (Wave 2 沉淀)**:
1. 任何 "加特征" 实验启动前, **先做 baseline 剪枝扫描**, 确认 baseline 不过参数化
2. 任何 Kappa 提升 ≥ 0.5% 必须做 **4-seed 显著性测试 (3σ)** 才能下结论
3. 不能跨任务套用 CV (E1 系 CV 3.21%, E8 系 CV 0.50%, 差 6 倍)

**Production 决策更新**: E20c 是当前唯一 promotion 候选。E21b 分类/Kappa 显著, 但 PnL 执行层不全线胜出 (止盈版本弱于 E8 baseline), **暂不 promote**, 保留 research/shadow 候选。

**本文档 §5 (7 个 sub-experiments) 整体暂停**, 详见 §5 头部状态标记。

---

## 0. TL;DR

> ⚠️ 以下是 **原计划** 描述, 已被 Wave 2 实证调整. 当前有效路线以上方 P0 警告 + §6.2 为准.

**Phase 2.5 原计划 = 在 2020-2025 锁定基准上, 用 BGeo 长历史指标 (≥ 12 年) 给 weekly bear 模型寻找
正交 alpha**, 通过 7 个并行 sub-experiment (E19-PUELL/SOPR-NEW/MVRV-EXT/ADDRESS/STABLE/AVIV/DERIV-SHORT)
验证. 原门槛 Kappa ≥ 0.3654 (+5% vs E1 0.348), **现门槛 Kappa ≥ 0.4505 (+5% vs E20c 0.4290)**.

**核心约束** (仍有效):
- 慢变量必须 short-horizon 转换 (raw level 禁进特征集)
- 候选指标必须通过 `audit_bgeo_nan.py` 数据卫生检 (cov ≥ 95%, stale ≤ 90d)
- 基准数据 sha256 锁定, 任何变动必先验证 E1 bit-exact
- **新增**: 任何 Kappa 变动 ≥ 0.5% 必须 4-seed 显著性检验 (§6.2 双引用)
- **新增**: 加特征前必须先扫 baseline 剪枝曲线 (§9 + lesson_0601_pruning_alpha)

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
4. **公平基准**: 全部 2020-2025; 新 sub 必须跟 **E20c baseline (Kappa 0.4290)** 对比, 不再跟原 E1 0.348 对比
5. **门槛**: Kappa ≥ E20c × 1.05 = **0.4505** 才考虑下一步; production 还必须通过 PnL/执行层 gate
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

> 🟡 **状态 (2026-06-01)**: 本节 7 个 sub-experiments **整体暂停**, 等待以下前置完成:
>
> 1. ✅ **E20c 完成** — 新 E1 系 baseline = **0.4290** (不是 0.348)
> 2. ✅ **E21b 完成** — 新 E8 系分类候选 = **0.7717** (不是 0.757), 但 **PnL 执行层不全线胜出, 暂不 promote**
> 3. ✅ 本节 §6.2 决策树已从 0.348 上调到 **0.4290** (弱 alpha 门槛 ≥ 0.4505, 强 alpha 门槛 ≥ 0.515)
> 4. ⏳ 若重启 §5.x, 需验证指标能否在 **E20c 的 28 特征 baseline** 上按新门槛赢 (难度远高于原计划)
>
> **推荐路径**: 先 promote E20c；E21b 进入 shadow/research 池；再重扫 7 个 sub 能否超 E20c → 幸存者进入 §5 探索
> **下面 §5.x 原本 保留** 用作 "后续扫描时的并行候选清单"。

### 5.1 E19-PUELL ⭐ 优先级 1

| 字段 | 值 |
|---|---|
| 假设 | Puell Multiple (Charles Edwards 经典周期 indicator) 提供 "周期顶/底" 信号 |
| 数据源 | BGeo `puell_multiple_data.json` (2012-2025, 14 年, L1: cov 99.5%, stale 2d) |
| 新增特征 | 1 × 5 = 5 (`zscore_30/90`, `slope_7/30`, `momentum_7`), **不含 raw** |
| 时间预算 | 30 min |
| 优势 | 单一指标快速验证, 经典机构信号, 长历史 |

> **CONCLUSION (2026-06-02, Wave 3 — E22 on E20c baseline)** 🔴 **关闭此方向**
>
> Wave 2 已证明 PUELL on E1(129) 失败 (0.326 < 0.348), 但归因为 "baseline 过参数化"。
> Wave 3 用健康 baseline (E20c 28 特征) 重测以隔离真因:
>
> | 对照 | n_feat | Kappa | Δ |
> |---|---|---|---|
> | E20c baseline (seed=42) | 28 | 0.4448 | — |
> | E20c 4-seed mean | 28 | 0.4290 | — |
> | **E22 = E20c + PUELL (seed=42)** | 33 | **0.4375** | **-1.6% vs seed42; +2.0% vs mean** |
>
> 未达门槛 (0.4505)。关键观察: `ext_puell_zscore_90` importance=63 **排第 5** (比 E1 下的 48 还高,
> 因为噪声变少更突出), 模型**确实在用**这个特征 — 但整体 Kappa 仍无增量。
>
> **真因判定**: 不是 "被噪声淹没", 而是 **puell 信息与现有价格动量/波动率特征高度重叠, 非正交 alpha**。
> 高 importance ≠ 高 alpha 增量 (经典陷阱: 模型把方差分给它, 但预测力没提升)。
> **教训**: Wave 3 后续 sub 不能只看 importance 排名, 必须看 Kappa 净增量 + 4-seed 显著性。

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

### 6.1 推荐执行顺序 (Wave 2 后修正版)

```
Step 0: 停止原 E19 加特征流水线
    └─ 原 E1(129 特征) 已证明过参数化, 不再作为 add-feature baseline

Step 1: promote E20c (directional, 28 特征)
    └─ 当前唯一 production promotion 候选

Step 2: E21b 进入 research/shadow 池
    └─ 分类显著, raw PnL 胜, 但止盈/执行层未适配 → 不 promote

Step 3: 若继续 Phase 2.5, 所有 add-feature sub 必须重建为:
    E20c 28 核心特征 + 单一新指标族
        ├─ Kappa ≥ 0.4505 且 4-seed 3σ 显著 → 继续 PnL gate
        ├─ PnL/执行层全线或核心版本胜出 → promote 候选
        └─ 否则 → research/shadow 或归档

Step 4: 对 E8/touch 路线的任何优化
    └─ 必须额外证明当前止盈/执行规则适配, 否则只算分类候选
```

**关键决策点**:
- **Kappa 提升不是终点** → production 必须过 PnL/执行层 gate
- **E20c 是当前唯一 production 候选** → 后续 add-feature 先跟 E20c 比
- **E21b 暂不 promote** → 等执行规则重调后再评估
- **原 PUELL/SOPR/MVRV 等 §5 sub** → 保留为候选清单, 不是立即执行队列

### 6.2 决策树 (基于 Wave 2 后新 baseline)

> ⚠️ **门槛已上调** (2026-06-01): 原门槛基于 E1=0.348, 现基于 **E20c=0.4290** (prune+27.8%).

| 单个 sub Kappa | 行动 |
|---|---|
| ≥ 0.515 | 🟢 强 alpha (+20% vs E20c), 立即 promote 候选 |
| 0.4505 ~ 0.515 | 🟢 弱 alpha 达门槛 (+5% vs E20c), 继续展开 |
| 0.4290 ~ 0.4505 | 🟡 持平, 视计算成本决定是否保留 |
| < 0.4290 | 🔴 拒绝, 不如 E20c 纯剪枝 |

**重要**: 运行新 sub-experiment 时, **baseline 应是 E20c 的 28 特征 + 新指标**, 不是 原 E1 的 129 特征 + 新指标. 后者默认过参数化, 调不出东西.

**4-seed 显著性强制**: 任何合格结论必须补上 4-seed 重跑 + 3σ 显著性检验 (参考 `lesson_0601_pruning_alpha.md` §6 铁律 A).

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

### 7.2 Wave 2 后待办

- [x] E20/E21 剪枝曲线完成, 并沉淀 `lesson_0601_pruning_alpha.md`
- [x] Phase 2.5 原加特征路线暂停, 主文档加 P0 警告
- [x] promote E20c 到 production (当前唯一候选) — `models/production/e20c-conservative-prune`, 已 live primary (`active.yaml`), commit `a0d76be`; 复现 gate seed=42 bit-exact 已补验 (metrics+predictions+model sha256), commit `dbf4554`
- [x] E21b 保留 research/shadow, 等执行规则重调后再评估 — 已落地 `models/production/e21b-touch-prune` (candidate 槽, status=offline_only, role=sota_candidate), 复现 seed=42 bit-exact, active.yaml 已注册+校验通过
- [x] 所有 v0601+ config 强制加 `expected_sha256` — 全量覆盖完成 (E1_repro/E18a_2020start 补齐, commit `aa90b37`); ⏳ CI 自动检查待加
- [ ] 若重启 §5 add-feature sub: 先基于 **E20c 28 核心特征** 创建新 config, 不再基于原 E1 129 特征
- [ ] **可选**: 扩充 audit 范围, 扫 200+ BGeo 长历史指标, 生成完整 L1 可用清单 (供后续 add-feature 候选用)

### 7.3 E19-DERIV-SHORT 专属前置 ⛔ 硬阻塞

- [ ] `src/features/builder.py` 加 `keep_nan_features: list[str]` 选项
- [ ] LightGBM 验证: 含 NaN 列训练正常, 不一致行不被 drop
- [ ] ⛔ **硬阻塞**: E1/E8 production + E20c candidate 复现测试, 任一 metric diff > 1e-12 立即回滚 builder 修改

---

## 8. 验收准则

### 8.1 每个 sub-experiment 必含

- `meta.json` 含 `data.sha256`, `data.effective_rows`, `data.effective_start/end`
- `metrics.json` 含 `kappa/f1/precision/recall/accuracy`
- `fold_metrics.csv` 至少 50+ folds (init_train=800, oos_window=63 默认)
- `pnl_metrics.json` + `pnl_report.md` 必须存在; production 候选不能只看分类指标
- `report.md` 包含跟 **E20c baseline** 的对比表 (若是 touch 路线, 同时跟 E8 production 对比)
- `feature_importance.csv` 显示新增特征排名分布
- 4-seed 复现性汇总: mean/std/CV/min/max + baseline 是否落在 3σ 之外

### 8.2 Production PnL gate

分类指标达标后, 必须继续通过执行层验证。最低要求:

| Gate | 要求 |
|---|---|
| raw signal | CAGR/Sharpe/MaxDD 不劣于 baseline |
| 默认执行 | 跟对应 baseline 版本比较 |
| 风险指标 | MaxDD 不恶化; Calmar/PF 改善 |
| 稳定性 | 4-seed 分类显著; 主 seed PnL 胜 |

**E21b 反例**: Kappa +1.93% 且 raw PnL 胜, 但 `+止盈` 与 `止盈+regime` 输给 E8 baseline, 所以暂不 promote。

### 8.3 反 over-fitting 纪律

**禁止**:
- ❌ sub 失败后反复调超参数让它 "看起来更好"
- ❌ 减少 `init_train` 让 fold 数变化重测
- ❌ 改 `oos_window` 让 metrics 涨

**允许**:
- ✅ 失败 sub 单独写一段 CONCLUSION 段落 (本文 §5 对应 sub 下), 然后**关闭**该方向
- ✅ 分类成功但 PnL 未过 gate 的 sub 进入 research/shadow 池 (E21b 模式)
- ✅ 分类 + PnL 都过 gate 的 sub 才能进入 promotion SOP

---

## 9. 已知失败方向 (避免重复试)

- **LTH/STH 6 核心指标** (E18a, 165 features, Kappa 0.3244 vs E1 0.3480, -6.8%): 周期级慢变量 (>180d) 与 weekly bear (T=21) 尺度严重错配. **教训沉淀为 §4 设计原则 #6**. 详见 `docs/plans/archive/` + `onchain_lth_sth_feature_plan.md` §7.
- **E19-PUELL** (134 features, Kappa 0.326 vs E1 0.348, -6.2%): 加 5 个 short-horizon Puell 派生. 单点信号很强 (puell_zscore_90 rank 3, importance 48), 但整体 kappa 仍下降. 详见 commit `7399f91` + `lesson_0601_pruning_alpha.md` §2.1.
- **E22 = E20c + PUELL** (33 features, Kappa 0.4375 vs E20c seed42 0.4448 / 4-seed mean 0.4290): Wave 3 用健康 baseline 重测 PUELL, **未达门槛 0.4505**. `ext_puell_zscore_90` importance 升到 rank 5 (63), 模型确实在用, 但整体无增量 → **puell 与价格动量/波动率高度共线, 非正交 alpha**. 结论: PUELL 方向彻底关闭 (E1-based 和 E20c-based 双重证伪). 详见 §5.1 CONCLUSION.
- **E19-FUNDING** (145 features, Kappa 0.288 vs E1 0.348, -17.1%): 加 16 个 Funding Rate 特征 (复用现有 `external_fr`). 16 个里 5 个 importance=0 废特征, 共线严重. 详见 commit `c88d918`.
- **“加特征”路线本身** (PUELL/FUNDING/E18a 3 连败): **不是新指标没信号, 是 baseline 过参数化**. 必须先走 prune 路线 (E20c +27.8%) 再判断。
- **Miner 系列** (miner_balance / out_flows / reserves / sell_presure): BGeo 矿工数据全部停更 200+ 天, 不可用. 未来如有 CryptoQuant 等公开源可重启.

---

*维护原则: 每个 sub-experiment 完成后, 在本文档 §5 对应 sub 下加 CONCLUSION 段落.
文档保持单一权威性, 重大决策历史见 `git log docs/plans/phase2.5_feature_landscape_v0601.md`.*
