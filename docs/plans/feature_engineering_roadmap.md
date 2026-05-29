# 特征工程改进 Plan

> **生成时间**: 2026-05-22
> **作者**: sam
> **前置阅读**: [`cr_0522_feature_engineering.md`](../reviews/cr_0522_feature_engineering.md) — 当前模型 7 大问题诊断
> **参考字典**: [`feature_dictionary.csv`](../specs/feature_dictionary.csv) — 129 特征完整清单

---

## 0. 路线图总览

```
本周    : Phase 1 (P0 清污)           — ~1 天，需重训+bootstrap+复现验证
本月    : Phase 2 (启用真数据 + MVRV)  — 2-3 天，含训练验证
本季度  : Phase 3 (剪枝去重)           — 0.5 天，需训练
持续    : Phase 4 (长期演进)           — 按需推进
```

> ✅ **Phase 1 状态 (2026-05-29): 已实施并验证**。重命名完成, 新实验
> `v0529_E1_rename` / `v0529_E8_rename` 与 production 基线 **bit-exact**
> (predictions 逐行一致 + PnL diff=0)。详见
> `experiments/weekly/v0529_E1_rename/PHASE1_RENAME_REVIEW.md`。
> ⚠️ 实测推翻了原文 "0 PnL 风险/不需重训" 的说法 — 见下表与 §1。

| Phase | 目标 | 影响 | 工作量 | 状态 |
|---|---|---|---|---|
| **🔴 P0 清污** | 消除 fake 特征命名误导 | 不改算法, 但**需重训** | ~1 天 | ✅ 完成 |
| **🟠 P1 启用真数据 + MVRV** | 引入真正独立信息维度 | 预期 Kappa ↑ | 2-3 天 | 未开始 |
| **🟡 P2 剪枝去重** | 减少噪声特征 + DRY | 速度 +30%，可解释性 ↑ | 0.5 天 | 未开始 |
| **🟢 P3 长期演进** | 季节性 / 真衔生品 / 跨资产 | 按月迭代 | 持续 | 未开始 |

> 💡 **核心建议**: 不要急着上 MVRV — **先做 Phase 1 清污**，避免 fake 数据继续误导决策；再做 Phase 2 启用已下载的真实数据（funding_rate / 宏观），跟 MVRV 一起作为新外部数据维度引入，对照实验隔离每一项的净贡献。

---

## 1. Phase 1 — 🔴 P0 清污 ✅ 已完成 (2026-05-29, 实耗 ~1 天)

**状态**: 已实施。实验 `v0529_E1_rename` / `v0529_E8_rename`, 与 production 基线 bit-exact。
详见 `experiments/weekly/v0529_E1_rename/PHASE1_RENAME_REVIEW.md`。

> ⚠️ **原定义勘误 (已修正)**: 原文称本 Phase "纯重命名、0 PnL 风险、不需重训"。
> 实测推翻: 重命名 = 改共享 feature builder, 会触发 `validate_feature_cols`
> 守卫使 production live 推理 **当场 halt** (新名 vs joblib 旧名不匹配)。
> 正确做法: **重训 + bootstrap feature_cols + 复现验证**, 非"零风险纯文字改动"。

**实际执行记录** (遵循 `docs/ops/experiment_sop.md` Stage 0-7):

| 任务 | 状态 | 说明 |
|---|---|---|
| Stage 0 复现守门 | ✅ | 改动前 E1/E8 bit-exact 绿 |
| 重命名 market_structure.py | ✅ | 见下表映射 |
| 新建 config v0529_E1/E8_rename | ✅ | 含 hypothesis 字段 |
| 重训 E1/E8 | ✅ | metrics bit-exact |
| 复现验证 + predictions 逐行 | ✅ | 3339 行全同, PnL diff=0 |
| 识别 live halt 副作用 | ✅ | 守卫正确拦截 |

**重命名映射** (已落地 `src/features/market_structure.py`):

| 旧名 (误导) | 新名 (诚实) |
|---|---|
| `funding_rate_{7,14,24}` | `price_mom_smooth_{7,14,24}` |
| `open_interest_{7,14,24}` | `volume_cumsum_{7,14,24}` |
| `stablecoin_inflow_proxy` | `down_volume_proxy` |

**收口决策 (✅ 已完成 2026-05-29)**: 已走 promotion SOP 用本实验刷新 production。
e1-conservative (hash=98c85910) + e8-touch (hash=0c965223) 均已覆盖,
feature_cols 现为新名 (price_mom_smooth_*), live 推理 halt 已解除
(复现守门 bit-exact, 28 tests pass)。commit 7696769 / d07fe3d。

### 原计划任务清单 (保留供追溯)

| # | 任务 | 状态 |
|---|---|---|
| P0-1 | 重命名 market_structure.py 伪外部特征 | ✅ 完成 |
| P0-2 | onchain.py + sentiment.py 加 DeprecationWarning | ⏳ 未做 (另算, 不在本次范围) |
| P0-3 | data_pipeline.md 加说明 | ✅ 已有 (§2.4 名称地雷; 例子用旧名, 可顺手更新) |
| P0-4 | bootstrap feature_cols (随重训自动生成) | ✅ 新实验已生成 + production 已刷新 |

---

## 2. Phase 2 — 🟠 P1 启用真数据 (估时 2-3 天，需重训对比)

**目标**: 补上 [cr_0522_feature_engineering.md §3](../reviews/cr_0522_feature_engineering.md) 揭示的"真实信息维度缺失"。

### 2.1 任务分解

| # | 任务 | 验证方式 |
|---|---|---|
| P1-1 | 新建实验 **E17**: `features.sets += [external_fr, external_macro]`，对比 E1 / E8 PnL | walk-forward + 显著性检验 |
| P1-2 | 集成 CoinMetrics MVRV 数据，新建 `src/data/coinmetrics_loader.py` + `download_external_data.py --sources mvrv` | 数据完整性 + 缓存机制 |
| P1-3 | 在 `external.py` 新增 `external_mvrv` 子集 (12 个特征，详见 §2.3) | 单元测试 + 历史回填脚本 |
| P1-4 | 新建实验 **E18**: 在 E17 基础上 `+ external_mvrv`，对比 PnL | 对照 E17 隔离 MVRV 净贡献 |

### 2.2 MVRV 引入设计

#### 为什么 MVRV 值得加 (与 §1.P0-1 揭示的 #1 fake 特征对比)

| 维度 | `funding_rate_14` (当前 #1，fake) | **MVRV (候选)** |
|---|---|---|
| 数据本源 | 价格自身派生 | 链上 UTXO + 价格 |
| 与价格相关性 | 极高 (本质就是动量) | 中低 (RV 是慢变量) |
| 周期识别能力 | 弱 (只看 14 天) | 极强 (覆盖整个减半周期) |
| 阈值可解释性 | 模糊 | 清晰 (≥3 = 顶部，≤1 = 底部) |
| 外部冲击鲁棒性 | 价格变它就变 | RV 是累计量，更稳 |

历史顶部 MVRV 峰值：2013-11 (5.5) / 2017-12 (4.7) / 2021-04 (3.9) / 2021-11 (3.0)。
对 **E1 (空头风控)** 模型尤其有价值 — 这正是它训练目标想捕捉的信号。

#### 数据源对比

| 源 | 价格 | KYC | 历史回看 | 频率 | 备注 |
|---|---|---|---|---|---|
| **CoinMetrics Community API** | 免费 | 否 | 2010 至今 | 日 | ✅ 推荐起点 |
| Glassnode Free Tier | 免费但限速 | 注册 | 部分指标限 1Y | 日 | API 严格限流 |
| LookIntoBitcoin | 免费可视化 | 否 | 全历史 | 日 | 无官方 API，需 scraping (出 walmart policy) |
| Bitcoin Magazine Pro | 付费 | 需 | 全历史 | 日 | 数据全但贵 |

**推荐**: CoinMetrics `Network Data Pro` 的 `CapMrktCurUSD` (MV) + `CapRealUSD` (RV) 两个字段即可计算 MVRV。

### 2.3 候选 MVRV 特征族 (12 个)

```
ext_mvrv                       — MV / RV (核心)
ext_mvrv_ma_30                 — 30 日均值 (平滑短期噪声)
ext_mvrv_ma_90                 — 90 日均值 (周期视角)
ext_mvrv_change_7              — 周环比变化
ext_mvrv_change_30             — 月环比变化
ext_mvrv_zscore_365            — 1 年滚动 Z-score (即 MVRV-Z Score)
ext_mvrv_pct_rank_730          — 在 2 年历史分布中的百分位
ext_mvrv_extreme_top           — (MVRV ≥ 3).astype(int)         ← Messari 阈值
ext_mvrv_extreme_bottom        — (MVRV ≤ 1).astype(int)         ← 资金成本线
ext_mvrv_in_top_zone           — (MVRV ≥ 2.5).astype(int)       ← 警戒区
ext_mvrv_in_bottom_zone        — (MVRV ≤ 1.2).astype(int)       ← 机会区
ext_mvrv_slope_30              — 30 日线性斜率 (趋势加速度)
```

### 2.4 风险评估

| 风险 | 缓解措施 |
|---|---|
| **链上数据可能有 1-2 天延迟** | live_signal 用前一日值（已经是 daily 模型不算问题） |
| **CoinMetrics API 限流** | 每日 1 次拉取 + 本地缓存到 `data/external/mvrv.csv` |
| **未来 API 变更** | 抽象成 `src/data/onchain_loader.py`，单点改动 |
| **历史回填 vs 实时一致性** | 一次性回填 + 日常增量，写 SHA256 校验防数据被静默替换 |
| **过拟合 Messari 阈值 (3.0)** | 阈值特征只作为辅助；用连续 z-score 作主信号 |

---

## 3. Phase 3 — 🟡 P2 剪枝与去重 (估时 0.5 天，需重训)

**目标**: 解决 [cr_0522_feature_engineering.md §2.P2-5/P2-6/P2-7](../reviews/cr_0522_feature_engineering.md) 揭示的稀疏 / 共线 / DRY 三大问题。

| # | 任务 | 数量 |
|---|---|---|
| P2-1 | drop `qvol_ratio_10` + 2 个 `ext_fgi_extreme_*` (零重要性) | 3 个 |
| P2-2 | drop `sma_5/10/100/200` + `ema_5/10/100/200` (保留 `sma_20/50` + `ema_20/50`) | 8 个 |
| P2-3 | 合并 DRY 违规: 删除 `flow.py` 里所有被 `market_structure.py` 覆盖/重复的定义 | ~10 个 |
| P2-4 | drop 所有两模型 importance ≤ 5 且非领域必需的特征 | ~20 个 |
| P2-5 | `config.yaml` 删除 `scaling: standard` (LightGBM 不需要 scaling) | 1 行 |

**预期效益**:
- 特征数 129 → ~85，训练速度 +30%，可解释性显著提升
- 多重共线性下降，特征重要性更稳定 (跨 fold 方差减小)

**风险与缓解**:
- 剪枝可能误删某些"看起来低 importance 但实际是后备特征"的列
- 缓解: 走对照实验 — 先建 E19 (full features) vs E20 (pruned), 比较 walk-forward Kappa 分布的 paired t-test, p > 0.05 才合并 main

---

## 4. Phase 4 — 🟢 P3 长期演进 (估时持续)

**目标**: 持续填补 [cr_0522_feature_engineering.md §3](../reviews/cr_0522_feature_engineering.md) 缺失维度表。

| # | 任务 | 触发条件 |
|---|---|---|
| P3-1 | 接入真实衍生品 OI (Binance OI API，`sync_binance_oi_ls.py` 已有原型，需启用) | Phase 2 完成后 |
| P3-2 | 加入日历特征: `day_of_week` / `month` / `days_since_halving` | 任何时候 (实施成本极低) |
| P3-3 | 加入跨资产: `ext_btc_dominance` / `ext_eth_btc_ratio` (`download_external_data.py --tier2` 已下载) | Phase 2 完成后 |
| P3-4 | 考虑链上估值衍生族: 真实 SOPR / Realized Cap HODL Waves / Coin Days Destroyed | Phase 2 MVRV 数据通道建好后顺势添加 |
| P3-5 | 重做 `regime.py` (当前 200MA 太粗糙，加入 MVRV-Z + Funding regime + 波动 regime 联合分类) | Phase 2 MVRV 上线后 |

---

## 5. 验证 SOP (任何 Phase 实施后必须执行)

```bash
# Step 1: 重训
python scripts/run_experiment.py --config configs/experiments/weekly/exp_XXX.yaml

# Step 2: 横向对比（救活 compare_experiments.py 后）
python scripts/compare_experiments.py \
  --ids weekly_bear_v0305_E1_decontam weekly_bear_v0305_E17_with_external

# Step 3: PnL 回测
python scripts/pnl_backtest_v0305.py --exp-dir experiments/weekly/E17_xxx

# Step 4: 显著性检验（fold-level paired t-test on Kappa）
# 没现成脚本，需要新增 — Plan 里 P3 候选

# Step 5: 通过后 promote
python scripts/promote_model.py --experiment XXX --target-name XXX
```

**通过标准**:
- Kappa 不低于 baseline 0.95 倍 (避免误伤)
- PnL 综合 Sharpe ≥ baseline
- Walk-forward fold 数 ≥ 8，paired t-test p < 0.1 才认为显著提升

---

## 6. 不做的事 (YAGNI)

明确**不**纳入 plan 的方向（避免 scope creep）：

| 方向 | 不做的原因 |
|---|---|
| 深度学习 (Transformer/LSTM) | 现有特征量级不够、可解释性损失大 |
| 实时 (intra-day) 信号 | 当前是 daily 模型，业务定位匹配 |
| 多币种 (ETH/SOL) | 先把 BTC 做扎实 |
| 链上 mempool 级特征 (e.g. unconfirmed txs) | 信噪比太低 |
| 社交媒体情绪 (Twitter/Reddit) | 数据成本 + 可复现性问题 |

---

## 7. 决策检查清单

实施任何 Phase 之前，确认：

- [ ] 已完整阅读 [`cr_0522_feature_engineering.md`](../reviews/cr_0522_feature_engineering.md)
- [ ] 当前生产模型 `feature_cols.json` 已存在 (P0 守卫已生效)
- [ ] `compare_experiments.py` 已修复 (能横向对比实验)
- [ ] 数据源 API key/配额已就绪 (Phase 2 需要 CoinMetrics 访问)
- [ ] 已 git commit 当前 main，方便回滚
- [ ] 已通知下游消费者 (邮件订阅人 / 信号 API) 若有 schema 变更
