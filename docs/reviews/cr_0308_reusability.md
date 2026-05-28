# CR 0308 — FcstLabPro 可复用性与架构合理性分析

Date: 2026-03-08
Scope: 代码可复用性、DRY 违规、架构分层合理性、版本管理

---

## 总体评价

**架构整体设计是合理的。** 三注册表模式（feature/label/model registry）+ YAML 配置继承 + Walk-Forward 回测引擎 + 模型晋升流水线，组成了一条完整的「实验 → 验证 → 晋升 → 部署」链路。

但可复用性存在 **5 个结构性问题**，不是 bug，而是阻碍你未来扩展新模型（E9、E10…）时的效率：

---

## 一、架构分层（做得好的部分）

### ✅ 三注册表统一范式

```
src/features/registry.py  →  @register_feature_set("technical")
src/labels/registry.py    →  @register_label_strategy("directional_filtered")
src/models/registry.py    →  @register_model("lightgbm")
```

三个注册表结构完全一致：装饰器注册 → `get_xxx()` 获取 → `list_xxx()` 枚举。**这是项目最好的设计决策**，因为它让你添加新标签/新特征/新模型时零侵入——写一个文件 + 一行 import 就完事。

### ✅ 配置继承系统

`base.yaml` → 实验 YAML 覆盖 → CLI `--override` 覆盖。三级配置合理且灵活。`_deep_merge()` 实现正确，支持嵌套覆盖。

### ✅ 模型晋升流水线

`promote_model.py` 做了正确的事：
- 自动检查 Kappa/PF/MaxDD 门槛
- 生成 `manifest.json`（模型谱系 + SHA256 哈希 + 检查清单）
- 从实验到 `models/production/` 是 **git-tracked** 的，回滚 = git revert

这个设计确保了「**模型是代码的一部分**」而非脱离版本管理的二进制 blob。非常好。

### ✅ 部署脚本模型无关化

`deploy/deploy.sh` 和 `deploy/docker_entrypoint.sh` 通过 `MODEL_NAME` 环境变量切换模型，不硬编码。这意味着部署 E8 和部署 E1 是同一个脚本 + 不同的环境变量。

```bash
MODEL_NAME=e1-conservative ./deploy/deploy.sh   # E1
MODEL_NAME=e8-touch ./deploy/deploy.sh           # E8
```

### ✅ 信号管道 3 步解耦

```
live_signal.py  →  生成信号 + 更新持仓状态
build_signal_json.py  →  从 state + manifest 组装 JSON（模型无关）
send_signal_email.py  →  JSON → HTML 邮件（纯展示层）
```

每一步只依赖上一步的输出文件，不依赖对方的代码。可以单独测试、单独替换。

---

## 二、可复用性问题（5 个结构性瓶颈）

### 🔴 问题 1: `_calculate_rsi()` / `_calculate_sma()` 复制了 3 份

| 位置 | 代码 |
|------|------|
| `src/labels/directional_filtered.py:26` | `def _calculate_rsi(...)` |
| `src/labels/touch_filtered.py:23` | `def _calculate_rsi(...)` — **完全相同** |
| `src/features/technical.py:45` | RSI 计算逻辑内联在 `build_technical_features()` 中 |

`_calculate_sma()` 也是 2 份。

**影响**: 假如你发现 RSI 计算有 edge case（比如除零），你需要改 3 个地方。

**修复**: 提取到 `src/utils/indicators.py`：
```python
# src/utils/indicators.py
def calculate_rsi(prices: pd.Series, window: int = 14) -> pd.Series: ...
def calculate_sma(prices: pd.Series, window: int) -> pd.Series: ...
```
`features/technical.py` 和 `labels/*_filtered.py` 都从这里 import。

---

### 🔴 问题 2: `get_git_info()` 复制了 2 份

| 位置 | 行数 |
|------|------|
| `src/experiment/tracker.py:46` | 15 行 |
| `scripts/promote_model.py:134` | 15 行 — **完全相同** |

**修复**: `promote_model.py` 直接 `from src.experiment.tracker import get_git_info`。

---

### 🟡 问题 3: `backtest.py` 串行 vs 并行代码重复 ~80 行

`run_walk_forward()` 的串行路径（120-230行）和 `_execute_single_fold()` （346-460行）几乎相同：
- 同样的 purge gap 逻辑
- 同样的 regime weight 逻辑
- 同样的 calibration + threshold optimization
- 同样的 sequence model alignment

**影响**: 改一个行为（比如加一个新的 calibration method）要改两个地方。

**修复**: 串行路径也调用 `_execute_single_fold()`，然后循环收集结果：
```python
def run_walk_forward(...):
    folds = walk_forward_split(...)
    if parallel_workers > 1:
        return _run_parallel(...)
    # 串行 = 顺序调用同一个 fold 执行器
    results = []
    for fold in folds:
        fr = _execute_single_fold(fold, X, y, ...)
        results.append(fr)
    return _aggregate_results(results)
```

---

### 🟡 问题 4: `BaseModel.fit()` 签名与子类不一致

```python
# base.py
def fit(self, X: np.ndarray, y: np.ndarray) -> "BaseModel": ...

# lgbm.py
def fit(self, X, y, sample_weight=None) -> "LightGBMModel": ...
```

`BaseModel` 的 `fit()` 不接受 `sample_weight`，但 `backtest.py` 直接 `model.fit(X, y, sample_weight=sw)` 传了它。这 **依赖了子类的隐式接口而非基类契约**。

如果你写一个新模型（比如 TabPFN），忘了在 `fit()` 里加 `sample_weight` 参数，运行时才会报错。

**修复**: 把 `sample_weight` 加到 `BaseModel.fit()` 签名：
```python
def fit(self, X, y, sample_weight=None) -> "BaseModel": ...
```
或者用 `**kwargs` 让基类更灵活。

---

### 🟡 问题 5: `src/utils/io.py` 写了但没人用

`read_json()` / `write_json()` / `read_yaml()` / `write_yaml()` 已经写好了，但全代码库 **没有一处 import**。反而到处都是：

```python
# promote_model.py
with open(path) as f:
    data = json.load(f)

# tracker.py
with open(path, "w") as f:
    json.dump(data, f, ensure_ascii=False, indent=2, default=str)
```

统计：全项目有 **28 处** 裸 `json.load/dump` + `yaml.safe_load/dump`。

**影响**: 不是功能问题，但如果将来想加统一的错误处理（比如 JSON 解析失败时给出更好的错误信息），改 28 个地方 vs 改 1 个地方。

**修复**: 全局替换为 `from src.utils.io import read_json, write_json`。但这是低优先级的。

---

## 三、版本管理评价

### ✅ 做得好

| 维度 | 评价 |
|------|------|
| **模型版本 = git commit** | `manifest.json` 记录了 `promotion_git.commit`，任何时候都能追溯 |
| **模型哈希** | SHA256 前 16 位，防篡改 |
| **回滚机制** | `git revert` 晋升 commit = 回滚模型。简单直接 |
| **实验可追溯** | `manifest.json.source_experiment` 链接到实验目录 |
| **检查清单** | `manifest.json.checklist` 记录了所有自检项 |

### 🟡 可以更好

| 维度 | 现状 | 建议 |
|------|------|------|
| **实验版本线性** | 实验 ID 用时间戳+hash，不支持 `v1 → v2 → v3` 线性迭代 | 考虑 `overwrite=True` 模式已解决了这个问题，但没有显式的「基于哪个实验迭代」的 parent 字段 |
| **配置变更追踪** | 配置变更只能通过 `git diff config.yaml` 看 | 可在 `manifest.json` 加 `config_diff_from_base` 字段 |
| **标签版本** | 标签策略通过字符串名引用，无版本概念 | 当 `directional_filtered` 的逻辑改了，历史实验的 label 就无法复现。可以给标签策略加 hash |

---

## 四、扩展性分析：加一个新模型需要改几个文件？

假设你要加一个 E9 模型（新标签策略 + 相同特征）：

| 步骤 | 操作 | 文件 |
|------|------|------|
| 1 | 写新标签 | `src/labels/my_new_label.py` (新建) |
| 2 | 注册标签 | `src/labels/__init__.py` + `src/experiment/runner.py` (加 import) |
| 3 | 写实验配置 | `configs/experiments/weekly/exp_e9.yaml` (新建) |
| 4 | 运行实验 | `python scripts/run_experiment.py --config ...` |
| 5 | PnL 回测 | `python scripts/pnl_backtest_v0305.py ...` |
| 6 | 晋升 | `python scripts/promote_model.py ...` |
| 7 | 部署 | `MODEL_NAME=e9-xxx ./deploy/deploy.sh` |

**需要改的文件**: 2 个（`__init__.py` + `runner.py` 加 import 行）
**需要新建的文件**: 2 个（标签 + 配置）

**评价**: **很好**。这是注册表模式的价值——新组件是增量的，不需要改核心逻辑。

**唯一的痛点**: `runner.py` 里有 8 行硬编码的 `import src.labels.xxx`：
```python
import src.labels.reversal  # noqa: F401
import src.labels.directional  # noqa: F401
import src.labels.triple_barrier  # noqa: F401
... (8 行)
```

这违反 OCP（开闭原则）。更好的方式是自动发现：
```python
# runner.py 顶部
import importlib, pkgutil
for _, name, _ in pkgutil.iter_modules(src.labels.__path__):
    importlib.import_module(f"src.labels.{name}")
```

---

## 五、回答原始问题

> 如果我想部署 E1 模型，并把每天预测的结果推送到 QQ 邮箱，当前架构支持吗？

### ✅ 完全支持，且已经在生产运行

当前架构**已经做了这件事**。完整链路：

```
Cloud Run Job (每天 UTC 00:05 触发)
  │
  ├── 1. 下载 Binance BTCUSDT 日线数据
  ├── 2. 从 GCS 恢复持仓状态
  ├── 3. live_signal.py (E1 推理 → BUY/SELL/HOLD/SILENT)
  ├── 4. 上传持仓状态到 GCS
  ├── 5. build_signal_json.py (组装信号 JSON)
  ├── 6. enrich_llm_analysis.py (Gemini AI 解读，可选)
  ├── 7. send_signal_email.py → QQ 邮箱 (SMTP_SSL:465)
  └── 8. 上传信号到 GCS
```

**QQ 邮箱配置已硬编码在 `deploy.sh`**：
```bash
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=792680027@qq.com
SMTP_PASS=mlefgnksjkafbfei
MAIL_TO=792680027@qq.com
```

### 部署 E1 的具体命令

```bash
# 1. 确认模型存在
ls models/production/e1-conservative/

# 2. 一键部署（构建镜像 + 创建 Job + 设置定时）
MODEL_NAME=e1-conservative ./deploy/deploy.sh

# 3. 手动触发一次测试
gcloud run jobs execute daily-btc-signal-e1-conservative --region asia-east1

# 4. 查看日志
gcloud logging read 'resource.labels.job_name="daily-btc-signal-e1-conservative"' --limit=50
```

---

## 六、修复优先级

| 优先级 | 问题 | 工作量 | 影响面 |
|--------|------|--------|--------|
| **高** | RSI/SMA 3 份重复 → 提取到 `utils/indicators.py` | 30 min | 防止未来计算逻辑不一致 |
| **高** | backtest 串行/并行代码重复 → 统一调用 `_execute_single_fold` | 1 hr | 消除最大的 DRY 违规 |
| **中** | `get_git_info()` 2 份 → 复用 tracker 版本 | 5 min | 纯粹的重复 |
| **中** | `BaseModel.fit()` 签名加 `sample_weight` | 10 min | 确保新模型实现的正确性 |
| **低** | `utils/io.py` 没人用 → 逐步替换裸 json/yaml 操作 | 2 hr | 长期可维护性 |
| **低** | runner.py 手动 import 标签 → 自动发现 | 15 min | OCP 原则 |

---

*本报告由 code-puppy-a0947d 生成*
