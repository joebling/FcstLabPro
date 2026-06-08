# 模型晋升安全操作规范 (Model Promotion SOP)

**适用范围**: FcstLabPro 所有 `experiments/weekly/*` → `models/production/*` 的模型晋升。
**核心原则**: promote 是生产变更，禁止无审计、无 diff、无显式确认地覆盖生产模型。

---

## 0. 为什么 promote 是危险操作

`promote_model.py` 会写入或覆盖：

```text
models/production/{name}/model.joblib
models/production/{name}/config.yaml
models/production/{name}/manifest.json
models/production/{name}/metrics.json
models/production/{name}/pnl_metrics.json
models/production/{name}/feature_cols.json
models/production/{name}/data_manifest.json
models/production/{name}/execution_policy.yaml
```

这些文件是生产推理实际加载的模型资产。覆盖它们等价于改变线上模型，即使
`active.yaml` 不变，也可能改变 primary/challenger 的实际行为。

所以 promote 不是普通复制文件，而是 **生产模型资产变更**。

---

## 1. 安全晋升的标准阶段

### Stage A — Code Fix / Pipeline Fix

适用于修代码，例如：

- 修 `loader` 的 `data.start/end` 过滤
- 修 feature pipeline
- 修 backtest / PnL 逻辑
- 修 config validation

要求：

1. 单独 commit 代码修复。
2. 不在同一个 commit 中混入生产模型覆盖。
3. 跑单元测试。
4. 如涉及训练/标签/数据边界，必须记录是否会改变 E1/E8 基线。

---

### Stage B — Re-run Experiment

重跑实验只能写入：

```text
experiments/weekly/{new_exp_name}/
```

命名规范：

```text
v{MMDD}_E{N}_{reason}
```

示例：

```text
v0529_E1_endfix
v0529_E8_endfix
```

要求：

1. 使用正式 config 和正式数据路径。
2. 不使用 `_tmp` / `_repro` / 临时数据路径作为生产 config。
3. 若使用 baseline snapshot 做复现，必须在 manifest 中区分：
   - raw data source
   - effective filtered range
4. 输出并检查：
   - `metrics.json`
   - `fold_metrics.csv`
   - `predictions.csv`
   - `feature_cols.json`

---

### Stage C — Re-run PnL / Execution Validation

如果模型要进入 `models/production/`，必须重新生成：

```text
pnl_metrics.json
pnl_report.md
execution_policy.yaml
```

检查项：

- `execution_time = next_open`
- fee/slippage 明确
- target variant 的 PF / MaxDD 过门槛
- signal variant 与 manifest 一致

---

### Stage D — Promotion Dry Run

正式覆盖 production 前必须先 dry-run：

```bash
python scripts/promote_model.py \
  --experiment experiments/weekly/{exp_name} \
  --name {production_name} \
  --variant conservative \
  --role risk_control \
  --status paper \
  --dry-run
```

要求：

- 无 error
- warning 必须逐条解释
- E8 等高 Kappa 模型必须记录为什么不是数据泄露

---

### Stage E — Candidate Review

推荐先生成候选目录，而不是直接覆盖 production：

```text
models/candidates/{production_name}_{exp_name}/
```

Review 内容：

```bash
git diff -- models/production/{name}/
diff old_metrics.json new_metrics.json
```

必须人工检查：

- model hash 是否变化
- metrics delta 是否合理
- PnL delta 是否合理
- `data_manifest.effective_ohlcv` 是否匹配 config 的 `data.start/end`
- `feature_cols_sha256` 是否变化
- active.yaml 是否需要切换

---

### Stage F — Explicit Production Overwrite

只有在 Stage D/E 通过后，才能覆盖 production。

生产覆盖必须显式加确认参数：

```bash
python scripts/promote_model.py \
  --experiment experiments/weekly/{exp_name} \
  --name {production_name} \
  --variant conservative \
  --role risk_control \
  --status live \
  --overwrite-production \
  --confirm-name {production_name}
```

没有这两个参数时，脚本必须拒绝覆盖已有 production 目录。

---

### Stage G — Post-promotion Verification

覆盖后必须立刻执行：

```bash
.venv/bin/python scripts/verify_reproducibility.py
.venv/bin/python -m pytest \
  tests/test_active_model_config.py \
  tests/test_config_validation.py \
  tests/test_manifest_contract.py \
  tests/test_signal_ledger.py \
  tests/test_loader.py -q
```

通过后才能 commit。

---

## 2. 推荐 commit 拆分

禁止把代码修复、实验产物、生产覆盖混成一个大 commit。

推荐拆法：

```text
fix(data): honor experiment data start/end
feat(exp): rerun E1/E8 after data end filtering
promote: refresh e1/e8 production models from v0529 endfix
```

如果只切换 active 模型，再单独：

```text
chore(active): switch primary model to {name}
```

---

## 3. Rollback 规则

回滚优先级：

1. 如果只是切换 active：`git revert active.yaml commit`
2. 如果 production artifact 被覆盖：`git revert promote commit`
3. 如果 code fix 引入问题：再 revert code fix commit

禁止 force-push。

---

## 4. 本次 2026-05-29 loader endfix 的经验教训

修复 `load_csv(start/end)` 会改变 E1/E8 训练样本范围，因此属于生产模型语义变更。
正确流程是：

```text
fix loader
→ 新实验 v0529_E1_endfix / v0529_E8_endfix
→ 重新 PnL
→ dry-run promote
→ 显式确认覆盖 production
→ verify_reproducibility
→ commit
```

这次暴露出原 promote 脚本缺少安全闸门。已要求补上：覆盖已有 production
目录时必须传 `--overwrite-production --confirm-name {name}`。

---

*维护人: FcstLabPro 核心架构组 + sam (code-puppy)*
