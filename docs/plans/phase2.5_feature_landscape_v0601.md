# Phase 2.5 特征工程战略 (v0601)

> **生成时间**: 2026-06-01
> **作者**: sam
> **状态**: 🟢 活动主文档 (取代 `archive/experiment_matrix_v0601_ARCHIVED.md` + `archive/bgeometrics_tier_s_expansion_v0608_ARCHIVED.md`)
> **前置阅读**:
>   - `docs/lessons/lesson_0601_data_governance_regime_shift.md` ⚠️ **必读**
>   - `docs/plans/feature_engineering_roadmap.md` (Phase 1-4 全局)
>   - `docs/plans/onchain_lth_sth_feature_plan.md` §7 (E18a 终结记录)
>   - `docs/ops/OPS_MANUAL.md` §2-§3 (实验规范)

---

## 0. TL;DR + 重大修正声明

### 0.1 本文档为什么存在

**取代两份归档文档**, 原因:

1. `experiment_matrix_v0601.md` 把 "CMD Tier 1 12 个" 当成全候选空间, 但 **CMD 29 个指标全部 2022-12-03 起** (3.5 年), 无法在 2020-2025 基准下公平使用。
2. `bgeometrics_tier_s_expansion_v0608.md` 把 BGeo 定位为 "Phase 2.6 后续扩展", 但事实是 **BGeo 437 个 JSON 才是 Phase 2.5 主战场**, 其中 **239 个 2012+ 长历史** (≥14 年)。

### 0.2 核心数据治理结论 (本文档铁律)

| 规则 | 值 | 依据 |
|---|---|---|
| 基准 `data.start` | `'2020-01-01'` 锁定 | lesson_0601 §3 (regime shift) |
| 基准 `data.end` | `'2025-12-31'` 锁定 | lesson_0601 §3 (避免泄漏未来) |
| BTC csv sha256 | 必填 `expected_sha256` | runner.py §B 校验 (lesson_0601 §4.2 P0) |
| BTC csv expected_rows | 必填 `expected_effective_rows: 2192` | 同上 |

### 0.3 Wave 2 战略修正

| 旧战略 (废弃) | 新战略 |
|---|---|
| E19c: CMD Tier 1 12 个一锅炖 | E19 拆 5 个 sub-experiment, 按 BGeo+CMD 联合空间设计 |
| Wave 2 = CMD 主体, BGeo 为补充 | Wave 2 = BGeo 主体 (239 个 2012+), CMD 为 NaN-aware 补充 |
| Phase 2.6 = Tier S 扩展 | Phase 2.6 不再需要, 已并入 Phase 2.5 主体 |

---

## 1. 数据源真实画像 (CMD vs BGeo)

### 1.1 数据源对比

| 维度 | crypto-market-data (CMD) | bgeometrics (BGeo) |
|---|---|---|
| **位置** | `/home/jupyter/qiu/github/crypto-market-data/data/daily/` | `/home/jupyter/qiu/github/bgeometrics.github.io/files/` |
| **总指标数** | 29 JSON | **437 JSON** (419 可解析) |
| **历史长度** | 全部 2022-12-03 起 (3.5 年) | 2010-07 ~ 2026, 不等 |
| **更新方式** | 每日 GitHub Actions 拉取 | CloudFlare CDN 实时刷新 |
| **schema** | 统一 dict (含 metadata + data list) | list-of-pairs (不统一) |
| **衍生品类** | 🟢 齐全 (funding/OI/taker/long_liq/short_liq) | 🟡 部分 (funding 2023+, OI 2020+, **无 liq**) |
| **链上长历史** | 🔴 无 (全 2022+) | 🟢 极强 (2个 2012+) |
| **定位** | 实时快照库 | 历史归档库 |

### 1.2 BGeo 历史长度分布 (419 个可解析 JSON)

| 起始年 | 数量 | 占比 | 代表指标 |
|---|---|---|---|
| **≤ 2012** | **239** | **57%** | address_*, cdd, coin_*, aviv, mvrv, sopr, miner_balance, puell_multiple_data |
| 2013-2014 | 78 | 19% | lth_nupl, miner_out_flows, miner_reserves, investor_cap, glm |
| 2015-2017 | 21 | 5% | stablecoin_usdt, stecoin_dai (2017-11), ... |
| 2018-2020 | 23 | 5% | open_interest_futures (2020-08+), ... |
| 2021-2022 | 26 | 6% | inflow_exchanges_btc (2021-06+), ... |
| 2023+ | 32 | 8% | funding_rate (2023-07+), funding_rate_7sma |

> **核心洞察**: BGeo 76% 的指标 ≥ 2014 起 (≥12 年), 远超 CMD 全员 3.5 年.

### 1.3 CMD 真实定位 (修正后)

CMD 不是 "首选数据源", 而是 "**衍生品 + 短历史链上的备份源**":

- ✅ **liquidations (long/short)** — CMD 唯一公开源 (BGeo 无, Binance API 无历史)
- ✅ **coinbase_premium_index** — 比自己算 Coinbase-Binance 价差省事
- ✅ **taker_buy_sell_ratio** — 比 Binance API 拉取省事
- 🟡 **funding_rates / open_interest** — BGeo 也有, 但 CMD 数据稍长 (2022-12 vs 2023-07)
- ❌ **exchange_netflow, miner_netflow** 等 CryptoQuant signature — 数据短, 信号未必比 BGeo 长历史替代品强

---

## 2. 466 联合特征空间 (按类别 × 历史长度)

### 2.1 矩阵概览 (代表性指标, 不完全枚举)

| 类别 | 长历史源 (≥ 2017, 推荐) | 短历史源 (2022+, NaN-aware) |
|---|---|---|
| **周期 Valuation** | `puell_multiple_data` (2012), `mvrv_data` (2012), `mvrv_zscore_*`, `aviv` (2010), `lth_nupl` (2013) | CMD `btc_mvrv_ratio` |
| **Miner (供给端)** | `miner_balance` (2012), `miner_out_flows` (2013), `miner_reserves` (2013), `miner_sell_presure` (2013), `puell_multiple_data` (2012) | CMD `miner_netflow_total`, `miners_position_index` |
| **SOPR 家族** | `sopr_data`, `sopr_adjusted`, `cdd`, `cdd_terminal_ajusted` (全 2012+) | — |
| **Address (HODL Waves)** | `address_*` 12 档 (2012+), `addresses_active` (2010) | — |
| **Stablecoin** | `stablecoin_usdt`, `stablecoin_dai`, `stablecoin_supply` (2017+) | CMD `stablecoin_exchange_netflow` (2022+) |
| **Funding Rate** | BGeo `funding_rate.json` (2023-07+) ❌ 短 | CMD `btc_funding_rates` (2022-12+), 或 Binance API DIY (2019+) |
| **Open Interest** | BGeo `open_interest_futures_btc_price.json` (**2020-08+** ⚠️ 接近基准) | CMD `btc_open_interest` (2022-12+) |
| **Taker Buy/Sell** | — | CMD `btc_taker_buy_sell_ratio` (2022+) |
| **Liquidations** | — | CMD `btc_long_liquidations`, `btc_short_liquidations` (2022+) ⚠️ **唯一源** |
| **Coinbase Premium** | — | CMD `btc_coinbase_premium_index` (2022+), 或 DIY (Coinbase + Binance 价差, 2019+) |
| **Exchange Flow** | BGeo `inflow_exchanges_btc` (2021-06+, **已停 2024-06**) ❌ 不可靠 | CMD `btc_exchange_netflow`, `whale_ratio` (2022+) |

### 2.2 数据可得性等级

| 等级 | 定义 | 实验策略 |
|---|---|---|
| **L0: 完整 2020-2025** | 在基准内 0 NaN | 直接加入特征集, ffill_then_drop 不丢行 |
| **L1: 部分覆盖 ≥ 70%** | 起始 2020-2022 | 加入但需 NaN-aware (改 builder) 或截断 |
| **L2: 短覆盖 < 70%** | 起始 2022+ | 仅 NaN-aware, 或换基准 (放弃 5 年 baseline) |
| **L3: 不可靠** | 已停更新或数据漂移 | 不用 |

**统计**:
- L0 BGeo 长历史: ~200+ 个 (主要工作面)
- L1 BGeo 部分覆盖: ~30 个 (open_interest_futures, stablecoin_*)
- L2 CMD 全部 + BGeo funding_rate: ~30 个 (需 NaN-aware)
- L3 不可用: ~15 个 (inflow_exchanges_btc 等已停)

---

## 3. 已完成实验回顾

### 3.1 E18a: LTH/STH 6 核心指标 (失败)

| 实验 | features | kappa | f1 | 判定 |
|---|---|---|---|---|
| E1 baseline (复现) | 129 | **0.3480** | 0.4161 | ✅ bit-exact |
| E18a (+ 36 LTH/STH) | 165 | 0.3244 | 0.3929 | ❌ -6.8% |

**详见**: `onchain_lth_sth_feature_plan.md` §7

**核心教训**:
1. LTH/STH 是周期级慢变量 (>180 天), 与 weekly bear (T=21) 任务尺度严重错配
2. ma_30 / slope_30 衰生后更慢, 在持续 bear 期产生大量假信号
3. **特征 importance 不为零 ≠ alpha**, 重要性 top-10 也可能拖低 precision

### 3.2 副产物: 数据治理事故 (lesson_0601)

- E1 production Kappa 0.348 → 0.241 (-30%), 原因: BTC csv 被默默扩展 2018-2019 数据
- Regime Shift Negative Transfer: 加入 2018-2019 让末 53 折 OOS kappa 降 19%
- **修复**: §0.2 基准锁定 + runner sha256 校验 (P0 已完成, commit `d1ef490`)

---

## 4. Wave 2 重新设计 (E19 拆 5 个 sub-experiments)

### 4.1 设计原则

1. **小步快跑**: 每个 sub-experiment ≤ 1h, 失败立即停止
2. **L0 优先**: 先用长历史 BGeo, 数据治理风险最低
3. **正交假设**: 5 个 sub 各覆盖不同 alpha 来源
4. **公平基准**: 全部 2020-2025, 都跟 E1 (Kappa 0.348) 对比
5. **门槛**: Kappa ≥ E1 × 1.05 = 0.3654 才考虑下一步

### 4.2 5 个 Sub-Experiments

#### E19-PUELL ⭐ 优先

| 字段 | 值 |
|---|---|
| 假设 | Puell Multiple (Charles Edwards 经典周期 indicator) 能给 bear 模型提供"周期顶/底"信号 |
| 数据源 | BGeo `puell_multiple_data.json` (2012-2025, 14 年) |
| 数据等级 | L0 |
| 新增特征 | 1 raw + 5 衍生 (ma_7/30, slope_7/30, zscore_90) = 6 |
| 时间预算 | 30 min |
| 优势 | 单一指标快速验证, 经典机构信号, 长历史 |

#### E19-MINER

| 字段 | 值 |
|---|---|
| 假设 | 矿工抛压/累积是 Bear 风险供给端核心信号 |
| 数据源 | BGeo `miner_balance`, `miner_out_flows`, `miner_reserves`, `miner_sell_presure` (全 2013+) |
| 数据等级 | L0 |
| 新增特征 | 4 raw + 4×5 衍生 = 24 |
| 时间预算 | 45 min |
| 风险 | 矿工已被多次套利, alpha 可能衰减 |

#### E19-MVRV-EXT

| 字段 | 值 |
|---|---|
| 假设 | MVRV Z-Score 多种 representation 在不同周期阶段强弱不同 |
| 数据源 | BGeo `mvrv_data`, `mvrv_365dma`, `mvrv_diff`, `mvrv_zscore_*` (全 2012+) |
| 数据等级 | L0 |
| 新增特征 | 5 raw + 5×5 衍生 = 30 |
| 时间预算 | 45 min |
| 关联 | E18a 用过 LTH/STH 但没用过 mvrv_data/zscore 这些总体 MVRV variants |

#### E19-STABLE

| 字段 | 值 |
|---|---|
| 假设 | 稳定币供给变化代表"待入场购买力" (Lyn Alden 论点) |
| 数据源 | BGeo `stablecoin_supply`, `stablecoin_usdt`, `stablecoin_dai`, `stablecoin_pax`, `stablecoin_others` (2017+) |
| 数据等级 | L1 (2017 起, 2020 基准 100% 覆盖, 但训练初期 stablecoin 总量低) |
| 新增特征 | 5 raw + 5×5 衍生 = 30 |
| 时间预算 | 45 min |

#### E19-DERIV-SHORT (需 NaN-aware 改造前置)

| 字段 | 值 |
|---|---|
| 假设 | 衍生品高频信号 (funding/OI/taker/liq) 提供短期风险溢价 |
| 数据源 | CMD `btc_funding_rates`, `btc_open_interest`, `btc_taker_buy_sell_ratio`, `btc_long_liquidations`, `btc_short_liquidations`, `btc_coinbase_premium_index` (全 2022-12+) |
| 数据等级 | L2 |
| 前置 | 改 `src/features/builder.py` 加 `keep_nan_features` 选项 (LightGBM 原生支持 NaN) |
| 新增特征 | 6 raw + 6×5 衍生 = 36 |
| 时间预算 | 1.5h (含改 builder + 测试 bit-exact + 跑) |
| 风险 | 2020-2022 全 NaN, 模型可能学到 "NaN 通道" 而非真信号 |

### 4.3 推荐执行顺序

```
E19-PUELL (30 min)
    ├─ Kappa ≥ 0.365: 大成功 → E19-MINER (验证矿工)
    └─ Kappa < 0.348: 失败 → 跳过 MINER/MVRV-EXT, 直接 E19-STABLE (换方向)
                                        ↓
                                  仍失败 → E19-DERIV-SHORT (短历史)
                                        ↓
                                  全部失败 → 转 Phase 3 剪枝
```

### 4.4 决策树 (基于 E1 baseline kappa = 0.3480)

| 单个 sub Kappa | 行动 |
|---|---|
| ≥ 0.40 | 🟢 强 alpha, 立即 promote 候选, 进入 ensemble + interaction 探索 |
| 0.365 ~ 0.40 | 🟢 弱 alpha 达门槛, 继续展开 (加 interactions) |
| 0.348 ~ 0.365 | 🟡 持平, 视计算成本决定是否保留 |
| < 0.348 | 🔴 拒绝, 此方向噪声 > 信号, 终止 |

---

## 5. 工程准备 (Wave 2 启动前必做)

### 5.1 已完成 ✅

- [x] `docs/lessons/lesson_0601_data_governance_regime_shift.md` 归档
- [x] `src/data/loader.py` 加 sha256 + effective_rows 校验
- [x] `src/experiment/runner.py` 透传 expected_sha256
- [x] `configs/experiments/weekly/exp_v0601_E18a_bgeo_core.yaml` 锁 2020-01-01
- [x] `scripts/download_onchain_bgeo.py` 11 指标拉取脚本
- [x] `src/features/external.py` `_load_onchain_csv` / `_load_onchain_series` helper

### 5.2 Wave 2 启动前待办

- [ ] 写 `scripts/download_bgeo_long_history.py` (扩展支持 puell/mvrv/miner/stablecoin 系列)
- [ ] BTC csv freeze: `sha256: 004bf0706559e0a79a4361c9a0db27d5acb07d72556499df0e081879017c7858`
- [ ] 所有 v0601+ config 强制加 `expected_sha256` (CI 检查)

### 5.3 E19-DERIV-SHORT 专属前置 (NaN-aware)

- [ ] `src/features/builder.py` 加 `keep_nan_features: list[str]` 选项
- [ ] LightGBM 验证: 含 NaN 列训练正常, 不一致行不被 drop
- [ ] E1 bit-exact 复现测试 (确认无 side effect)

---

## 6. 验收准则

### 6.1 每个 sub-experiment 必含

- `meta.json` 含 `data.sha256`, `data.effective_rows`, `data.effective_start/end`
- `metrics.json` 含 kappa/f1/precision/recall/accuracy
- `fold_metrics.csv` 至少 50+ folds (init_train=800, oos_window=63 默认)
- `report.md` 包含跟 E1 baseline 的对比表
- `feature_importance.csv` 显示新增特征排名分布

### 6.2 决策准则

不允许在 sub-experiment 失败后:
- ❌ 反复调超参数让它"看起来更好" (Over-fitting the process)
- ❌ 减少 init_train 让 fold 数变化重测
- ❌ 改 oos_window 让 metrics 涨

允许:
- ✅ 失败 sub 单独写一段 CONCLUSION.md, 然后**关闭** 该方向
- ✅ 成功 sub 进入下一阶段 (加 interactions, ensemble 等)

---

## 7. 维护记录

* **2026-06-01 v1.0**: 初始创建. 取代 `experiment_matrix_v0601.md` + `bgeometrics_tier_s_expansion_v0608.md` 两份归档文档.
  - 修正 CMD-only Tier 1 12 个分类错误
  - 引入 CMD vs BGeo 真实画像 + 466 联合特征空间
  - 重新设计 E19 为 5 个 sub-experiments
  - 写入数据治理铁律 (lesson_0601 整合)

---

*维护原则: 每个 sub-experiment 完成后, 在本文档 §4 对应 sub 下加 CONCLUSION 段落, 不写新 plan 文档. 文档保持单一权威性.*
