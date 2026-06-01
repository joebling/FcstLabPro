# Phase 2.5 实验矩阵 (v0601)

> **生成时间**: 2026-06-01
> **作者**: sam
> **前置阅读**:
>   - [`onchain_lth_sth_feature_plan.md`](./onchain_lth_sth_feature_plan.md) — 特征工程总计划
>   - [`feature_engineering_roadmap.md`](./feature_engineering_roadmap.md) — Phase 1-4 全局
> **关联文档**:
>   - `docs/ops/OPS_MANUAL.md` §2-§3 — 实验规范
> **状态**: 待审核 → 待执行

---

## 0. TL;DR

**问题**: 一次性加 6 个 LTH/STH + 12 个 crypto-market-data 指标 → 不知道谁贡献了 alpha → 重蹈 E17 反面教材覆辙。

**方案**: 拆成 **9 个对照实验，4 个 Wave 顺序执行**，每个 Wave 有明确决策点。

**预算**: ~10 小时，分 3-4 天，可中途终止。

---

## 1. 设计原则

1. **每实验只改一个变量** — 严格隔离 alpha 来源
2. **每实验都对照 E1 baseline** — 统一 reference point
3. **每实验有 GO/NO-GO 决策点** — 失败立刻止损，不连环投入
4. **Wave 按"信息量优先"排序** — 先做最值得知道答案的
5. **失败的实验进"反面教材库"** — 跟 E17 一起，下次别再做

---

## 2. 数据源 / 特征族总览

| 代号 | 来源 | 指标数 | 衍生 + 交互 | 总特征 | 来源文件 |
|---|---|---|---|---|---|
| **BGEO-CORE** | BGeometrics CDN | 6 (lth/sth × mvrv/nupl/sopr) | 6 × 6 = 36 | 36 | `charts.bgeometrics.com/files/*.json` |
| **BGEO-INT** | BGeometrics 衍生 | — | 8 交互特征 | 8 | 同上派生 |
| **CMD-ONCHAIN** | crypto-market-data | 6 (whale/netflow/miner/coinbase/puell/sc_netflow) | ~5 × 6 = 30 | ~30 | `crypto-market-data/data/daily/*.json` |
| **CMD-DERIV** | crypto-market-data | 4 (funding/OI/taker/liquidations) | ~5 × 4 = 20 | ~20 | 同上 |
| **CMD-T2** | crypto-market-data | 6 (Tier 2 候选) | ~3 × 6 = 18 | ~18 | 同上 |
| **BGEO-EXTRA** | BGeometrics 候选 | 2 (aviv, reserve_risk) | ~5 × 2 = 10 | 10 | BGEO CDN |

---

## 3. 实验矩阵 (9 个)

### 3.1 总览表

| ID | 名称 | 新增特征族 | Δ 特征 | 对照 | 主要回答 | 预算 |
|---|---|---|---|---|---|---|
| **E1** | (baseline, 已存在) | — | 0 | — | — | — |
| **E18a** | `v0601_E18a_bgeo_core` | BGEO-CORE | +36 | E1 | LTH/STH 基础价值? | 30 min |
| **E18b** | `v0601_E18b_bgeo_full` | BGEO-CORE + INT | +44 | E18a | 行为分化交互价值? | 30 min |
| **E19a** | `v0601_E19a_cmd_onchain` | CMD-ONCHAIN | +30 | E1 | crypto-market-data 链上贡献? | 30 min |
| **E19b** | `v0601_E19b_cmd_deriv` | CMD-DERIV | +20 | E1 | 真衍生品贡献 (替代 fake)? | 30 min |
| **E19c** | `v0601_E19c_cmd_full` | CMD-ONCHAIN + DERIV | +50 | E19a/b | cmd 内部互补 vs 冗余? | 30 min |
| **E20**  | `v0601_E20_integrated` | BGEO-FULL + CMD-FULL | +94 | E18b, E19c | 两源数据是否互补? | 30 min |
| **E18c** | `v0601_E18c_bgeo_extras` *(可选)* | + BGEO-EXTRA | +10 | E18b | aviv/reserve_risk 额外贡献? | 30 min |
| **E19d** | `v0601_E19d_cmd_t2` *(可选)* | + CMD-T2 | +18 | E19c | Tier 2 额外贡献? | 30 min |
| **E21** | `v0601_E21_decontam` *(条件)* | E20 − fake (price_mom_smooth, volume_cumsum) | −7 | E20 | 清理 fake 后是否还行? | 30 min |

> *(可选)* = 只在前置实验显著提升时执行
> *(条件)* = 只在 E19b 证明真衍生品有效时执行（确认可以替代 fake）

### 3.2 Wave 分组

```
═══════════════════════════════════════════════════════════
Wave 1: 单数据源隔离 (3 实验, 1.5h)
═══════════════════════════════════════════════════════════
  E18a — BGeometrics LTH/STH core (6 indicators)
  E18b — BGeometrics LTH/STH + interactions
  E19c — crypto-market-data 全 Tier 1 (12 indicators)
    [跳过 E19a/E19b 子分解, 直接合并跑]
    [理由: 链上 + 衍生品本就该一起评估]

  → 决策点 P1: 哪个数据源更值得整合?

═══════════════════════════════════════════════════════════
Wave 2: 双源整合 (1 实验, 0.5h)
═══════════════════════════════════════════════════════════
  E20  — BGEO + CMD 全部整合

  → 决策点 P2: 整合 > Σ(单源) ? 还是冗余?

═══════════════════════════════════════════════════════════
Wave 3: 子分解 (条件触发, 1h)
═══════════════════════════════════════════════════════════
  E19a — CMD-ONCHAIN only       [触发条件: E19c 显著提升]
  E19b — CMD-DERIV only         [同上]

  → 决策点 P3: 链上 vs 衍生品 谁是主贡献?

═══════════════════════════════════════════════════════════
Wave 4: 候选 + 清理 (条件触发, 1.5h)
═══════════════════════════════════════════════════════════
  E18c — + BGEO-EXTRA (aviv, reserve_risk) [E18b 显著时]
  E19d — + CMD-T2 候选 6 个                [E19c 显著时]
  E21  — E20 - fake_features              [E19b 显著时,
                                            确认真数据可替代]

  → 决策点 P4: 最终生产模型应该是哪个?
```

---

## 4. 决策树（每 Wave 后判断）

### 4.1 决策点 P1 (Wave 1 后)

```
读 E18a / E18b / E19c 的 Kappa & F1 vs E1:

if E18b.Kappa > E1.Kappa * 1.05 AND E19c.Kappa > E1.Kappa * 1.05:
    → 两源都有价值，执行 E20 整合实验
elif E18b.Kappa > E1.Kappa * 1.05 AND E19c.Kappa <= E1.Kappa * 1.05:
    → 只有 BGEO 有价值，跳过 E20，执行 E18c (候选 ablation)
elif E18b.Kappa <= E1.Kappa * 1.05 AND E19c.Kappa > E1.Kappa * 1.05:
    → 只有 CMD 有价值，跳过 E20，执行 E19a/b 子分解
else:
    → 两源都失败，归档全部为反面教材，回到 Phase 3 剪枝路线
```

### 4.2 决策点 P2 (E20 后)

```
读 E20 vs max(E18b, E19c):

if E20.Kappa > max(E18b, E19c).Kappa * 1.02:
    → 两源互补，E20 是 promotion 候选
    → 继续 Wave 4 看是否能更好
elif abs(E20.Kappa - max(E18b, E19c).Kappa) < 0.005:
    → 两源高度冗余, 选 Kappa 高的 + 特征数少的
    → 跳过 Wave 3
else:
    → E20 反而下降 = 信号互相干扰
    → 退回单源最佳, 调研干扰来源
```

### 4.3 决策点 P3 (Wave 3 子分解后, 仅 E19c 显著时)

```
对比 E19a (only onchain) vs E19b (only deriv) vs E19c (combined):

if E19a + E19b > E19c:
    → 子集互补，但合并出现交互效应不好
    → 用 E19a 或 E19b 单一
elif E19a > E19c * 0.95 AND E19b ≈ E1:
    → 链上是主贡献, 衍生品几乎无用
    → 简化生产: 只用 onchain
elif E19b > E19c * 0.95 AND E19a ≈ E1:
    → 衍生品是主贡献 (= 真 funding/OI 起作用)
    → 强烈支持执行 E21 (清理 fake)
else:
    → 两子集都有用，用 E19c (combined)
```

### 4.4 决策点 P4 (Wave 4 后)

```
对比所有候选: E20, E18c, E19d, E21

选择 Kappa 最高 + 特征数合理 (<200) + Sharpe ≥ baseline 的那个。
按 OPS_MANUAL §3 promotion SOP 流程晋升到 production。
```

---

## 5. 实验配置详情

### 5.1 E18a: BGeometrics LTH/STH Core

```yaml
# configs/experiments/weekly/v0601_E18a_bgeo_core.yaml
name: v0601_E18a_bgeo_core
inherits: weekly_bear_v0305_E1_decontam  # 继承 E1 baseline
hypothesis: |
  BGeometrics 6 个 LTH/STH 链上原生指标 (mvrv/nupl/sopr × lth/sth)
  对 Bear 模型的周期识别能力有显著提升。预期 Kappa ↑ 3-5%.

features:
  sets: [..., external_lth_sth_core]  # 在 E1 基础上追加

# 其他训练参数完全继承 E1
```

**特征组成** (36 个):
```
6 个原始指标 × 6 个衍生 = 36
ext_lth_mvrv, ext_lth_mvrv_ma_7, _ma_30, _change_7, _change_30, _slope_30
ext_sth_mvrv, ...
ext_lth_nupl, ...
ext_sth_nupl, ...
ext_lth_sopr, ...
ext_sth_sopr, ...
```

### 5.2 E18b: + 行为分化交互

```yaml
name: v0601_E18b_bgeo_full
inherits: weekly_bear_v0305_E1_decontam
hypothesis: |
  在 E18a 基础上, 添加 LTH vs STH 行为分化交互特征,
  捕捉 "派发期" / "恐慌底" 等典型周期信号。预期 Kappa 再 ↑ 1-3%.

features:
  sets: [..., external_lth_sth_core, external_lth_sth_interactions]
```

**追加 8 个交互特征**（详见 plan §3.3）

### 5.3 E19c: crypto-market-data 全 Tier 1

```yaml
name: v0601_E19c_cmd_full
inherits: weekly_bear_v0305_E1_decontam
hypothesis: |
  crypto-market-data 的 12 个 CryptoQuant-style 指标
  (链上 6 + 衍生品 6) 提供与 BGEO 不同维度的微观结构信号,
  预期独立提升 Kappa 2-4%.

features:
  sets: [..., external_cmd_onchain, external_cmd_deriv]
```

**特征组成** (~50 个):

*链上类 (5 个衍生 × 6 = 30)*:
```
exchange_netflow, exchange_whale_ratio, miner_netflow_total,
miners_position_index, coinbase_premium_index, puell_multiple,
sc_exchange_netflow
→ × (raw, ma_7, ma_30, change_7, slope_30)
```

*衍生品类 (5 个衍生 × 4 = 20)*:
```
funding_rates, open_interest, taker_buy_sell_ratio,
long_liquidations + short_liquidations (合并为 net_liq_imbalance)
→ × (raw, ma_7, ma_30, change_7, slope_30)
```

### 5.4 E20: 整合

```yaml
name: v0601_E20_integrated
inherits: weekly_bear_v0305_E1_decontam
hypothesis: |
  BGEO LTH/STH (行为周期) 与 CMD (微观结构/衍生品) 是正交信息维度,
  整合后应有协同效应。预期 Kappa 比 max(E18b, E19c) 再 ↑ 1-2%.

features:
  sets: [..., external_lth_sth_core, external_lth_sth_interactions,
              external_cmd_onchain, external_cmd_deriv]
```

### 5.5 E18c / E19a / E19b / E19d / E21（条件触发，详见 §3 总览）

完整配置生成时机：触发条件成立后再写。

---

## 6. 验收标准（统一）

每个实验完成后必须报告：

| 指标 | 计算 | 通过门槛 |
|---|---|---|
| **Kappa OOS** | Walk-forward avg | ≥ E1 × 1.05 |
| **F1 OOS** | 同上 | ≥ E1 × 1.05 |
| **Accuracy OOS** | 同上 | ≥ E1 × 1.02 |
| **Walk-forward folds** | 实测 | ≥ 8 |
| **Paired t-test** | Kappa fold-level vs E1 | p < 0.1 |
| **PnL Sharpe** | 见 `pnl_backtest_v0305.py` | ≥ E1 |
| **Top-20 importance** | LightGBM feature_importance | 新增特征占比 ≥ 5/20 |

**任何一项不达标 → 标记 "negative"**，写 `experiments/weekly/{exp}/CONCLUSION.md` 归档为反面教材。

---

## 7. 时间预算

| Wave | 实验 | 单实验 | 累计 |
|---|---|---|---|
| 准备 | 写 download script + features module | 1.5h | 1.5h |
| Wave 1 | E18a + E18b + E19c | 1.5h | 3.0h |
| 分析 | 决策点 P1 + 写报告 | 0.5h | 3.5h |
| Wave 2 | E20 (条件触发) | 0.5h | 4.0h |
| 分析 | 决策点 P2 + 写报告 | 0.5h | 4.5h |
| Wave 3 | E19a + E19b (条件触发) | 1.0h | 5.5h |
| Wave 4 | E18c / E19d / E21 (按需) | 1.5h | 7.0h |
| 总结 | 最终决策 P4 + promote SOP | 1.0h | **~8h** |

可以一天内冲完 Wave 1-2，剩余 Wave 视决策结果分散到第 2-3 天。

---

## 8. 资源依赖清单

实施前必须就绪：

- [ ] **特征模块**: `src/features/external.py` 新增 3 个 builders
  - `build_lth_sth_core_features`
  - `build_lth_sth_interaction_features`
  - `build_cmd_onchain_features`
  - `build_cmd_deriv_features`
- [ ] **数据下载脚本**: `scripts/download_onchain_bgeo.py`
- [ ] **数据落地**: `data/external/onchain/{indicator}.csv` × 6 + `data/external/cmd/{indicator}.csv` × 12
- [ ] **特征注册**: `src/features/__init__.py` 注册 4 个新 set
- [ ] **Probe 复测**: 实验前 1 小时再次跑 `probe_bgeometrics_cdn.sh` 确认 CDN 可达
- [ ] **CMD 数据更新**: `cd crypto-market-data && git pull`（确认最新数据）
- [ ] **基线 E1 验证**: 复现守门绿（`scripts/verify_reproducibility.py`）

---

## 9. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| **Wave 1 三个实验全失败** | 🟡 中 | 立刻终止，归档反面教材，跳到 Phase 3 剪枝 |
| **特征数膨胀到 ~220 → 欠拟合** | 🟡 中 | 后续配合 Phase 3 剪枝；E20 失败时退回单源 |
| **CMD 数据 2022-12 起 → 训练集前期 NaN 60%** | 🟡 中 | 用 fillna(0) + 加 `_isna` 指示特征；接受短历史 |
| **E18a/b 显著但 LTH/STH 真值跟生产 CDN 不对齐** | 🔴 高 | E18 完成后必跑 `verify_cdn_match.py` 比对本地 vs CDN |
| **生产部署后 BGeo CDN 挂掉** | 🟡 中 | onchain_lth_sth_feature_plan §5.4 三级降级策略 |
| **跑实验中途 OOM** | 🟢 低 | 用相同 LightGBM 配置，不引入大型模型 |

---

## 10. 实施 SOP

每个实验严格按以下流程：

```bash
# Step 1: 训练
.venv/bin/python scripts/run_experiment.py \
    --config configs/experiments/weekly/{exp}.yaml \
    --overwrite

# Step 2: 立即看 metrics
cat experiments/weekly/{exp}/metrics.json

# Step 3: PnL 回测
.venv/bin/python scripts/pnl_backtest_v0305.py \
    --exp-dir experiments/weekly/{exp}

# Step 4: 跟 E1 对比
.venv/bin/python scripts/compare_experiments.py \
    --ids weekly_bear_v0305_E1_decontam {exp}

# Step 5: 写 CONCLUSION.md (无论成败)
# 模板:
#   - Hypothesis
#   - 实测 metrics vs baseline
#   - 显著性 (t-test)
#   - 特征重要性 top-20
#   - 决策: PROCEED / RETIRE / INVESTIGATE
```

---

## 11. 跟现有 Plan 的关系

| 文档 | 关系 |
|---|---|
| `feature_engineering_roadmap.md` | 本文档 = 该 roadmap Phase 2 的执行细化 |
| `onchain_lth_sth_feature_plan.md` | 本文档实施前者 §4 的实验路线，并扩展到 CMD 数据源 |
| `cr_0522_feature_engineering.md` | 本文档执行其建议的 P1-P3 整合策略 |
| `OPS_MANUAL.md` §2-§3 | 本文档完全对齐实验规范 |

---

## 12. 不做的事 (YAGNI)

明确**不**纳入本批次：

- ❌ 修改 LightGBM 超参数（只动特征集，控制变量）
- ❌ 改 walk-forward 划分（保持跟 E1 一致）
- ❌ 加入 LSTM/Transformer（违反 roadmap §6）
- ❌ 一次跑全 9 个不看中间结果（违反决策树原则）
- ❌ 在实验进行中调整 hypothesis（防 p-hacking）
- ❌ 训练 Bull 模型（先验证 Bear，下批次再做 Bull）

---

## 13. 决策检查清单

启动前确认：

- [ ] `onchain_lth_sth_feature_plan.md` 已评审通过
- [ ] §8 资源依赖全部就绪
- [ ] 当前 E1 baseline 复现守门绿
- [ ] git working tree clean (方便每实验独立 commit)
- [ ] 准备好接受 "全部 9 个都失败" 的可能性
- [ ] 准备 ~8h 集中时间块 (分散执行也行)

---

## 14. 启动命令（一键）

资源就绪后：

```bash
# Wave 1 一键执行（3 个实验串行）
for exp in v0601_E18a_bgeo_core v0601_E18b_bgeo_full v0601_E19c_cmd_full; do
    .venv/bin/python scripts/run_experiment.py \
        --config configs/experiments/weekly/${exp}.yaml \
        --overwrite \
        2>&1 | tee experiments/weekly/${exp}/train.log
done

# Wave 1 决策报告
.venv/bin/python scripts/compare_experiments.py \
    --ids weekly_bear_v0305_E1_decontam \
          v0601_E18a_bgeo_core \
          v0601_E18b_bgeo_full \
          v0601_E19c_cmd_full \
    --output docs/reports/wave1_decision_v0601.md
```

---

*维护: 每个 Wave 完成后更新本文档 §3 状态列；最终决策后归档到 `docs/plans/archived/`*
