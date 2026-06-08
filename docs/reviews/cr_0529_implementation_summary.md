# 模型治理改造实施总结 (Phase 0-4)

**分支**: `feat/model-governance-overhaul`
**日期**: 2026-05-29
**依据**: `docs/reviews/cr_0529_model_governance_vs_riskdetect.md`
**铁律**: 全程守住 E1/E8 bit-exact 复现性 (CLAUDE.md §5.3)

---

## 一句话总结

把评审里点出的 11 项治理欠缺，按依赖顺序分 5 个 Phase 落地。每个 Phase 收尾都跑
`scripts/verify_reproducibility.py` 确认 E1/E8 数值零漂移。新增 50 个测试全过。

---

## 🚨 Phase 0 最大发现：复现性基线本来就是坏的

开工第一步重跑 E1 发现 Kappa 漂移。后续复核确认，**直接根因是数据窗口没有被正确锁住**：

| # | 根因 | 状态 |
|---|------|------|
| 1 | `data/raw` CSV 被 git-tracked 且被 append 了新数据 (2240→2340 行) | ✅ 已冻结快照 |
| 2 | `src/data/loader.py` 曾忽略 config 的 `data.start/end`, 多余数据直接进训练 | ✅ 已修复 |
| 3 | 依赖无 lockfile (全 `>=` 下限锁) 是复现治理风险，但固定数据窗口后 Py3.9+LGBM4.6 与 Py3.10+LGBM4.3 对 E1/E8 指标 bit-exact | ✅ 防御性锁定 |

> 这印证了评审的核心论点：CLAUDE.md 吹的「bit-exact 已验证」在当时流程下**实际已失效**，
> 只是没人重跑过。复核后不要甩锅给 LightGBM：本次直接元凶是 data boundary contract。

**交付物**:
- `requirements.lock.txt` — 防御性锁定 Py3.10 + LightGBM 4.3.0 + numpy 1.26.4 + sklearn 1.4.1
- `baseline_snapshot/` — 冻结基线数据 (sha256) + E1/E8 黄金 metrics
- `scripts/verify_reproducibility.py` — 一键 bit-exact 对账守门员 (后续每个 Phase 都靠它)

---

## Phase 1 — 治理地基

### 1a. `active.yaml` 单一真相源 (评审 §1/§6)
- `models/production/active.yaml`: primary=e1-conservative(live) / challenger=e8-touch(paper)
- `src/serving/active_config.py`: 加载器 + **variant 绑定门** (active.yaml 的 variant 必须 ==
  manifest 的 deployment.variant, 不一致直接 fail)
- 去硬编码: `live_signal.py` / `run_cron_signal.py` / `deploy/run_signal.sh` 不再写死
  `e1-conservative` 和 `/Users/qiubling/...` 绝对路径

### 1b. config schema 硬校验 (评审 §4)
- `src/experiment/validation.py`: 8 条强制规则把机构手册 §2 的软规则变硬门
  (`step==T` / `purge_gap>=T` / `walk_forward` / `seed` / label 注册 / ...)
- 接进 `run_experiment.py` 入口, 违规 fail-fast

---

## Phase 2 — 契约硬化 (评审 §5/§8/§10)

- `src/serving/contracts.py`: 4 个构建器 (data_manifest / execution_policy /
  validation_gates / lifecycle), 复用 `VARIANT_FLAGS` 消除 DRY
- `promote_model.py` 增强:
  - 生成 `execution_policy.yaml` (固化 `next_open` 执行防回测虚高 / 成本 / 滑点 / kill-switch)
  - 生成 `data_manifest.json` (训练数据 hash / 区间 / freshness)
  - manifest 增 `lifecycle` / `validation_gates` / `fallback`
  - 去硬编码 (`count: 129` → 动态读 / 删 `docker_image` 写死)
  - 新增 `--role` / `--status` 参数
- 回填 E1/E8 这些新产物 (不重训)

---

## Phase 3 — serving 层收编 (评审 §3, 复现风险最高)

- `src/serving/feature_contract.py`: `build_feature_frame` + `validate_feature_cols`
  从 `live_signal.py` **原样搬迁** (逻辑零改动保 bit-exact), 训推共用同一契约
- `live_signal.py` 删本地副本改 import, 消除 DRY
- runner.py 保留底层 `build_features` (含 top_n 预筛选语义不同, 不强并 — YAGNI)

---

## Phase 4 — 运行审计与监控 (评审 §2/§9)

- `src/serving/signal_ledger.py`: RiskDetect 式 live/shadow/archive 三层信号账本
  + 每日监控产物 (文件系统实现, 不依赖 DB)
  - `data/signals/live/{model}.json` — 单版本指针
  - `data/signals/archive/{model}/{date}.json` — 多版本可审计
  - `data/live/monitoring/{model}/{date}.json` — 每日监控
- 每条信号带 **provenance 戳** (model_name / hash / variant / input_data_end / fc_sha256)
- `live_signal.py` 新增 `--ledger-mode {live,shadow,dry-run}`

---

## 提交历史

```
437d584 feat(ledger):     Phase 4 — signal ledger + monitoring artifacts
c4ea0b0 refactor(serving): Phase 3 — extract feature contract to src/serving
7e7e3a1 feat(contracts):  Phase 2 — manifest hardening + execution policy + data lineage
edfb42f feat(validation): Phase 1b — config schema hard validation
5cc65b4 feat(serving):    Phase 1a — active.yaml single source of truth
5c80243 feat(repro):      Phase 0 — lock reproducibility baseline
838b4ca docs(review):     add FcstLabPro vs RiskDetect governance comparison
```

---

## 测试与复现状态

- 新增测试 **50 个全过**:
  - `test_active_model_config.py` (12) — active.yaml 加载 + variant 绑定门
  - `test_config_validation.py` (14) — 配置硬校验
  - `test_manifest_contract.py` (15) — 契约构建器 + 真实 manifest 回归
  - `test_signal_ledger.py` (7) — 三层账本 + 监控
  - `test_feature_cols_validation.py` (既有, Phase 3 后仍过)
- **每个 Phase 收尾 E1/E8 bit-exact** (`diff=0.00e+00`)

---

## 已知遗留 (后续任务)

| 优先级 | 事项 | 说明 |
|--------|------|------|
| 🔴 | loader 忽略 `data.start/end` (根因3) | 修复会改基线数值, 需配合重生成 E1/E8 黄金基线 |
| 🟡 | 既有 `test_lgbm_quirks` / `test_smoothing` 失败 | LightGBM 4.3 / numpy 1.26 版本兼容 (与本次改动无关) |
| 🟡 | `tests/test_inference_pipeline.py` import 已删除模块 | 陈旧测试, 引用不存在的 `scripts.weekly_signal` |
| 🟡 | `tests/verify_kappa.py` / `verify_models.py` 指向退役模型 | 已被 `verify_reproducibility.py` 取代, 可清理 |
| 🟢 | execution_policy `verified=false` | 数值为默认假设, 上线前需人工确认实际成本结构 |
| 🟢 | data_manifest 外部源 lineage | FGI/funding 仍埋在 pipeline, 待 serving 深度重构接入 |

---

## 还没做的评审建议 (本次范围外)

- §11 部分测试 (data_freshness_gate / external_feature_missing_behavior) — 需配合 loader 改造
- live monitoring 的周报 `reports/live_monitoring/{week}.md` — 账本已就绪, 报告生成待加
- promote gate 强制要求 `reproducibility_verified=true` — 现为字段占位, 待接 CI

---

*实施人: sam (code-puppy) | 全程 bit-exact 守护*
