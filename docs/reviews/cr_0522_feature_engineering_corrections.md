# CR-0522 Feature Engineering Review 修正说明

> **生成时间**: 2026-05-22  
> **作者**: sam (`code-puppy-0a0d12`)  
> **关联文档**: [`cr_0522_feature_engineering.md`](./cr_0522_feature_engineering.md)  
> **目的**: 记录对原 review 结论的二次核验结果，以及需要修正文案/归因的地方。

---

## 0. 总结

`cr_0522_feature_engineering.md` 的核心诊断结论整体成立：

- `funding_rate_14` 确实是生产 E1/E8 双模型 #1 特征。
- `funding_rate_*` 实际是 `close.pct_change().rolling(w).mean() * 100`，不是外部资金费率。
- `open_interest_*` / `stablecoin_inflow_proxy` 也是 OHLCV 衍生代理。
- E1/E8 生产配置确实只启用了 `external_fgi`，没有启用真实 `external_fr` / `external_macro`。
- `onchain.py` / `sentiment.py` 当前都是模拟代理模块，生产模型没有启用。
- 37/129 个特征在 E1/E8 中 importance 均 ≤ 5。
- SMA/EMA 12 个特征总重要性低，存在明显共线/冗余风险。

需要修正的主要是 **P2-7 DRY 违规部分的归因和措辞**。

---

## 1. 必须修正：`qvol_*` 重复定义的归因不准确

### 1.1 原文问题

原 review 的 P2-7 写法大意为：

> `flow.py` 与 `market_structure.py` 重复定义 `qvol_*` / `trades_*` / ...

其中 `qvol_*` 的归因不准确。

### 1.2 实际代码逻辑

`qvol_sma_*` / `qvol_ratio_*` 实际由以下两个模块重复生成：

| 特征族 | 模块 1 | 模块 2 | 备注 |
|---|---|---|---|
| `qvol_sma_*` | `src/features/volume.py` | `src/features/market_structure.py` | 同名重复 |
| `qvol_ratio_*` | `src/features/volume.py` | `src/features/market_structure.py` | 同名重复 |

`src/features/flow.py` **没有**生成 `qvol_sma_*` / `qvol_ratio_*`。

### 1.3 建议替换文案

建议将原 P2-7 的开头改为：

```md
DRY 违规: `volume.py` / `flow.py` / `market_structure.py`
之间存在重复定义：

- `qvol_*` 由 `volume.py` 与 `market_structure.py` 重复生成；
- `trades_*` / `flow_change_*` / `flow_price_divergence_*`
  / `avg_trade_size*` / `volume_density` 由 `flow.py`
  与 `market_structure.py` 重复生成；
- 同名列当前公式等价，后续模块会重新赋值但数值不变；
- `_sma_` vs `_ma_` 后缀版本则双双保留，形成冗余。
```

---

## 2. 建议修正："后者覆盖前者"措辞需要更严谨

### 2.1 原文问题

原 review 中提到：

> `flow.py` 先建以下列，`market_structure.py` 后建相同列名（后者覆盖前者）

这个描述方向基本对，但容易被理解为“数值发生了改变”。

### 2.2 实际情况

生产配置中的特征构建顺序是：

```yaml
features:
  sets:
    - technical
    - volume
    - flow
    - market_structure
    - external_fgi
```

因此，后面的 `market_structure.py` 确实会对已有同名列重新赋值，例如：

- `trades_sma_*`
- `trades_ratio_*`
- `trades_change_*`
- `flow_change_*`
- `flow_price_divergence_*`
- `avg_trade_size`
- `avg_trade_size_ratio_*`
- `volume_density`

但是目前这些同名重复列的公式等价，二次赋值后的数值没有实质变化。

### 2.3 建议替换文案

建议将“后者覆盖前者”改成更精确的说法：

```md
同名列会被后续模块重新赋值；当前公式等价，因此数值基本不变，
但维护上仍然违反 DRY。若未来任一模块公式调整，可能产生隐蔽行为变化。
```

---

## 3. 建议补充：完整重复列清单

二次核验发现，当前由多个 feature set 重复生成的同名列共 25 个：

| 重复列 | 生成模块 |
|---|---|
| `avg_trade_size` | `flow`, `market_structure` |
| `avg_trade_size_ratio_5` | `flow`, `market_structure` |
| `avg_trade_size_ratio_10` | `flow`, `market_structure` |
| `avg_trade_size_ratio_20` | `flow`, `market_structure` |
| `flow_change_1d` | `flow`, `market_structure` |
| `flow_change_3d` | `flow`, `market_structure` |
| `flow_change_5d` | `flow`, `market_structure` |
| `flow_change_10d` | `flow`, `market_structure` |
| `flow_price_divergence_10` | `flow`, `market_structure` |
| `flow_price_divergence_20` | `flow`, `market_structure` |
| `qvol_sma_5` | `volume`, `market_structure` |
| `qvol_sma_10` | `volume`, `market_structure` |
| `qvol_sma_20` | `volume`, `market_structure` |
| `qvol_ratio_5` | `volume`, `market_structure` |
| `qvol_ratio_10` | `volume`, `market_structure` |
| `qvol_ratio_20` | `volume`, `market_structure` |
| `trades_sma_5` | `flow`, `market_structure` |
| `trades_sma_10` | `flow`, `market_structure` |
| `trades_sma_20` | `flow`, `market_structure` |
| `trades_ratio_5` | `flow`, `market_structure` |
| `trades_ratio_10` | `flow`, `market_structure` |
| `trades_ratio_20` | `flow`, `market_structure` |
| `trades_change_1d` | `flow`, `market_structure` |
| `trades_change_5d` | `flow`, `market_structure` |
| `volume_density` | `flow`, `market_structure` |

---

## 4. 保留但建议标注为假设：SMA/EMA 剪枝建议

### 4.1 原结论

原 review 提到：

> 可以削到 3 个核心 (`sma_20` / `sma_50` / `sma_200`) 不损失信号。

### 4.2 建议措辞

该判断作为工程假设合理，但是否“不损失信号”需要消融实验验证。建议改成：

```md
可优先做消融实验：将 SMA/EMA 家族从 12 个缩减到
`sma_20` / `sma_50` / `sma_200` 等少量核心趋势特征，
验证是否能在不显著损失 Kappa / PnL 的前提下降低冗余。
```

这样更符合证据边界，避免把待验证优化写成已验证事实。

---

## 5. 可直接修改原文的位置

建议在 `cr_0522_feature_engineering.md` 中只改两处，保持 diff 小：

1. **TL;DR 第 7 条**  
   将 `flow.py 与 market_structure.py 重复定义 qvol_* ...`  
   改为 `volume.py / flow.py / market_structure.py 之间存在重复定义 ...`。

2. **P2-7 小节正文**  
   替换重复定义清单和“后者覆盖前者”的措辞，加入第 3 节中的 25 个重复列清单。

不建议重写整篇 review。原文核心诊断是正确的，只需要修正 DRY 归因和证据边界。

---

## 6. 核验命令摘要

二次核验过程中执行了以下类型检查：

- 读取 E1/E8 production config，确认 feature sets 与 drop features。
- 读取 `src/features/*.py`，核对特征公式。
- 聚合 `docs/specs/feature_dictionary.csv`，确认 importance 分布。
- 构建 E1/E8 特征列，确认生产特征数为 129。
- 扫描各 feature set standalone 输出，确认重复列来源。
- 计算 `funding_rate_14` 与 `return_14d` 的相关性，结果约为 `0.9953`。

结论：原 review 主结论可保留，以上修正项建议作为后续小 patch 处理。
