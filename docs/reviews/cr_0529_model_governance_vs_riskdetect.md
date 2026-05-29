# 架构与模型版本管理对比评审：FcstLabPro vs RiskDetect

**日期**: 2026-05-29
**评审范围**: 架构分层、模型版本管理、生产治理（**不含 Git 管理规范**）
**对比基线**: `/home/jupyter/qiu/RiskDetect`
**结论一句话**: FcstLabPro 的「研究分层 + Walk-Forward 实验框架」很强，但相比 RiskDetect，
**生产级模型治理 / 切版 / 训推一致性 / 运行审计** 这套制度还没成型——欠的不是算法，是
「让模型从实验变成可长期运营资产」的工程纪律。

> ✅ **实施状态 (2026-05-29)**: 本评审主干已在分支 `feat/model-governance-overhaul` 落地 Phase 0-4。
> 详见 `docs/reviews/cr_0529_implementation_summary.md`。
> 全程守住 E1/E8 bit-exact 复现性 (新增 `scripts/verify_reproducibility.py` 守门员)。
>
> ⚠️ **当前状态**: active.yaml / config validation / feature contract / signal ledger / SOP 已完成；
> external data lineage 与 train-score audit 仍待方案确认。

---

## 总览：原始欠缺清单

> 下面是 2026-05-29 原始评审结论；最新落地状态见后文「实施状态矩阵」。

| 领域 | 评审时 FcstLabPro 状态 | 相比 RiskDetect 欠缺 |
|---|---|---|
| 活跃模型管理 | 靠 `MODEL_NAME` 环境变量 | 缺 `active.yaml` 单一真相源 |
| 模型角色 | E1/E8 靠文档说明 | 缺机器可读 role/lifecycle |
| 切版流程 | promote + deploy | 缺 shadow/live/archive 流程 |
| 训推一致性 | 有 `feature_cols.json` | 缺完整 schema/data contract |
| 配置校验 | YAML merge 为主 | 缺强类型 config validation |
| Promotion gate | Kappa/PF/MDD | 缺 IC、执行假设、shadow、审计 gate |
| 数据 lineage | data path 为主 | 缺数据 hash、外部源版本、freshness |
| 生产脚本 | 多脚本拼装 | 缺统一 serving 层 |
| 监控 | 文档建议 | 缺每日 drift/score/signal 产物 |
| 审计材料 | manifest/report | 缺 train-score audit 标准件 |
| 执行层 | PnL 有但假设不硬 | 缺 execution policy 合同 |

---

## 实施状态矩阵 (2026-05-29)

| # | 领域 | 状态 | 当前实现 | 待完成 |
|---|---|---|---|---|
| 1 | active.yaml | ✅ 完成 | `active_config.py` | 持续维护 |
| 2 | shadow/live/archive | ✅ 基础完成 | `signal_ledger.py` | 云端持久化待定 |
| 3 | 训推一致性 | 🟡 部分 | `feature_contract.py` | audit 脚本待定 |
| 4 | 配置校验 | ✅ 完成 | `validation.py` | 可补 hypothesis |
| 5 | promotion gate | 🟡 部分 | 安全覆盖闸门 | IC/shadow gate 待定 |
| 6 | 模型角色生命周期 | ✅ 基础完成 | `active.yaml` + manifest | 状态流转自动化待定 |
| 7 | serving 层 | 🟡 部分 | serving 模块已起步 | `live_signal.py` 仍偏胖 |
| 8 | 数据 lineage | 🟡 部分 | raw/effective OHLCV | 外部源 lineage 待定 |
| 9 | monitoring/drift | 🟡 部分 | monitoring JSON | drift/weekly report 待定 |
| 10 | execution policy | ✅ 基础完成 | `execution_policy.yaml` | verified gate 待定 |
| 11 | 事故防护测试 | 🟡 部分 | 新增多组测试 | freshness/audit 待定 |

### 已完成主干

- `models/production/active.yaml` 成为生产模型真相源。
- `src/serving/active_config.py` 绑定 model slot / role / variant。
- `src/experiment/validation.py` 强制 Non-overlap 与 Walk-Forward。
- `src/serving/feature_contract.py` 收编 serving feature 校验。
- `src/serving/contracts.py` 生成 data / execution / lifecycle 合同。
- `src/serving/signal_ledger.py` 提供 live / shadow / archive 账本。
- `scripts/promote_model.py` 增加覆盖生产安全闸门。
- `docs/ops/experiment_sop.md` 与 `model_promotion_sop.md` 已补齐。

### 暂缓项

以下两项需要进一步确认方案后再做，不在本次更新范围内：

- **B. external data lineage**: FGI / funding / macro 的 hash、freshness、fallback。
- **C. train-score audit**: 正式审计脚本与 promotion gate 接入。

---

## 1. 缺少 `active.yaml` 这类「生产模型唯一真相源」

RiskDetect 有 `models/production/active.yaml`，明确写：当前 live 模型、业务段
（`wb` / `unified`）、`artifact_dir`、是否 Platt 校准、上线原因、回滚方案、数据依赖、
训推一致性审计结果、promotion plan 链接。

FcstLabPro 现状：
- 部署靠 `MODEL_NAME=e1-conservative`
- `live_signal.py` 默认硬编码 `e1-conservative`
- 部分脚本硬编码 `e1-conservative` / `e8-touch`
- `STRATEGY_VARIANT` 与 manifest 的 variant 可能不一致

```python
# scripts/live_signal.py
DEFAULT_MODEL = PROJECT_ROOT / "models/production/e1-conservative/model.joblib"
DEFAULT_CONFIG = PROJECT_ROOT / "models/production/e1-conservative/config.yaml"
```

```bash
# deploy/docker_entrypoint.sh
MODEL_NAME="${MODEL_NAME:?ERROR: MODEL_NAME 未设置}"
STRATEGY_VARIANT="${STRATEGY_VARIANT:-conservative}"
```

**欠缺**：没有统一的生产切版入口，例如：

```yaml
active:
  primary:
    artifact_dir: models/production/e1-conservative
    role: conservative
    strategy_variant: conservative
  challenger:
    artifact_dir: models/production/e8-touch
    mode: paper
```

**风险**：`MODEL_NAME=e8-touch STRATEGY_VARIANT=base` 不一定被阻止——模型标签、策略变体、
部署用途之间没有硬绑定。

---

## 2. 缺少正式的 Shadow / Live / Archive 版本运行模式

RiskDetect 生产打分有明确三模式：

```text
--dry-run   不写库
--shadow    写 archive，不动 live
--live      写 live + archive
```

并有：

```text
seller_risk_scores          live 单版本
seller_risk_scores_archive  多版本 + shadow/live 并存（PK 含 model_version）
```

价值：新模型先 shadow 跑 → 同日对比旧模型 → live 单版本 → archive 多版本审计 → 可回溯切换影响。

FcstLabPro 现状：有 `--dry-run`、paper trading、signal JSON、state 文件、GCS 上传，但没有正式的
信号版本账本（live / shadow / archive + model_version + score_source）。

**建议**：本地/云端统一的信号归档结构：

```text
data/live/signals/current.json
data/archive/signals/{model_name}/{date}.json
data/shadow/signals/{model_name}/{date}.json
```

每条信号带：

```json
{
  "model_name": "e1-conservative",
  "model_hash": "...",
  "strategy_variant": "conservative",
  "score_source": "live",
  "generated_at": "...",
  "input_data_end": "...",
  "feature_cols_sha256": "..."
}
```

---

## 3. 训推一致性治理比 RiskDetect 弱

FcstLabPro 的优点（要表扬）：有 `feature_cols.json`，`live_signal.py::validate_feature_cols()`
会校验列顺序。

RiskDetect 更系统：config 显式列出 `features.columns`；推理按 config 列顺序取特征；训练/推理共用
`build_wide_table.py`；`src/serving.py` 抽出 dtype / category 对齐；有
`train_score_consistency_audit.md`；测试覆盖缺失特征、类别截断、dtype 对齐、PIT 快照完整性。

FcstLabPro 现状：训练侧靠 `feature_sets` 展开，推理侧重新 build features，再靠 `feature_cols.json`
挡最后一刀——是「列顺序安全带」，不是完整的训推一致性治理。

**欠缺**：
1. 显式 feature schema version
2. 训练/推理共同的 feature contract
3. 数据源完整性 hard-fail
4. train-score consistency audit 成为 promotion 必需项
5. 类别/缺失值/外部数据 fallback 的统一 serving 层

**理想结构**：

```text
src/serving/
  feature_contract.py
  model_loader.py
  signal_engine.py
  schema_checks.py
```

生产推理统一走：

```python
contract = FeatureContract.load(model_dir)
X = contract.build_and_validate(raw_df)
```

---

## 4. 配置校验不够硬

RiskDetect 的 `src/config.py` 有 dataclass `Config` + `_validate()`：校验 mode、algorithm、
`features.columns` 必须存在且类型正确，并有 `tests/test_config_validation.py`。

FcstLabPro 的 `src/experiment/config.py` 主要是 load / merge / override / save，无强 schema 校验。

**欠缺**（应强制）：

```yaml
label.T == evaluation.step
evaluation.purge_gap >= label.T
evaluation.method == walk_forward
data.path exists
model.type in registry
features.sets all registered
label.strategy in registry
seed exists
```

机构手册写了 Non-overlapping 强制 / Walk-Forward 强制 / 禁止 train-oncredict-all，但目前多是
「文档要求」而非「代码硬门」。

**建议**：上 Pydantic / dataclass validation：

```python
class ExperimentConfig(BaseModel):
    @model_validator(mode="after")
    def validate_non_overlap(self):
        if self.evaluation.step != self.label.T:
            raise ValueError("evaluation.step must equal label.T")
        return self
```

---

## 5. Promotion gate 太基础

FcstLabPro 的 `promote_model.py` 已有：实验状态检查、必要文件检查、Kappa / PF / MaxDD 门槛、
manifest 生成、model hash（这是好东西）。

RiskDetect 更完整：每版本有 promotion plan、train-score consistency audit、shadow 验证、数据依赖检查、
fallback 模型说明、分段适用范围、阈值方案、监控与回滚、业务风险解释。

**建议补充 manifest 字段**：

```json
{
  "role": "primary | challenger | retired",
  "active_from": "date",
  "active_until": null,
  "compatible_strategy_variants": ["conservative"],
  "default_strategy_variant": "conservative",
  "data_contract": {
    "raw_data_path": "...",
    "raw_data_sha256": "...",
    "external_sources": ["fgi", "funding_rate"],
    "required_freshness_days": 1
  },
  "validation_gates": {
    "ic_analysis_passed": true,
    "non_overlapping_confirmed": true,
    "walk_forward_confirmed": true,
    "cost_model_confirmed": true,
    "train_serve_audit_passed": true
  },
  "fallback": {
    "model_name": "e1-conservative",
    "trigger": "feature_schema_mismatch or data_stale"
  },
  "monitoring": {
    "expected_signal_rate": "...",
    "expected_exposure": "...",
    "probability_distribution_ref": "..."
  }
}
```

当前 checklist 有 `python_version` / `pnl_backtested`，但缺更关键的交易系统 gate（IC、执行假设、shadow、审计）。

---

## 6. 缺少明确的模型角色与生命周期

RiskDetect 明确区分 `wb` / `unified` 两个 section，并反复强调「两个模型不可互换」。

FcstLabPro 有 `e1-conservative` / `e8-touch`，但角色（E1 风控优先 / E8 收益优先 / E16b SOTA 候选）
主要写在 README / SUMMARY 里。

**欠缺**：机器可读的模型角色与生命周期：

```yaml
models:
  primary:
    name: e1-conservative
    purpose: risk_control
  secondary:
    name: e8-touch
    purpose: return_enhancement
  candidate:
    name: e16b-savgol-close
    status: offline_only
```

```text
lifecycle: candidate → shadow → paper → live → deprecated → archived
```

目前这些状态靠文档和人脑维护。

---

## 7. 生产脚本仍有「研究脚本味道」

RiskDetect 生产主链路集中在 `scripts/unified_pipeline/` + `src/serving.py` + `src/utils/pg_io.py`。

FcstLabPro 生产链路分散：`live_signal.py`、`build_signal_json.py`、`send_signal_email.py`、
`run_cron_signal.py`、`deploy/docker_entrypoint.sh`、`deploy/run_signal.sh`，以及
paper trading / consensus / sensitivity 脚本。

并且 `scripts/run_cron_signal.py` 有本地绝对路径：

```python
PROJECT_ROOT = Path("/Users/qiubling/Desktop/projects/FcstLabPro")
venv_python = "/Users/qiubling/Desktop/projects/FcstLabPro/venv_py310/bin/python"
```

**欠缺**：生产入口尚未抽象为稳定模块：

```text
src/serving/
  loader.py
  feature_pipeline.py
  signal_policy.py
  state_store.py
  output_writer.py
```

**风险**：本地与云端行为漂移；部分脚本绕过 manifest / 硬编码模型名 / 硬编码路径；
variant 与 manifest 无统一约束。

---

## 8. 数据版本与外部数据 lineage 不如 RiskDetect 明确

RiskDetect 强调 snapshot date、schema version、source completeness、PIT snapshot、backfill source、
数据链路 runbook；`score.py` 有 `_assert_snapshot_complete()`，缺数据 hard-fail。

FcstLabPro 数据配置以 `data.path` 为主，外部数据（FGI / 资金费率 / 宏观）在 feature pipeline 内部处理。

**欠缺**：生产 manifest 未强记录训练数据 hash、外部数据源版本、FGI 缓存截止、funding/macro 区间、
freshness SLA、数据缺失时 fail 还是 fallback。

**建议**：每次实验/promotion 保存 `data_manifest.json`：

```json
{
  "raw_ohlcv": {
    "path": "data/raw/btc_binance_BTCUSDT_1d.csv",
    "start": "2018-01-01",
    "end": "2026-03-01",
    "sha256": "..."
  },
  "external_sources": {
    "fgi": { "rows": 1234, "last_date": "2026-03-01", "sha256": "..." }
  }
}
```

---

## 9. 缺少正式的 live monitoring / drift / explainability 产物

RiskDetect 有 scored features dump、SHAP background、SHAP explain、PSI/drift 计划与测试、bad case 分析、
线上分数分布查询、archive 表对比。

FcstLabPro 的 `models/production/SUMMARY.md` 有监控建议（signals/day、exposure、rolling win-rate、
live MaxDD、概率漂移），但更像「建议」而非系统产物。

**建议**：每日产物 `data/live/monitoring/{model}/{date}.json`：

```json
{
  "n_rows": 2300,
  "data_last_date": "2026-05-28",
  "signal": "BUY",
  "probability": 0.63,
  "prob_mean_rolling_30d": 0.42,
  "feature_missing_rate": {},
  "feature_drift": {},
  "state": {},
  "pnl_since_live": {}
}
```

以及每周 `reports/live_monitoring/{week}.md`。

---

## 10. 回测执行假设尚未进入模型治理

`models/production/SUMMARY.md` 已自陈：手续费/滑点、资金费率/借贷、信号执行价「未在本报告披露」。
对交易系统而言，这些是 Layer 5 的核心合同。

**欠缺**：Promotion gate 应要求成本模型、滑点模型、执行延迟（`t close signal → t+1 open execute`）、
funding 计入方式、spot/perp、position sizing / vol targeting、max exposure / drawdown kill-switch。

**建议**：生产模型目录强制有 `execution_policy.yaml`：

```yaml
execution:
  signal_time: daily_close
  execution_time: next_open
  fee_bps: 10
  slippage_bps: 5
  instrument: spot
  max_position: 1.0
  vol_target: null
  kill_switch:
    max_live_drawdown: 0.15
```

---

## 11. 测试覆盖方向不同：FcstLabPro 偏实验，RiskDetect 偏生产事故防护

FcstLabPro 测试：feature cols validation、inference pipeline、labels、models、smoothing、kappa
verification、production model verification。

RiskDetect 测试更「事故驱动」：PIT snapshot、missing feature safety、bad cases、schema validation、
SHAP、active WB metrics、data fetch labels、duplication bug、score upsert dtype。

**建议补充测试**：

```text
test_active_model_config.py
test_manifest_contract.py
test_strategy_variant_compatible.py        # MODEL_NAME 与 STRATEGY_VARIANT 必须兼容
test_promote_requires_ic_analysis.py
test_promote_requires_execution_policy.py
test_live_signal_archive_schema.py
test_data_freshness_gate.py
test_external_feature_missing_behavior.py
```

---

## 优先级建议（Top 5）

### P0 — 加 `models/production/active.yaml`（生产唯一真相源）

```yaml
primary:
  artifact_dir: models/production/e1-conservative
  role: risk_control
  strategy_variant: conservative
  status: live

challenger:
  artifact_dir: models/production/e8-touch
  role: return_enhancement
  strategy_variant: conservative
  status: paper
```

`deploy.sh` / `live_signal.py` 一律从它读，不再到处硬编码。

### P0 — 让 manifest 约束 strategy variant

启动时校验 `requested variant == manifest.deployment.variant`，否则直接 fail。

### P1 — 加 config schema validation

强制 `evaluation.step == label.T`、`purge_gap >= label.T`、`method == walk_forward`、`seed` 存在、
model/label/feature sets 已注册——把「研究规范靠自觉」变成代码门禁。

### P1 — 补 `execution_policy.yaml`

把成本、滑点、执行延迟写成模型产物，而非只在报告里口头描述。

### P1 — 加 shadow/archive 信号记录

即使不用数据库，先用文件系统：

```text
data/signals/live/
data/signals/shadow/
data/signals/archive/
```

每条 signal 必须带模型版本、hash、variant、输入数据日期。

---

## 结语

FcstLabPro 是一个不错的机构级研究框架雏形，但 RiskDetect 已更像「线上模型产品」。
当前项目最欠缺的不是模型算法，而是 **active model governance、切版审计、训推契约、shadow 运行、
执行层合同**。研究部分像量化实验室，生产治理还像「聪明脚本帮派」——该收编成正规军了。

---

*评审人: sam (code-puppy) | 来源: FcstLabPro vs RiskDetect 静态代码对比*
