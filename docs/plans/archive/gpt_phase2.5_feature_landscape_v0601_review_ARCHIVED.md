# ⚠️ ARCHIVED — GPT Review 已全量采纳, 使命完成

> **归档时间**: 2026-06-01
> **归档原因**: 本 review 提出的 4 个 P0/P1 建议 + 2 个措辞建议 + audit 脚本修复
>             已全部固化进主文档 + 代码 (见 commit 链).
> **追加发现** (复审时由 sam 验证): BGeo 全部 68 个 `*_btc_price.json` 文件都是 BTC 价格副轴,
>             不只 mvrv_btc_price. 已在主文档 §3 升级为铁律.
> **现行位置**: `docs/plans/phase2.5_feature_landscape_v0601.md` (主文档, 已含 GPT 7/7 patch)
> **保留价值**:
>   - 高质量 review 范本 (评论 + 实际改代码 + 跑 audit 闭环)
>   - 抓出 3 个真 bug: L1 阈值 / mvrv_btc_price 数据泄漏 / Layer 0 无 shift(1)
>   - 验收评分 9.5/10 (自评 8/10 偏谦虚)
>
> **如需引用后续 work**: 请以 `phase2.5_feature_landscape_v0601.md` 为准, 本文仅作历史证据.

---

# GPT Review: Phase 2.5 Feature Landscape v0601

> **Review target**: `docs/plans/phase2.5_feature_landscape_v0601.md`  
> **Review focus**: 数据源、Layer 0 数据治理、候选指标可用性、实验公平性  
> **Reviewer**: GPT / sam  
> **Date**: 2026-06-01

---

## 0. Executive Summary

`phase2.5_feature_landscape_v0601.md` 的大方向是成立的：

- BGeo 的长历史链上指标确实是 Phase 2.5 的主要 alpha 搜索空间。
- CMD 更适合作为短历史衍生品/交易行为数据源。
- 2020-01-01 到 2025-12-31 的基准窗口锁定是必要且正确的。
- 慢变量必须做 short-horizon transform，这条纪律非常重要。

但在 Wave 2 正式开跑前，建议补齐几个 **P0 数据治理约束**：

1. 所有 external/onchain 日频特征默认应 `shift(1)`，除非能证明当日决策时点已可用。
2. `E19-DERIV-SHORT` 不应直接和 2020 起 E1 baseline 比较，应使用 2022-12-03 起同窗 baseline。
3. `mvrv_btc_price` 不建议作为 MVRV alpha 特征，应仅用于 QA/对齐校验。
4. 文档中 “L1 + ffill_then_drop 不丢行” 的表述需要收敛，rolling 派生仍会自然丢前置样本。
5. 原 `audit_bgeo_nan.py` 与 plan 不一致，已修正并重跑生成完整 audit 结果。

---

## 1. 已验证且正确的关键事实

### 1.1 BTC 基准数据

实测结果：

```text
BTC csv sha256:
004bf0706559e0a79a4361c9a0db27d5acb07d72556499df0e081879017c7858

raw rows:
3074, 2018-01-01 ~ 2026-06-01

effective rows under 2020-2025 baseline:
2192, 2020-01-01 ~ 2025-12-31
```

结论：文档 §3 中的 `expected_sha256` 与 `expected_effective_rows: 2192` 是正确的。

### 1.2 BGeo 总体画像

实测结果：

```text
BGeo JSON files: 437
Parseable JSON: 419
```

起始年份分布与文档一致：

| 起始年份 | 实测指标数 |
|---|---:|
| ≤2012 | 239 |
| 2013-2014 | 78 |
| 2015-2017 | 21 |
| 2018-2020 | 23 |
| 2021-2022 | 26 |
| 2023+ | 32 |

结论：BGeo 作为 Phase 2.5 主战场的定位成立。

### 1.3 CMD 数据源画像

`/home/jupyter/qiu/github/crypto-market-data/data/daily` 实测：

```text
29 JSON
schema: dict with data list
主要从 2022-12-03 开始
```

结论：CMD 更适合短历史衍生品与交易行为特征，不适合作为长历史链上主源。

---

## 2. 已修正的支撑脚本问题

### 2.1 原问题：audit 候选清单未覆盖 plan

原 `scripts/audit_bgeo_nan.py` 只覆盖：

- `E19-PUELL`
- `E19-MINER`
- `E19-MVRV-EXT` 部分指标
- `E19-STABLE` 部分指标

但 plan 中的实际 sub-experiments 包括：

- `E19-PUELL`
- `E19-SOPR-NEW`
- `E19-MVRV-EXT`
- `E19-ADDRESS`
- `E19-STABLE`
- `E19-AVIV`
- `E19-DERIV-SHORT`

这导致 plan 里部分 “L1: coverage/stale” 结论没有持久化证据。

### 2.2 原问题：L1/L2 分类逻辑与文档不一致

原脚本逻辑近似为：

```python
if coverage >= 0.70:
    return "L1"
```

这与 plan 中定义冲突：

```text
L1: coverage >= 95%, stale <= 90d
L2: coverage 70%-95%, stale <= 90d
L3: stale > 90d 或 coverage < 70%
```

### 2.3 已完成修正

已修改：

- `scripts/audit_bgeo_nan.py`
- `data/external/onchain/nan_audit.json`

验证命令：

```bash
python scripts/audit_bgeo_nan.py
python -m py_compile scripts/audit_bgeo_nan.py
```

结果：均通过。

---

## 3. 重跑 audit 后的数据结论

### 3.1 L1 候选确认

重跑后确认以下 sub 的核心候选指标为 L1：

| Sub | 结论 |
|---|---|
| E19-PUELL | L1 |
| E19-SOPR-NEW | 全部 L1 |
| E19-MVRV-EXT | 核心 5 个 L1 |
| E19-ADDRESS | 全部 L1 |
| E19-STABLE | 5 个主稳定币 L1 |
| E19-AVIV | L1 |

关键实测值：

```text
puell_multiple_data:
coverage 99.54%, NaN 10, stale 2d

sopr_data:
coverage 99.54%, NaN 10, stale 2d

lth_sopr / sth_sopr:
coverage 99.32%, NaN 15, stale 2d

mvrv core:
coverage 99.54%, NaN 10, stale 2d

address buckets:
coverage 99.09%-99.18%, stale 36d

stablecoin usdt/dai/pax/usdc/busd:
coverage 99.45%, NaN 12, stale 2d

aviv:
coverage 99.68%, NaN 7, stale 1d
```

### 3.2 反例指标确认

以下指标不应进入当前 Phase 2.5 主实验：

| 指标 | 问题 |
|---|---|
| `mvrv_zscore_adapt_data` | stale 234d, L3 |
| `stablecoin_supply` | coverage 64.28%, stale 925d, L3 |
| `stablecoin_others` | coverage 65.69%, stale 894d, L3 |
| miner 系列 | stale 217-291d, L3 |
| BGeo `funding_rate` | 当前 daily align coverage 0%, L3 |

---

## 4. P0 风险与建议

### 4.1 P0: 外部数据 availability lag 未定义

当前 `_load_onchain_series()` 行为：

```python
data["value"].reindex(target_index, method="ffill")
```

这意味着特征日 `t` 直接使用 BGeo 日期 `t` 的值。

问题是：链上指标的 `date=t` 数值是否在 `t` 日模型决策时点已可用？如果不可证明，则存在 Layer 0 未来函数风险。

建议写入 hard rule：

```text
所有 external/onchain daily features 默认 shift(1)，
除非能证明该指标在 t 日决策时刻已发布。
```

或在 config 中显式加：

```yaml
external:
  availability_lag_days: 1
```

### 4.2 P0: DERIV-SHORT 不应直接对比 2020 baseline

CMD 衍生品数据主要从：

```text
2022-12-03
```

但 Phase 2.5 baseline 是：

```text
2020-01-01 ~ 2025-12-31
```

如果加入 `keep_nan_features`，LightGBM 可能学到：

```text
NaN = 早期 regime
非 NaN = 后期 regime
```

这会把缺失性变成日期代理变量，而不是 funding/OI/liquidation alpha。

建议：

```text
E19-DERIV-SHORT 必须重跑 2022-12-03 起同窗 E1 baseline，
然后只和同窗 baseline 对比。
```

### 4.3 P0/P1: `mvrv_btc_price` 不建议作为 alpha 特征

`mvrv_btc_price` 本质上是 BTC price representation，项目已有 OHLCV 与 technical features。

风险：

- 与已有价格特征高度共线；
- 不是正交链上 alpha；
- 会污染 MVRV family 的解释性；
- 容易让模型把价格重复信息当作新增 alpha。

建议：

```text
mvrv_btc_price 仅用于 QA / 对齐校验，
不进入模型特征集。
```

推荐 MVRV-EXT 改为：

```text
mvrv_data
mvrv_365dma
mvrv_diff
mvrv_zscore_data
```

如必须保留 5 个指标，应选择非价格代理的 L1 链上指标。

---

## 5. 文档措辞建议

### 5.1 `ffill_then_drop 不丢行` 表述过满

当前含义容易被误读为完全不丢样本。

建议改为：

```text
L1 + ffill_then_drop 不会因 BGeo 偶发缺口大量丢行；
但 rolling 派生特征仍会按窗口长度自然丢弃前置样本。
```

原因：

- `zscore_90` 会自然损失前 89 行；
- `slope_30` 会自然损失前 29 行；
- labels / sampling 也会影响最终 effective rows。

### 5.2 BGeo funding_rate 需加注

BGeo `funding_rate` 当前 audit：

```text
data_start 2023-07-09
data_end   2026-05-31
coverage   0.00%
NaN        2192
level      L3
```

可能原因是 schema/frequency 与当前 daily exact reindex 不匹配。

建议补充：

```text
BGeo funding_rate 当前不进入 Phase 2.5；
若未来使用，需先做频率归一化/字段解析，
不可直接 daily reindex。
```

---

## 6. Sub-experiment 专项意见

### 6.1 E19-PUELL

结论：推荐先跑。

理由：

- 单指标；
- L1 数据质量；
- 长历史；
- 适合作为 Phase 2.5 smoke test。

前提：外部特征需处理 availability lag。

### 6.2 E19-SOPR-NEW

结论：推荐第二优先级。

理由：

- SOPR/CDD 数据质量好；
- 与 LTH/STH NUPL 不完全同源；
- 有独立行为维度。

注意：`lth_sopr` / `sth_sopr` 仍偏慢，raw 不应直接进入模型。

### 6.3 E19-MVRV-EXT

结论：可跑，但建议删除 `mvrv_btc_price`。

推荐指标：

```text
mvrv_data
mvrv_365dma
mvrv_diff
mvrv_zscore_data
```

`mvrv_zscore_data` raw level 作为 regime exception 可以接受，但必须在 config 中明示。

### 6.4 E19-ADDRESS

结论：可跑。

理由：

- 数据为 L1；
- holder structure 有一定正交性。

风险：

- 仍属于慢变量；
- weekly bear 上更可能是弱 alpha 或 regime interaction，而不是强单点 alpha。

### 6.5 E19-STABLE

结论：可跑。

注意：

- `BUSD` 数据层面为 L1；
- 但 2023 后经济意义衰减，若 feature importance 很高，需要额外审计。

### 6.6 E19-AVIV

结论：适合作为单点 sanity check。

理由：

```text
2010-07-19 ~ 2026-05-31
coverage 99.68%
stale 1d
```

注意：AVIV 仍是慢变量，必须做 short-horizon transform。

### 6.7 E19-DERIV-SHORT

结论：不建议直接并入 2020 baseline 对比。

推荐流程：

```text
1. 重跑 2022-12-03 起 E1 baseline；
2. 再跑 DERIV-SHORT；
3. 只比较同窗 Kappa / F1 / fold stability。
```

---

## 7. Final Verdict

### 文档评分

```text
8 / 10
```

优点：

- 数据源定位准确；
- 2020 baseline 锁定正确；
- BGeo 长历史方向有数据支撑；
- 慢变量 short-horizon 转换原则正确；
- 反 overfitting 纪律明确。

主要扣分点：

1. external/onchain availability lag 没有硬规则；
2. DERIV-SHORT 的同窗 baseline 问题没钉死；
3. `mvrv_btc_price` 不应作为 alpha 特征；
4. 原 audit 脚本与文档不一致；
5. `ffill_then_drop 不丢行` 表述过满。

---

## 8. 建议立即 patch 到主 plan 的 4 条

```text
1. 在 §3 或 §4 加：
   所有 onchain/external daily features 默认 shift(1)。

2. 在 E19-MVRV-EXT 删除：
   mvrv_btc_price 作为模型特征。
   改为 QA-only。

3. 在 E19-DERIV-SHORT 加：
   必须使用 2022-12-03 起同窗 E1 baseline。

4. 在 §2.2 改：
   ffill_then_drop 不因偶发缺口大量丢行，
   但 rolling transform 会自然丢前置窗口。
```

---

## 9. Related Files

本次 review 过程中已更新：

```text
scripts/audit_bgeo_nan.py
data/external/onchain/nan_audit.json
```

验证命令：

```bash
python scripts/audit_bgeo_nan.py
python -m py_compile scripts/audit_bgeo_nan.py
```
