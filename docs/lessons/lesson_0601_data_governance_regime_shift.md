# Lesson Learned: 数据治理事故 + Regime Shift Negative Transfer

> **日期**: 2026-06-01
> **作者**: sam (with Qiu)
> **触发场景**: Phase 2.5 E18a 实验跑出来 Kappa 暴跌 35%, 调查发现 E1 baseline 自身也崩了
> **影响范围**: 所有 v0305 ~ v0529 实验的可复现性 + 未来所有 weekly bear 实验的基准选择

---

## TL;DR (1 分钟版)

今天在跑 E18a (BGeometrics LTH/STH 链上指标实验) 时, 发现 Kappa 比 E1 baseline 差 35%, 准备判定 LTH/STH 路线失败。**但用户问了一个关键问题**: "两个实验是同一基准吗?"

复现验证发现两个**同等重要的事故**:

1. **数据治理事故**: BTC csv 在 2026-05-29 ~ 2026-06-01 之间被回填了 2018-2019 的早期数据 (2192 行 → 3074 行), 但 config 写的 `start: 2018-01-01` 没变. 导致 E1 production (训练时 csv 还只有 2020+) 在新数据上 kappa 从 0.348 崩到 0.241 (-30%)。
2. **Regime Shift Negative Transfer**: 即使把 OOS 窗口对齐 (末 53 折), 加入 2018-2019 数据训练的模型在**完全相同的 53 个测试折**上 kappa 也低 19% (0.218 vs 0.269)。即早期数据**不只是没贡献, 还主动让模型变笨**。

**最终结论**: 锁定 **2020-01-01** 为所有 weekly bear 实验的统一起始日, 写入 plan 和 config 注释。

---

## 1. 事件时间线

| 时刻 (2026-06-01) | 事件 |
|---|---|
| 06:31 | E18a 跑完, Kappa=0.2273 |
| 06:32 | 跟 production E1 metrics.json (0.348) 对比, 准备判定 **失败 -35%** |
| 06:32 | 用户问: "两个实验是同一基准吗?" |
| 06:37 | 重跑 E1 (当前数据 + 当前代码) → Kappa=0.2408, **E1 自己就崩了 -30%** |
| 06:40 | 调查 data_manifest.json: production E1 effective_start=2020-01-01, rows=2192 |
| 06:42 | 当前 BTC csv: rows=3074, 多了 2018-01-01 ~ 2019-12-31 的 ~882 行 |
| 06:43 | 创建 `v0601_E1_repro_2020start`, 锁定 start=2020-01-01 |
| 06:43 | 重跑 → Kappa=0.3480, **bit-exact 复现 production E1** ✅ |
| 06:44 | 创建 `v0601_E18a_bgeo_core_2020start` (公平基准 E18a) |
| 06:45 | 跑完 → Kappa=0.3244, **跟 E1 公平对比仍 -6.8%** |
| 06:50 | 深挖 fold_metrics, 发现 negative transfer 证据 |
| 06:55 | 用户决定 D+A 路线: 文档化 + 锁基准 |

---

## 2. 事故 1: BTC CSV 数据治理事故

### 2.1 事实

| 项 | production E1 (2026-05-29) | 现在 (2026-06-01) |
|---|---|---|
| `data/raw/btc_binance_BTCUSDT_1d.csv` rows | 2341 | 3074 |
| start date | 2020-01-01 | 2018-01-01 |
| end date | 2026-05-29 | 2026-06-01 |
| sha256 | `2b0aa34c...` | (未记录) |
| config `data.start` (没变) | `'2018-01-01'` | `'2018-01-01'` |
| config `data.end` (没变) | `'2025-12-31'` | `'2025-12-31'` |
| effective_start | 2020-01-01 (csv 限制) | **2018-01-01** (csv 扩了) |
| effective_rows | 2192 | **3074** |

### 2.2 影响

production E1 在新数据下用同一份代码跑出:
```
accuracy:  0.8781 → 0.8497  (-3.2%)
f1:        0.4161 → 0.3233  (-22.3%)
precision: 0.4085 → 0.2823  (-30.9%)
recall:    0.4240 → 0.3783  (-10.8%)
kappa:     0.3480 → 0.2408  (-30.8%)
```

**直接违反 OPS_MANUAL §5.3 "E1 bit-exact" 承诺**。

### 2.3 根因

`data_manifest.json` 在 promote 时**已经记录了** `effective_rows=2192, start=2020-01-01`,
但没有:

1. ❌ 没有把 csv sha256 写入 config (只在 manifest 单独存)
2. ❌ 没有在 runner 启动时校验 csv hash 是否跟 manifest 一致
3. ❌ 没有强制 csv 进 git LFS 或固定版本
4. ❌ 没有让 config.data.start 跟 etive_start 强一致

### 2.4 应对措施

| 优先级 | 措施 | 状态 |
|---|---|---|
| 🔴 P0 | 所有新 config 显式声明 `data.start: '2020-01-01'`, 不依赖 csv 自身范围 | ✅ 本次已做 |
| 🔴 P0 | 在 plan 中写明 weekly bear 基准 = 2020-01-01 | ✅ 本次已做 |
| 🟡 P1 | runner 启动时打印 csv 实际 sha256, 跟 config.data.expected_sha256 (新字段) 比对, 不一致 WARN | ⏳ 待办 |
| 🟡 P1 | promote 工具检查 effective_rows / sha256 是否匹配 manifest | ⏳ 待办 |
| 🟢 P2 | 考虑 BTC csv 切到 git LFS 或冻结版本子目录 (data/frozen/) | ⏳ 待办 |
| 🟢 P2 | live_signal 启动时检查数据 freshness, 但不允许范围扩张 | ⏳ 待办 |

---

## 3. 事故 2: Regime Shift Negative Transfer

### 3.1 现象 (反直觉发现)

直觉: "数据多 → 训练更充分 → 效果更好"
现实: **完全反过来**

证据 (E1 同代码同 config, 唯一变量 = data.start):

| 实验 | data.start | fold 数 | aggregate kappa |
|---|---|---|---|
| E1 (2020 起) | 2020-01-01 | 53 | **0.3480** |
| E1 (2018 起) | 2018-01-01 | 88 | 0.2408 |

差额 35 折是新增的, OOS 时间在 2020 ~ 2022 之间。

### 3.2 关键诊断: 末 53 折对比 (理论 OOS 完全相同)

| 末 53 折 | kappa | f1 | acc |
|---|---|---|---|
| **2018 start** (train pool 含 2018-2019) | 0.2184 | 0.2143 | 0.8811 |
| **2020 start** (train pool 不含) | 0.2690 | 0.2730 | 0.8781 |
| **差额** | **-19%** | **-21%** | -0.3% |

→ **OOS 完全一样, 唯一区别是训练池多了 2018-2019 → 模型反而变差 19%**

这不是 "多出 35 个 fold 拖累 aggregate" 那么简单, 而是 **早期数据主动污染了后期模型** = Negative Transfer。

### 3.3 多出的 35 折是灾难现场

```
2018 start 多出前 35 折 (OOS 2020 之前):
  kappa mean = 0.1106 (几乎随机)
  f1 mean    = 0.1418
  acc mean   = 0.8023  ← 全猜 0 也有 80%

前 8 折几乎全猜 0 (kappa=0 或 NaN):
  train: 2018-01-01 ~ ~2020-09 (BTC 19k→3k 大熊市为主)
  OOS:   2020-10 之后 (COVID 反弹 + 牛市起步)
  → 用熊市训, 牛市测 → 模型完全猜错方向
```

### 3.4 真正原因: 加密市场 Regime Shift

| 时代 | 主导特征 | 行为模式 |
|---|---|---|
| **2018-2019** | ICO 泡沫破灭, BTC 19k→3k 大熊市 | 散户主导, 高波动, 鞭子行情 |
| **2020+** | 减半 + COVID 印钞 + 机构 + ETF | 大资金主导, 周期更明确 |

Walk-forward expanding window 默认假设 **stationary**, 但 crypto 显然不是。Expanding window 会让 2018-2019 的过时模式永远留在训练池里, 持续误导模型。

### 3.5 印证 OPS_MANUAL 既有教导

| OPS_MANUAL 条款 | 本次印证 |
|---|---|
| §4.1 **Regime-Specific**: Bull/Bear 分别优化 T | ✅ 加 2018-2019 拖累说明 regime 确实不同 |
| §4.2 **致命陷阱: Regime 依赖** | ✅ 这次亲眼看到 negative transfer 的破坏力 |
| §2.2 **滚动训练**: 必须 Expanding 或 Rolling | ⚠️ Expanding 在非平稳市场上有 negative transfer 风险, Rolling 可能更合适 |

---

## 4. 教训 & 行动项

### 4.1 立即生效 (本 commit 含)

- [x] **锁定 2020-01-01** 为所有 weekly bear 实验的统一基准
- [x] 在 `docs/plans/experiment_matrix_v0601.md` §0 加 "基准锁定" 声明 → 后升级为 `docs/plans/phase2.5_feature_landscape_v0601.md` §0.2
- [x] 在 `docs/plans/onchain_lth_sth_feature_plan.md` §7 加 E18a 阶段结论
- [x] 在 `docs/plans/bgeometrics_tier_s_expansion_v0608.md` §10 加 "基准 = 2020-01-01" 检查项 → 后与主文档合并为 `phase2.5_feature_landscape_v0601.md` §5.2
- [x] 本 lesson 文档归档全部诊断证据

### 4.2 短期 (本周内)

- [ ] **P0**: `runner.py` 启动时打印 csv 实际 sha256 + 实际 effective range
- [ ] **P0**: 给 config schema 加可选 `data.expected_sha256` 字段, 不一致 WARN
- [ ] **P1**: 给现有 production model manifest 加 baseline_sha256_verified=true 字段, 未来检查

### 4.3 中期 (Phase 3 前)

- [ ] **P1**: 跑 Rolling Window 对照实验 (固定 train_window=800), 看是否消除 negative transfer
- [ ] **P1**: 跑 Regime Detection (用 200d MA 或 hash ribbon 分 bull/bear), Bull/Bear 分模型
- [ ] **P2**: BTC csv 进 git LFS 或冻结版本目录

### 4.4 不做的事 (YAGNI)

- ❌ 不在 v0601 上重做所有历史实验 (沉没成本, 既然教训学到了往前走)
- ❌ 不立即上 Regime Detection (Phase 3 再说, 不在 Wave 1 范围)
- ❌ 不把 BTC csv 改成只存 2020+ (data layer 应该保留全量, 是 effective range 应该锁)

---

## 5. 附录: 4 个对照实验完整 metrics

| 实验 | 数据范围 | n_folds | accuracy | f1 | precision | recall | kappa |
|---|---|---|---|---|---|---|---|
| E1 production (2026-05-29) | 2020-2025 | (~53) | 0.8781 | 0.4161 | 0.4085 | 0.4240 | 0.3480 |
| **E1 repro_2020start** ✅ bit-exact | 2020-2025 | 53 | 0.8781 | 0.4161 | 0.4085 | 0.4240 | 0.3480 |
| E1 重跑 (今天数据 2018 起) | 2018-2025 | 88 | 0.8497 | 0.3233 | 0.2823 | 0.3783 | 0.2408 |
| E18a (原版, 2018 起) | 2018-2025 | 88 | 0.8523 | 0.3089 | 0.2777 | 0.3479 | 0.2273 |
| **E18a (公平版, 2020 起)** | 2020-2025 | 53 | 0.8769 | 0.3929 | 0.3970 | 0.3889 | 0.3244 |

### 5.1 LTH/STH 公平评估 (2020-2025 同基准)

```
E1 baseline:    kappa = 0.3480
E18a (LTH/STH): kappa = 0.3244
─────────────────────────────
delta:          -0.0236 (-6.8%)
```

→ LTH/STH 36 个特征在 weekly bear (T=21, X=0.04) 任务上**无显著 alpha**, 轻微负面 (噪音级)。

### 5.2 LightGBM Feature Importance 旁证

```
ext_lth_sopr_ma_30: rank #8 (top-10!)
ext_sth_sopr_change_30: rank #18
LTH/STH top-50 占 10/50 (按比例分布, 模型用了但没产生正面 alpha)
```

→ 模型有"用"这些特征, 但用得不好或这些特征**就是噪声**。

---

## 6. 元教训 (Meta Lessons)

1. ✅ **复现验证是金标准** — 一句 "两个实验是同一基准吗?" 救了我们一次错误决策
2. ✅ **直觉不可信** — "数据多 → 模型好" 在非平稳时序上是个常见误解
3. ✅ **Negative Transfer 真实存在** — 不是教科书概念, 而是工程现实
4. ✅ **配置文件需要校验** — config.data.start 跟 csv 实际 range 不一致, 必须强制 WARN
5. ✅ **失败实验也有价值** — E18a 本身失败, 但暴露了 2 个核心治理问题
6. ✅ **plan + commit 大于全部** — 没有 plan 体系, 这次发现就会变成口头记忆然后遗忘

---

*这份 lesson 应该在每次新人 onboarding + 每次 quarterly review 时重读。*
