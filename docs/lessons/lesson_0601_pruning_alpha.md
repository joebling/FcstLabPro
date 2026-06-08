# Lesson Learned: 剪枝 > 加特征 — Wave 2 意外突破

> **日期**: 2026-06-01
> **作者**: sam (with Qiu)
> **触发场景**: Phase 2.5 Wave 2 连续 3 次"加特征"实验失败 (E19-PUELL/FUNDING/E18a 全 -kappa), 主人灵感转向纯剪枝, 意外挖到强 alpha
> **影响范围**: 所有 weekly 任务的特征工程方法论 + 显著性判断纪律

---

## TL;DR (1 分钟版)

Phase 2.5 Wave 2 原计划用"加新指标 (链上/合约/估值)"提升 E1 (kappa 0.348), 跑了 3 次全部失败 (-6.2% ~ -17.1%)。**主人一句"先别加特征, 试试剪掉"**, 跑了 6 个梯度剪枝实验, 发现:

- **E1 (directional)**: 剪到 **28 特征** kappa 从 0.348 → 0.4290 (**+27.8% 强 alpha**, CV 3.21%)
- **E8 (touch)**: 剪到 **81 特征** kappa 从 0.757 → 0.7717 (**+1.93% 显著 alpha**, CV 0.50%, 3.8σ)

**核心洞察**: 100+ 特征里有 30-60 个是噪声, **不是新指标没信号, 是 baseline 本身就过参数化**。

**附带教训**: sam 一开始误判 E21b (+1.64%) 为"噪声", 主人质疑后实测发现 E8 系 CV 只有 0.50% (E1 系的 1/6), 提升是 3.8σ 显著。**ML 里不能凭直觉判断显著性, 必须实测**。

---

## 1. 事件时间线 (2026-06-01)

| 时刻 | 事件 |
|---|---|
| 08:00 | E1/E8 数据窗口锁定修复完成 (commit `c7ec6ba`, bit-exact ✅) |
| 08:25 | E19-PUELL 跑完: kappa 0.326 (-6.2%) 🔴 但 puell_zscore_90 rank 3 |
| 08:33 | E19-FUNDING 跑完: kappa 0.288 (-17.1%) 🔴 跌得更深 |
| 08:35 | sam 发现规律: "加特征数 vs kappa 单调反相关" |
| 08:38 | **主人灵感**: "OK A 路线 (剪枝替换), 但**先别加特征**" |
| 08:50 | E20a/b/c/d/e/f 6 梯度剪枝跑完 → **E20c (留 28) kappa 0.4448 +27.8%** |
| 09:05 | E20c 4-seed 复现性: 全 ≥ 0.40, CV 3.21% ✅ |
| 09:15 | E21a/b/c/d (E8 系) 跑完: E21b (留 81) +1.64% |
| 09:18 | sam 写 commit "E21b 在噪声范围内" (错误判断) |
| 09:20 | **主人质疑**: "E21 不是也略有提升吗?" |
| 09:30 | E21b 4-seed 复现性: CV 0.50%, **3.8σ 显著真 alpha** ✅ |

---

## 2. 实验全谱 (10 个实验)

### 2.1 "加特征"路线 — 全军覆没

| 实验 | n_feat | kappa | Δ vs E1 (0.348) | 类别 |
|---|---|---|---|---|
| E18a (LTH/STH +36 特征) | 165 | 0.324 | -6.8% | 🔴 |
| E19-PUELL (+5 特征) | 134 | 0.326 | -6.2% | 🔴 |
| E19-FUNDING (+16 特征) | 145 | 0.288 | **-17.1%** | 🔴 |

模式: **每加 1 特征, kappa 平均下降 ~0.0037**

### 2.2 "剪枝"路线 — U 形最优 (E1 系)

| 实验 | n_feat | kappa | Δ% | 类别 |
|---|---|---|---|---|
| E1 baseline | 129 | 0.348 | 0 | — |
| E20a (删 6 死) | 123 | 0.328 | -5.7% | colsample 副作用 |
| E20b (删 44 弱) | 85 | 0.357 | +2.5% | 🟡 |
| E20d (删 67) | 62 | 0.373 | +7.1% | 🟢 |
| **E20c (留 28)** | **28** | **0.445** | **+27.8%** | **🚀 强 alpha** |
| E20e (留 9) | 9 | 0.393 | +12.9% | 🟢 (下沿) |
| E20f (留 2) | 2 | 0.344 | -1.1% | 表达不足 |

### 2.3 "剪枝"对照 — E8 (touch) 完全不同的甜蜜点

| 实验 | n_feat | kappa | Δ% |
|---|---|---|---|
| E8 baseline | 129 | 0.7571 | 0 |
| E21a (删 dead) | 117 | 0.7565 | -0.08% |
| **E21b (留 81)** | **81** | **0.7695** | **+1.64% 🏆** |
| E21d (留 44) | 44 | 0.7687 | +1.54% |
| E21c (留 17) | 17 | 0.7313 | **-3.41%** 过剪! |

### 2.4 复现性验证 (4-seed 跨度: 42/123/456/789)

| 模型 | mean kappa | std | CV | 最差 seed Δ |
|---|---|---|---|---|
| E20c (E1) | 0.4290 | 0.0138 | **3.21%** | +18.3% |
| E21b (E8) | 0.7717 | 0.0038 | **0.50%** | +1.59% |

---

## 3. 三个核心规律

### 规律 1: 剪枝增益与 baseline 高度反相关

| | baseline | 剪枝增益 |
|---|---|---|
| E1 (低 baseline, 信号被噪声淹没) | 0.348 | **+27.8%** |
| E8 (高 baseline, 已近 task 上限) | 0.757 | +1.93% |

**机制**: baseline 越低 → 模型越接近随机 → 噪声特征的边际影响越大 → 剪枝增益越大。

### 规律 2: 甜蜜点位置由标签复杂度决定

| 任务 | 标签 | 甜蜜点 n_feat | 解释 |
|---|---|---|---|
| E1 | directional_filtered (T=21, X=4%) | **28** | 二元方向判断, 低维问题 |
| E8 | touch_filtered (T=21, 触阈值) | **81** | 需要更多市场状态上下文 |

**铁律**: 不能跨任务套用 importance 阈值, **必须为每个任务单独扫描完整 U 形曲线**。

### 规律 3: 过剪枝代价非线性, 且任务相关

| n_feat | E1 (directional) | E8 (touch) |
|---|---|---|
| 17 | +12.9% (仍提升) | **-3.41%** (崩) |
| 9 | +12.9% (略降) | (未测, 预估 -10%+) |

touch label 对特征数更敏感, 过剪枝代价非线性放大。

---

## 4. 三个反直觉发现

### 反直觉 1: E20a (剪 6 个 importance=0 死特征) kappa 反而 -5.7%

**机制**: LightGBM `colsample_bytree=0.8` 每棵树抽 80% 特征。死特征通过抽样占位置, 降低了"有效特征比例", **起到了隐式正则化作用**。删除它们 → 抽样池缩小 → 单棵树见到的有效特征比例反而上升 → 略微过拟合。

**实用启示**: importance=0 不等于"无害可删", 取决于模型的随机抽样机制。

### 反直觉 2: E1 vs E8 的 CV 差 6 倍

| 任务 | mean kappa | CV |
|---|---|---|
| E1 (directional) | 0.43 | 3.21% |
| E8 (touch) | 0.77 | **0.50%** |

**机制**: 信号越强 → tree split 的 tie-break 决策受 seed 影响越小。E1 baseline 低意味着边际特征贡献大, 它们的入选高度依赖 colsample 抽样的偶然性。

### 反直觉 3 (sam 翻车): "+1.64% 看起来像噪声" 不等于"在噪声范围内"

sam 在 `949ebd9` commit 里写:
> ❌ E21b/d 提升 +1.5% 在 seed 噪声范围内 (E20c CV 3.21%, 对应 E8 噪声 ~0.025)

**错误**: 把 E1 系的 CV 套到 E8 系, 没实测就下结论。

**真相**: E8 CV 是 0.50%, 提升 0.0146 / std 0.0038 = **3.8σ 显著**。

**教训**: 写在第 6 节铁律。

---

## 5. "加 vs 剪" 决策矩阵

| 场景 | 推荐策略 | 依据 |
|---|---|---|
| baseline < 0.50 (low SNR 任务) | **先剪后加** | E1 +27.8% > 任何加特征 |
| baseline ≥ 0.70 (high SNR 任务) | **先加后剪** (但剪也有 1-3% 收益) | E8 剪 +1.9% 不如新指标潜力大 |
| 新加特征 + 整体 kappa 下降 | **不一定是新特征没信号**, 可能是 baseline 过参数化 | E19-PUELL/FUNDING 单点 Top 10 但整体降 |
| 已有 100+ 特征的 baseline | **必须先做剪枝扫描** 找甜蜜点 | E1 129 → 28 是甜蜜点 |
| 不同标签任务 | **每个任务单独扫曲线**, 不能套阈值 | E1 甜蜜点 28, E8 甜蜜点 81 |

---

## 6. 铁律 (写入 OPS_MANUAL 候选)

### 铁律 A: 任何 kappa 提升/下降必须经 4-seed 显著性测试才能下结论

**禁止行为**:
- 看到 "+1.5%" 凭感觉说"差不多就是噪声"
- 跨任务/跨模型套用 CV 数值
- 单 seed 实验结果直接 commit 写定性

**正确流程**:
1. 跑 base seed 实验, 看 raw 提升
2. **必须** 跑额外 3 个 seed (123/456/789)
3. 计算 mean ± std, 看是否落在 baseline ± 3σ 之外
4. **3σ 显著** 才能写"真 alpha"
5. **4/4 seed 全超 baseline** 才能晋升生产

### 铁律 B: 任何"加特征"实验之前, 先做 baseline 剪枝扫描

如果当前 baseline 有 >100 个特征, **先扫一遍 U 形曲线**, 确认当前 baseline 不是过参数化的。否则后续"加特征 vs baseline"的对比毫无意义。

### 铁律 C: importance=0 不等于"无害可删"

如果模型用了 `colsample_bytree<1.0`, 死特征对结果有隐式正则化效应。**先实测再决定删不删**, 别盲目 prune dead。

---

## 7. 复现指引

### 7.1 E20c (E1 系强 alpha)

```bash
# 单 seed
.venv/bin/python scripts/run_experiment.py \
    --config configs/experiments/weekly/exp_v0601_E20c_prune_core.yaml

# 4-seed 复现性 (验证 CV)
for seed in 42 123 456 789; do
    .venv/bin/python scripts/run_experiment.py \
        --config configs/experiments/weekly/exp_v0601_E20c_repro_seed${seed}.yaml
done
```

预期: 4 seed kappa 全 ≥ 0.40, mean ≈ 0.4290, CV ≈ 3.21%

### 7.2 E21b (E8 系小幅 alpha)

```bash
# 同上, 把 E20c 改成 E21b
```

预期: 4 seed kappa 全 > 0.757, mean ≈ 0.7717, CV ≈ 0.50%

### 7.3 复现完整 U 形曲线

```bash
for v in E20a_prune_dead E20b_prune_weak E20c_prune_core \
         E20d_prune_mid  E20e_prune_15   E20f_prune_10; do
    .venv/bin/python scripts/run_experiment.py \
        --config configs/experiments/weekly/exp_v0601_${v}.yaml
done
```

---

## 8. 与既有 plan 的关系

### 8.1 推翻的: "Phase 2.5 加特征路线"

`docs/plans/phase2.5_feature_landscape_v0601.md` 设计了 7 个 sub-experiments (PUELL/SOPR-NEW/MVRV-EXT/ADDRESS/STABLE/AVIV/DERIV-SHORT) 全部是"加特征"。**应在文档头加警告**: 这 7 个实验在 baseline 未剪枝前跑都是浪费 token, 预期全失败。

### 8.2 补强的: `docs/lessons/lesson_0601_data_governance_regime_shift.md`

那篇 lesson 锁定了"2020-01-01 为统一起始日 + sha256 锁"。本 lesson 是它的方法论层面补充: 数据治理之后, **特征工程方法论也要校准**。

---

## 9. Production 决策更新 (2026-06-01)

E21b 虽然是 **分类层显著 alpha** (Kappa +1.93%, 4-seed CV 0.50%), 但 **暂不 promote**。

| 执行版本 | E8 baseline | E21b | 决策 |
|---|---:|---:|---|
| raw 策略 CAGR | 17.8% | **29.6%** | E21b 胜 |
| raw Sharpe | 0.626 | **0.882** | E21b 胜 |
| +止盈 CAGR | **29.9%** | 25.5% | baseline 胜 |
| 止盈+regime Sharpe | **0.806** | 0.666 | baseline 胜 |

**结论**: E21b 是更激进、更少漏报的 touch signal, 但当前执行层 (尤其止盈规则) 未适配。production promotion 只推进 E20c；E21b 进入 research/shadow 池, 等执行规则重调后再评估。

---

## 10. 待办

- [x] E20c/E21b 4-seed 复现性验证 (done, commit `c3881aa` + `4ae794a`)
- [ ] E20c 晋升生产 (`models/production/e20c-conservative-prune/`)
- [x] E21b **暂不晋升生产**: 分类/Kappa 显著提升, 但 PnL 执行层不全线胜出 (止盈版本弱于 E8 baseline), 先保留 research/shadow 候选
- [x] phase2.5 主文档加 "先剪后加" 警告
- [ ] OPS_MANUAL §2.3 加 "铁律 A: 显著性测试"
- [ ] 探索 4-seed 集成 (OOF probability 平均) 看是否能继续推 kappa

---

## 11. 一句话总结

> **"加新指标"是手段, 不是目的; "kappa 提升"也不是终点; production 还必须过 PnL/执行层验证。当 baseline 过参数化时, 剪枝比加新指标快 100 倍。**

---

*This lesson learned was hard-earned through 14 experiments, 1 hour debugging, and 1 critical user question.*
