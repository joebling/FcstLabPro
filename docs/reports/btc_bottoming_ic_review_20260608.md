# BTC 底部 IC 报告 Review 结论

- **被 review 报告**: `docs/reports/btc_bottoming_ic_analysis_20260608.html`
- **关联脚本**: `scripts/research/bottoming_indicator_ic.py`
- **关联结果**: `experiments/research/bottoming_indicator_ic.csv`
- **Review 日期**: 2026-06-08
- **Reviewer**: code-puppy-3e293f

---

## 1. 总体结论

报告中的核心数字本身基本可信：

- HTML 图表/表格中的 90d、180d 超额与命中率，与 `experiments/research/bottoming_indicator_ic.csv` 完全一致。
- 使用 `PYTHONPATH=. python scripts/research/bottoming_indicator_ic.py` 复跑后，CSV 无 diff，结果可复现。
- 脚本方法论整体方向正确：使用 expanding 历史分位避免未来函数，子样本 IC 使用非重叠采样。

但当前报告结论有几处需要降调：

> 最大问题不是数据错，而是报告主结论强依赖日频重叠低估样本。按“低估事件段”去重后，NUPL 和 Reserve Risk 的角色会明显变化。

建议在合并或作为最终研究结论前，至少修复复现命令问题，并软化部分结论。

---

## 2. 已完成的校验

### 2.1 工作区状态

执行：

```bash
git status --short --branch
```

结果显示当前分支为：

```text
research/cycle-bottoming-ic...origin/research/cycle-bottoming-ic
```

Review 过程中未修改既有文件。原先存在的 `CLAUDE.md` 未提交改动保持不变。

### 2.2 脚本复现

直接执行报告中隐含的复现命令：

```bash
python scripts/research/bottoming_indicator_ic.py
```

当前会失败：

```text
ModuleNotFoundError: No module named 'scripts'
```

原因是 `bottoming_indicator_ic.py` 中使用了：

```python
from scripts.research.topping_indicator_ic import (...)
```

但直接执行脚本时项目根目录不一定在 `PYTHONPATH` 中。

使用以下命令可以跑通：

```bash
PYTHONPATH=. python scripts/research/bottoming_indicator_ic.py
```

复跑后 `experiments/research/bottoming_indicator_ic.csv` 没有 diff，说明结果本身稳定。

### 2.3 HTML 手填数据 vs CSV

机器检查 HTML 中的：

```js
const ROWS = [...]
```

与 CSV 中 18 个指标的 90d / 180d 超额和命中率，结果：

```text
HTML rows: 18
CSV indicators: 18
mismatches: 0
```

因此报告图表和表格没有抄错数字。

---

## 3. 数据与数字结论

CSV 与报告一致的核心数字如下：

| 指标 | 180d 命中 | 180d 超额 | 当前报告判断 |
|---|---:|---:|---|
| AVIV | 87% | +53.4% | 强 |
| MVRV-Z | 83% | +47.7% | 强 |
| LTH-NUPL | 84% | +41.1% | 强 |
| NUPL | 81% | +41.1% | 强 |
| Reserve Risk | 82% | +24.7% | 中游 |
| 恐惧贪婪 | 48% | -30.6% | 反向 |
| STH-NUPL | 45% | -15.0% | 反向 |

这些数字均可由脚本复现。

---

## 4. 分析代码 Review

### 4.1 正确之处

#### 4.1.1 未发现明显未来函数

核心逻辑：

```python
pct = expanding_pct(sig)
fwd = price.shift(-h) / price - 1.0
```

`expanding_pct()` 使用 `<= 当日` 的历史数据计算分位，符合 point-in-time 口径，没有使用未来信号计算分位。

#### 4.1.2 子样本 IC 使用非重叠采样

```python
low_no = low.iloc[::h]
```

虽然是在低估子样本中抽样，但至少避免了直接用每日重叠收益计算 t-stat 的问题。

#### 4.1.3 报告中包含必要 caveat

报告 §7 已注明：

> 命中率 / 超额为日频重叠计数，看趋势可以，不能当独立同分布样本下硬结论。

该说明是必要且正确的。

### 4.2 必修问题：复现命令当前失败

当前脚本无法用以下命令直接运行：

```bash
python scripts/research/bottoming_indicator_ic.py
```

建议在 `bottoming_indicator_ic.py` 中，在 import `scripts.research.topping_indicator_ic` 前加入：

```python
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
```

或者在报告中明确复现命令为：

```bash
PYTHONPATH=. python scripts/research/bottoming_indicator_ic.py
```

更推荐修脚本，让报告中的复现方式更稳定。

---

## 5. 最大方法论风险：日频重叠样本

当前主结果基于：

```python
low = df[df["pct"] <= LOW_Q]
hit = float((low["r"] > 0).mean())
avg = float(low["r"].mean())
excess = avg - base_mean
```

这里的 `low` 是所有低估日。BTC 底部低估通常是一大段连续时期，因此 `358 个低估天数` 并不等价于 358 个独立样本。

额外 sanity check：将连续低估日合并为“低估事件段”，分别查看每段首日与末日的 180d 收益。

| 指标 | 低估事件段数 | 段首 180d 命中/均值 | 段末 180d 命中/均值 | 日频低估 180d 命中/均值 |
|---|---:|---:|---:|---:|
| AVIV | 9 | 88.9% / +54.9% | 77.8% / +70.0% | 87.3% / +87.1% |
| MVRV-Z | 6 | 66.7% / +30.8% | 83.3% / +52.7% | 83.0% / +81.5% |
| NUPL | 13 | 38.5% / -1.0% | 46.2% / +8.8% | 80.8% / +74.9% |
| LTH-NUPL | 10 | 80.0% / +14.1% | 90.0% / +40.0% | 84.4% / +74.9% |
| Reserve Risk | 24 | 83.3% / +91.1% | 91.7% / +93.1% | 82.4% / +58.4% |
| 恐惧贪婪 | 95 | 51.6% / +6.5% | 52.6% / +5.9% | 47.9% / +7.8% |
| STH-NUPL | 44 | 45.5% / +1.4% | 50.0% / +11.1% | 44.7% / +18.8% |

该检查不是正式替代方法，但暴露出：

- AVIV 在日频和事件段口径下都较强。
- MVRV-Z 更偏“低估区 + 右侧确认”，首次进入低估区时没那么强。
- NUPL 的强结果高度依赖日频重叠低估样本，事件段口径明显变弱。
- Reserve Risk 在事件段口径下并不弱，当前报告中“退到中游”的结论需要软化。
- 恐惧贪婪和 STH-NUPL 的无效/反向结论较稳。

---

## 6. 逐项结论 Review

### 6.1 AVIV 是底部主力：认可

AVIV 在日频与事件段口径下均较强：

- 日频低估 180d：87.3% 命中，+87.1% 均反弹。
- 事件段首日：88.9% 命中，+54.9%。
- 事件段末日：77.8% 命中，+70.0%。

可以继续作为底部 Layer A 候选。

### 6.2 MVRV-Z 是底部主力：基本认可，但需强调右侧确认

MVRV-Z 日频表现强：

- 83% 命中。
- +47.7% 超额。

但事件段首日表现下降：

- 66.7% 命中。
- +30.8% 均值。

事件段末日则明显更好：

- 83.3% 命中。
- +52.7% 均值。

建议表述为：

> MVRV-Z 是底部主力候选，但 edge 更偏“低估区 + 右侧确认”，不应简单在首次进入低分位时满仓抄底。

### 6.3 LTH-NUPL：适合作确认层

LTH-NUPL 日频表现强：

- 84.4% 命中。
- +41.1% 超额。

事件段口径：

- 段首：80% 命中，但均值只有 +14.1%。
- 段末：90% 命中，均值 +40.0%。

它的命中率稳定，但收益幅度更依赖右侧/后段。适合作为确认信号，不一定适合放在 Layer A 第一梯队。

### 6.4 NUPL：建议从“主力”降级为“确认候选”

当前报告将 NUPL 与 AVIV / MVRV-Z / LTH-NUPL 放在同一组主力指标中。

但事件段 sanity check 下，NUPL 很弱：

- 段首：38.5% 命中，-1.0%。
- 段末：46.2% 命中，+8.8%。
- 日频：80.8% 命中，+74.9%。

这说明 NUPL 的强结果可能高度依赖连续低估区内部的日频重叠权重。

建议改为：

> 底部主力：AVIV / MVRV-Z；确认信号：LTH-NUPL / NUPL / LTH-MVRV。

或者：

> NUPL 在日频条件分位上表现强，但事件去重后稳定性不足，应降为确认信号。

### 6.5 Reserve Risk：“退到中游”结论需要软化

按当前日频超额排名，Reserve Risk 的确不是第一梯队：

- Reserve Risk 180d 超额 +24.7%。
- AVIV +53.4%。
- MVRV-Z +47.7%。

但事件段 sanity check 下，Reserve Risk 仍然很强：

- 24 个低估事件段。
- 段首 180d 命中 83.3%，均值 +91.1%。
- 段末 180d 命中 91.7%，均值 +93.1%。

建议将当前报告中的“Reserve Risk 退位/退到中游”软化为：

> 在日频条件分位超额排名中，Reserve Risk 不再是第一梯队；但事件去重口径下仍可能很强，需进一步用底部事件级/右侧确认回测验证。不能简单判定其“退位”。

### 6.6 恐惧贪婪抄底是伪命题：强烈认可

该结论较稳：

- 日频低估 180d：48% 命中，+7.8% 均值，超额 -30.6%。
- 事件段首日：51.6% 命中，+6.5%。
- 事件段末日：52.6% 命中，+5.9%。

可以保留甚至强化：

> 极恐不是底，极恐只是“市场正在疼”。靠恐惧贪婪左侧抄底没有 edge。

### 6.7 STH 系列反向/无效：认可

以 STH-NUPL 为例：

- 日频 180d 命中 44.7%。
- 事件段首日 45.5%。
- 事件段末日 50.0%。

STH-MVRV / STH-SOPR 在 CSV 中也均为负超额。该结论可以保留。

---

## 7. 报告文字建议修改点

### 7.1 “全样本基线 180d ≈ +33.8%”需要更精确

报告 §3.1 写：

> 全样本基线(+33.8%)

实际基线是按每个指标可用日期分别计算，因此略有差异：

- AVIV：约 +33.7%。
- MVRV-Z：约 +33.8%。
- DXY：约 +35.6%。
- TNX：约 +35.6%。
- 恐惧贪婪：约 +38.4%。
- 资金费率：约 +28.9%。

建议改为：

> 全样本基线按各指标可用样本期分别计算，主流链上指标约 +33.8%。

### 7.2 执行摘要应更明确提示重叠样本风险

建议增加：

> 本报告的 180d 超额/命中率主要用于候选指标排序；正式晋升前需做事件去重与右侧触发回测。

### 7.3 调整核心结论表述

建议将当前核心结论改为：

> 底部 alpha 有迹象存在，但强度应分层。AVIV / MVRV-Z 是更稳的底部 Layer A 候选；LTH-NUPL / NUPL / LTH-MVRV 更适合作确认层。Reserve Risk 在日频条件分位排名中不再第一，但事件口径下仍可能很强，不能简单判定退位。极恐和 STH 系列则是明确避坑项。底部框架必须右侧确认，不能靠首次进入低分位左侧抄底。

---

## 8. 优先级建议

### P0：必须修

1. 修复 `bottoming_indicator_ic.py` 直接运行失败的问题。
2. 报告中复现命令改正确，或脚本内加入项目根目录到 `sys.path`。

### P1：建议修

1. 软化 “Reserve Risk 退位/退到中游” 的表述。
2. 将 NUPL 从“主力”降级为“确认候选 / 日频强但事件口径待验证”。
3. 在执行摘要中加入事件去重与右侧触发回测的 caveat。

### P2：可选增强

新增 robustness CSV / 表格，包含：

- low spell count。
- first-low-day return。
- last-low-day return。
- event-level hit / avg / excess。

并在报告中增加一张“日频 vs 事件段”稳健性对照表。

---

## 9. 最终 Verdict

报告可以作为研究记录保留，但不建议按当前文字直接作为“最终结论版”合并。

综合判断：

- 数据可复现，HTML 数字无错。
- 极恐无效、STH 无效、底部要右侧确认，这些结论较稳。
- AVIV / MVRV-Z 作为底部核心候选，合理。
- NUPL 当前被高估，建议降级。
- Reserve Risk “退中游”表述过强，事件口径下它可能仍很强。
- 复现命令当前失败，必须修。

建议下一步做一个小补丁：

1. 修脚本复现。
2. 调整报告措辞。
3. 加一段事件去重 robustness caveat。

保持小 diff，避免引入不必要的大规模重构。
