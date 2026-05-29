# 实验执行安全操作规范 (Experiment SOP)

**适用范围**: FcstLabPro 所有研究实验，尤其是 `configs/experiments/weekly/*` → `experiments/weekly/*` 的训练、PnL、IC、review 与实验结果提交。

**边界说明**: 本 SOP 只覆盖实验流程。任何 `experiments/*` → `models/production/*` 的操作必须转到 [`model_promotion_sop.md`](model_promotion_sop.md)。

---

## 0. 核心原则

1. **实验不是生产**: 实验目录可以反复迭代，production 目录不能顺手覆盖。
2. **配置即契约**: config 写了什么，代码必须真实执行什么。
3. **先验证再改动**: 改训练、标签、数据边界前后都要跑复现守门。
4. **代码修复和实验结果分开提交**: 不要把 bug fix、实验产物、production promote 混在一个 commit。
5. **没有 review 的实验不能 promote**: 实验通过 review 后才能进入 promotion SOP。

---

## 1. 标准阶段

```text
Stage 0  复现守门
Stage 1  假设定义
Stage 2  配置创建
Stage 3  训练实验
Stage 4  PnL 回测
Stage 5  IC / 统计验证
Stage 6  Review package
Stage 7  实验提交
Stage 8  Optional promotion handoff
```

---

## Stage 0 — 复现守门

### 何时必须跑

以下情况必须先跑：

- 修改 `src/data/*`
- 修改 `src/features/*`
- 修改 `src/labels/*`
- 修改 `src/evaluation/*`
- 修改 `src/experiment/*`
- 修改模型训练逻辑
- 修改依赖版本
- 修改生产模型 config
- 准备重跑 E1/E8 基线

### 标准命令

```bash
.venv/bin/python scripts/verify_reproducibility.py
```

通过标准：

```text
E1/E8 全指标 diff=0.00e+00
```

如果失败：

1. 停止实验。
2. 查明是代码变化、数据变化还是环境变化。
3. 不要继续跑新实验假装没看见，小狗会记仇。

---

## Stage 1 — 假设定义

每个实验必须先定义假设。不要“调一下看看”，那是过拟合的亲戚。

推荐写入 config：

```yaml
experiment:
  name: v0530_E17_example
  description: "验证某 Alpha 在 bear regime 下的稳定性"
  hypothesis: >-
    某特征在非重叠 21D 标签上应提高 precision，
    且不会显著提高 MaxDD。
  tags:
    - weekly
    - bear
    - hypothesis_x
  category: weekly
```

目前 `hypothesis` 不是强制字段，但新实验建议补上。后续可在 config validation 中强制。

---

## Stage 2 — 配置创建

### 命名规范

Config name 格式：

```text
v{MMDD}_E{N}_{reason}
```

示例：

```text
v0529_E1_endfix
v0529_E8_endfix
v0530_E17_fgi_ablation
```

配置路径：

```text
configs/experiments/weekly/exp_weekly_bear_{name}.yaml
```

实验输出路径：

```text
experiments/weekly/{name}/
```

### 必须满足的硬规则

这些规则已由 `src/experiment/validation.py` 校验：

| 规则 | 要求 |
|---|---|
| Non-overlap | `evaluation.step == label.T` |
| Purge gap | `purge_gap >= label.T` |
| OOS 方法 | `method == walk_forward` |
| Seed | 必须存在 |
| Label | strategy 必须注册 |
| Model | `model.type` 必须存在 |
| Data | `data.path` 必须存在 |
| Features | `features.sets` 非空 |

### 数据边界

config 中必须明确：

```yaml
data:
  path: data/raw/btc_binance_BTCUSDT_1d.csv
  start: '2018-01-01'
  end: '2025-12-31'
```

注意：

- `load_csv()` 现在会真实执行 `start/end`。
- PnL 回测也必须使用同一数据窗口。
- 如果改 `data.end`，就是实验语义变化。

---

## Stage 3 — 训练实验

### 标准命令

```bash
.venv/bin/python scripts/run_experiment.py \
  --config configs/experiments/weekly/{config}.yaml \
  --overwrite
```

如果临时 override：

```bash
.venv/bin/python scripts/run_experiment.py \
  --config configs/experiments/weekly/{config}.yaml \
  --override experiment.name=v0530_E17_test \
  --overwrite
```

### 禁止事项

- 禁止用 `_tmp` / `_repro` 名称提交正式实验。
- 禁止用临时数据路径写入最终 config。
- 禁止在同一实验名上反复覆盖后不记录原因。
- 禁止 train-once-predict-all 伪 OOS。

### 训练后必须检查的产物

```text
config.yaml
meta.json
metrics.json
fold_metrics.csv
feature_cols.json
feature_importance.csv
report.md
```

如果缺少以上关键产物，不算完整实验。

---

## Stage 4 — PnL 回测

### 标准命令

```bash
.venv/bin/python scripts/pnl_backtest_v0305.py \
  --experiment experiments/weekly/{exp_name} \
  --data data/raw/btc_binance_BTCUSDT_1d.csv \
  --regime-switch
```

### 输出产物

```text
pnl_metrics.json
pnl_report.md
equity_*.csv
```

### 必查指标

| 指标 | 说明 |
|---|---|
| Total Return | 总收益 |
| CAGR | 年化收益 |
| Sharpe | 风险调整收益 |
| MaxDD | 最大回撤 |
| Profit Factor | 盈亏比 |
| Exposure | 暴露比例 |

### 执行假设

PnL review 中必须确认：

- 是否使用 `next_open` 执行假设
- fee/slippage 是否明确
- 是否启用 regime switch
- 是否启用 take-profit
- target variant 是哪个

当前 production 常用目标：

```text
策略(止盈+regime)
```

---

## Stage 5 — IC / 统计验证

如果实验属于 alpha / label / feature 研究，必须跑 IC 或说明为什么不跑。

标准命令示例：

```bash
.venv/bin/python scripts/ic_analysis_corrected.py \
  --bull-dir experiments/weekly/{exp_name}
```

注意：当前参数名 `--bull-dir` 历史包袱较重，后续可单独清理。不要在实验中途顺手大改脚本接口，别把小修变成开荒。

### 统计 review 要点

| 项目 | 要求 |
|---|---|
| Rank IC | 说明方向和稳定性 |
| IC t-stat | 基于 IC 时间序列 |
| Fold 稳定性 | 查看 `fold_metrics.csv` |
| 高指标审计 | Kappa/Sharpe 过高需查泄露 |

---

## Stage 6 — Review package

一个可 review 的实验目录至少应包含：

```text
config.yaml
meta.json
metrics.json
fold_metrics.csv
feature_cols.json
feature_importance.csv
report.md
pnl_metrics.json
pnl_report.md
equity_*.csv
```

### 推荐 review 命令

查看实验：

```bash
.venv/bin/python scripts/manage_experiments.py show {exp_name}
```

对比实验：

```bash
.venv/bin/python scripts/compare_experiments.py \
  --ids {old_exp} {new_exp}
```

### Review checklist

- [ ] config 与实验假设一致
- [ ] `step == T`
- [ ] `purge_gap >= T`
- [ ] 数据窗口符合预期
- [ ] feature_cols hash 合理
- [ ] 分类指标变化可解释
- [ ] PnL 指标变化可解释
- [ ] Exposure 没有异常上升
- [ ] 最新信号差异已检查
- [ ] 无 production 文件改动

---

## Stage 7 — 实验提交

### 什么时候提交

可以提交：

- 实验有明确结论
- 实验需要供他人 review
- 实验是 promotion candidate
- 实验修复了重要基线问题

暂不提交：

- 快速调参中间产物
- 明显失败且无分析价值
- 临时 `_tmp` / `_repro` 目录

### 标准 commit

```bash
git add experiments/weekly/{exp_name}/ experiments/registry.json

git commit -m "feat(exp): add {exp_name} experiment record"
```

### 禁止混入

实验 commit 不应包含：

```text
models/production/*
active.yaml 切换
promote_model.py 大改
无关代码重构
```

除非 commit message 明确说明并经过 review。一般别这么干，DRY 不是乱炖。

---

## Stage 8 — Optional promotion handoff

实验 review 通过后，如果考虑进入 production，停止使用本 SOP，转到：

```text
docs/ops/model_promotion_sop.md
```

promotion 前至少要有：

```text
metrics.json
pnl_metrics.json
feature_cols.json
feature_importance.csv
config.yaml
meta.json
review 结论
```

正式覆盖 production 必须使用：

```bash
--overwrite-production --confirm-name {name}
```

没有显式确认，`promote_model.py` 会拒绝覆盖。

---

## 9. 推荐 commit 拆分

### 场景 A：纯代码修复

```text
fix(data): honor experiment data start/end
```

### 场景 B：实验重跑

```text
feat(exp): add v0529 E1/E8 end-filter records
```

### 场景 C：实验 review 文档

```text
docs(exp): add production vs candidate review
```

### 场景 D：production 晋升

```text
promote: refresh e1-conservative from v0529_E1_endfix
```

四类 commit 尽量分开。Git 历史要像实验室台面，不要像被哈士奇翻过的垃圾桶。

---

## 10. 常见坑

### 10.1 Config 写了但代码没用

典型例子：旧 `load_csv()` 曾忽略 `data.start/end`。

防线：

- config validation
- loader 测试
- review data window 日志

### 10.2 PnL 与训练数据窗口不一致

训练用了 `end=2025-12-31`，PnL 却读完整 CSV，会导致样本错位。

防线：

- PnL 脚本必须读取实验 config 的 `data.start/end`
- PnL 日志必须检查数据范围

### 10.3 临时路径写进 config

例如：

```yaml
path: data/raw/_repro_baseline.csv
```

这种不能进入正式实验或 production config。

### 10.4 指标小变但信号大变

即使 Kappa 只变 0.005，最新信号也可能从 `SILENT` 变 `BUY`。

防线：

- review 最新 live_signal 对比
- 候选模型先 shadow

### 10.5 实验 commit 混入 production

这是最危险的混乱。

防线：

```bash
git status --short
```

确认没有：

```text
models/production/*
```

---

## 11. v0529 endfix 案例模板

`v0529_E1_endfix` / `v0529_E8_endfix` 是标准案例：

```text
Stage A: 修 load_csv(start/end)
Stage B: 重跑 E1/E8
Stage C: 重跑 PnL
Stage D: 写 production diff review
Stage E: 不直接 promote，先 review/shadow
```

关键结论：

```text
实验只改变了 data boundary contract，
没有改模型参数、特征、标签或 walk-forward 设置。
```

---

## 12. 最小命令模板

```bash
# 0. 守门
.venv/bin/python scripts/verify_reproducibility.py

# 1. 训练
.venv/bin/python scripts/run_experiment.py \
  --config configs/experiments/weekly/{config}.yaml \
  --overwrite

# 2. PnL
.venv/bin/python scripts/pnl_backtest_v0305.py \
  --experiment experiments/weekly/{exp_name} \
  --data data/raw/btc_binance_BTCUSDT_1d.csv \
  --regime-switch

# 3. 查看
.venv/bin/python scripts/manage_experiments.py show {exp_name}

# 4. 提交实验
git add experiments/weekly/{exp_name}/ experiments/registry.json
git commit -m "feat(exp): add {exp_name} experiment record"
```

---

*维护人: FcstLabPro 核心架构组 + sam (code-puppy)*
