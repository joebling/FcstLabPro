# 特征工程现状 Review

> **生成时间**: 2026-05-22
> **作者**: sam (代码 review 助手)
> **基线**: E1-conservative + E8-touch 生产模型 (129 特征)
> **同级文档**:
> - [`feature_dictionary.csv`](../specs/feature_dictionary.csv) — 129 特征完整字典 (含分类/公式/重要性)
> - [`feature_engineering_roadmap.md`](../plans/feature_engineering_roadmap.md) — 基于本文诊断给出的改进 Plan

---

## 0. TL;DR (一页摘要)

| # | 严重度 | 核心结论 |
|---|---|---|
| 1 | 🔴 **P0** | **`funding_rate_14` 是双料 #1 特征，但本质是价格动量的代理 (`close.pct_change().rolling(14).mean()`)。模型最依赖的"市场结构"信号其实是价格自己。** |
| 2 | 🔴 **P0** | `market_structure.py` 里 7 个特征命名为 `funding_rate_*` / `open_interest_*` / `stablecoin_inflow_proxy`，**视觉上像外部数据，实际全是 OHLCV 衍生品** — 在 E8 模型中合计 **15.3% 重要性** |
| 3 | 🟠 **P1** | `data/external/funding_rate_BTCUSDT.csv` 等**真实**数据已经下载，但 E1/E8 没启用 `external_fr` / `external_macro` 子集 — 真货闲置、假货上岗 |
| 4 | 🟠 **P1** | `onchain.py` 和 `sentiment.py` 整个模块都是"模拟链上/情绪"代理（注释自承），所有 MVRV/SOPR/NUPL/FGI 都是 `close` 的代数组合，**完全没有真链上信息** |
| 5 | 🟡 **P2** | 37/129 (29%) 的特征在两模型里 importance ≤ 5 — 高度稀疏，候选大规模剪枝 |
| 6 | 🟡 **P2** | SMA + EMA 跨 6 个窗口共 12 个特征，总重要性仅 3-6% — 多重共线性严重 |
| 7 | 🟡 **P2** | DRY 违规: `flow.py` 与 `market_structure.py` 重复定义 `qvol_*` / `trades_*` / `avg_trade_size_*` / `volume_density_*` / `flow_*`，后者覆盖前者；命名后缀不同(`_sma_` vs `_ma_`)的版本**两份都保留**了 |

> 📋 **改进路线图**: 7 个问题的修复方案、优先级、估时、验证 SOP 全部在 [`feature_engineering_roadmap.md`](../plans/feature_engineering_roadmap.md)。

---

## 1. 现状盘点

### 1.1 当前 E1 / E8 启用的特征集 (5 类)

```yaml
features:
  sets: [technical, volume, flow, market_structure, external_fgi]
  drop_features: [rsi_*, price_vs_sma_*, sma_cross_10_50, sma_cross_50_200]
```

| 类别 | 模块 | 特征数 | E1 重要性 | E8 重要性 | 备注 |
|---|---|---:|---:|---:|---|
| **技术指标** | `technical.py` | 41 | 37.0% | 43.4% | SMA/EMA/RSI/MACD/BB/ATR/动量 |
| **市场结构** | `market_structure.py` | 36 | 30.5% | 30.8% | ⚠️ **15.3% 是 fake 外部数据 (E8)** |
| **量能** | `volume.py` | 22 | 16.2% | 14.4% | 成交量均线/比率/OBV/VWAP |
| **资金流** | `flow.py` | 20 | 11.4% | 6.3% | DRY 违规：与 market_structure 重复 |
| **外部数据** | `external.py` (仅 FGI 子集) | 10 | 4.9% | 5.1% | 真实数据但占比极低 |
| **合计** | — | **129** | 100% | 100% | |

### 1.2 没有启用的模块 (代码里写了但生产没用)

| 模块 | 状态 | 评语 |
|---|---|---|
| `onchain.py` | 🚫 未启用 | **谢天谢地** — 整个模块是"价格代理伪装链上指标"，启用了反而误导 |
| `sentiment.py` | 🚫 未启用 | 同上 — `fgi = 50 + price_momentum * 100 - ...` 完全是价格代数组合 |
| `regime.py` | 🚫 未启用 | 真正的 regime 分类器，但当前没启用 (可能担心和 technical 重叠) |
| `bear_volatility.py` | 🚫 未启用 | 专为 bear 模型设计的波动率标准化族 |
| `lag_rolling.py` | 🚫 未启用 | 给核心指标加 lag/rolling，但其引用的 `mvrv/lth_sopr` 来自 onchain（已 fake） |
| `external` (主特征集) | 🚫 仅启用 `external_fgi` | 真实 funding_rate / 宏观因子 / long_short_ratio 数据**已下载未启用** |

---

## 2. 七大问题诊断 (按严重度排序)

### 🔴 P0-1: 双料 #1 特征是个**价格代理**

模型 importance 排名第 1 的 `funding_rate_14` 的真实代码：

```python
# src/features/market_structure.py:30
for w in [7, 14, 24]:
    df[f"funding_rate_{w}"] = close.pct_change().rolling(w).mean() * 100
```

这就是**14 日平均收益率 × 100**，本质是动量平滑器，跟"资金费率"没有任何关系。

**为什么这是炸弹**:
- 对树模型来说，这个特征和 `return_14d` 几乎线性相关 → 多重共线性
- 命名让人误以为是衍生品市场信号 → 后续开发者基于错误前提优化
- 真正的 funding rate（多空成本不对称）携带**独立信息**，与价格弱相关，模型本该获益但没获益

**影响**: E1 中 5.3% 重要性、E8 中 11.9% 重要性都建立在这个误解上。

---

### 🔴 P0-2: 一整片"伪外部数据"特征

| 特征 | 真实代码 | E1 imp | E8 imp |
|---|---|---:|---:|
| `funding_rate_14` | `close.pct_change().rolling(14).mean() * 100` | 79 (#1) | 166 (#1) |
| `funding_rate_24` | 同上换窗口 | 22 | 12 |
| `funding_rate_7` | 同上换窗口 | 2 | 12 |
| `open_interest_7` | `volume.rolling(7).sum()` | 5 | 0 |
| `open_interest_14` | `volume.rolling(14).sum()` | 3 | 2 |
| `open_interest_24` | `volume.rolling(24).sum()` | 3 | 2 |
| `stablecoin_inflow_proxy` | `-close.pct_change(7) * volume.rolling(7).mean()` | 5 | 19 |
| **合计** | | **119 (7.9%)** | **213 (15.3%)** |

**E8 模型有 15.3% 的"决策权"基于这些假指标。**

---

### 🟠 P1-3: 真数据已经下载但未启用

`src/features/external.py` 已经实现了 4 大类**真实**外部数据的读取与衍生：

| 子特征集 | 数据来源 | 状态 |
|---|---|---|
| `external_fgi` | `data/external/fear_greed_index.csv` (alternative.me) | ✅ 已启用 |
| `external_macro` | `data/external/macro_factors.csv` (DXY/SPX/Gold/10Y) | 🚫 未启用 |
| `external_fr` | `data/external/funding_rate_BTCUSDT.csv` (Binance) | 🚫 未启用 |
| `external` (全集，含 long_short_ratio) | 全部 4 类 | 🚫 未启用 |

**只用 FGI 不用宏观/真 funding 是个明显的浪费。**

---

### 🟠 P1-4: `onchain.py` + `sentiment.py` 命名是定时炸弹

虽然当前没启用，但代码里**"MVRV / SOPR / NUPL / FGI"** 这些圈内 holy-grail 级别的命名都被用来包装价格代理。未来的开发者：

1. 看到 `mvrv` 在代码里 → 以为已经实现
2. 在 `lag_rolling.py:CORE_FEATURES` 里看到 `mvrv` 已被引用
3. 启用 `onchain` 特征集 → 拿到的根本不是真 MVRV

```python
# src/features/onchain.py:28 — 注释自承是代理
# 用 close / expanding_mean(close) 模拟
realized_price = close.expanding().mean()
df["mvrv"] = close / realized_price
```

**真正的 MVRV** 需要 Realized Cap (每个 UTXO 按最后移动时的价格估值再加总)，与 `close.expanding().mean()` 完全不是一回事。

---

### 🟡 P2-5: 29% 特征接近零价值

37/129 个特征在两个模型里 importance ≤ 5（每个特征对 splits 的贡献不到 0.4%）。这些是 LightGBM 训练时"碰一下就丢"的特征 — 占模型参数空间，但不提供信号。

零重要性 (importance = 0 in both) 的 3 个特征：
- `qvol_ratio_10` — 与 `qvol_ratio_5/20` 极度共线
- `ext_fgi_extreme_fear` — 历史上极少触发 → 树模型分裂时样本不足
- `ext_fgi_extreme_greed` — 同上

---

### 🟡 P2-6: SMA/EMA 多重共线性

```python
for w in [5, 10, 20, 50, 100, 200]:
    df[f"sma_{w}"] = close.rolling(w).mean()
    df[f"ema_{w}"] = close.ewm(span=w).mean()
```

12 个均线特征总重要性 (E1: 6.5%, E8: 3.4%) — 平均每个 < 1%。LightGBM 在共线特征面前会**随机分配重要性**，模型选哪个完全是噪声。可以削到 3 个核心 (`sma_20` / `sma_50` / `sma_200`) 不损失信号。

---

### 🟡 P2-7: DRY 违规 (flow ↔ market_structure 重复)

`flow.py` 先建以下列，`market_structure.py` 后建相同列名 (后者覆盖前者)：
- `trades_sma_*`, `trades_ratio_*`, `trades_change_*`
- `qvol_sma_*`, `qvol_ratio_*`
- `flow_change_*`, `flow_price_divergence_*`
- `volume_density`

更糟的是命名不同的版本**双双保留**：
- `avg_trade_size_sma_5/10/20` (flow) ✅ 保留
- `avg_trade_size_ma_5/10/20` (market_structure) ✅ 也保留 — 公式一样
- `volume_density_sma_5/10` (flow) ✅ 保留
- `volume_density_ma_5/10` (market_structure) ✅ 也保留 — 公式一样

这是教科书级的 DRY 违规。

---

## 3. 缺失的关键维度

当前 129 个特征虽多，但**信息维度极窄**：
- 95% 直接或间接来自 OHLCV
- 5% 来自 FGI 情绪指数
- **0% 真实链上数据 / 衍生品市场数据 / 跨资产数据**

| 维度 | 当前覆盖 | 信息独立性 | 候选数据源 |
|---|---|---|---|
| **链上 (UTXO/地址)** | ❌ 全是代理 | 与价格弱相关 | Glassnode / CoinMetrics / mempool.space |
| **衍生品 (真 OI / Funding / Skew)** | ❌ 全是代理 | 与现货弱相关 | Binance / Bybit / Deribit API |
| **跨资产宏观 (DXY/SPX/Gold/10Y)** | ⚠️ 已下载未启用 | 与 BTC 周期相关 | Yahoo Finance / FRED |
| **季节性 (周/月/减半周期)** | ❌ 完全缺失 | 与价格完全独立 | 直接从日期推导 |
| **市场广度 (Alt/BTC 比, Dominance)** | ❌ 缺失 | 与 risk-on/off 相关 | CoinGecko / TradingView |
| **链上估值 (真 MVRV / NUPL / SOPR)** | ❌ 全是代理 | 与周期顶/底高度相关 | Glassnode (付费) / CoinMetrics (免费) |

---

## 4. Importance 分布快照 (Top 10)

> 完整 129 特征排名见 [`feature_dictionary.csv`](../specs/feature_dictionary.csv)，按 E1+E8 综合重要性降序。

| 排名 | 特征 | 类别 | E1 rank | E8 rank | 备注 |
|---|---|---|---:|---:|---|
| 1 | **`funding_rate_14`** | 市场结构-模拟资金费率 | #1 | #1 | ⚠️ 价格代理，非真 funding |
| 2 | `high_50d_dist` | 技术-极值距离 | #4 | #2 | E8 看重 |
| 3 | `low_50d_dist` | 技术-极值距离 | #14 | #3 | E8 反弹检测 |
| 4 | `obv` | 量能-OBV | #3 | #8 | E1 看重 |
| 5 | `volatility_20d` | 技术-波动率 | **#2** | #59 | E1/E8 分歧巨大 |
| 6 | `bb_pctb_20` | 技术-布林带 | #42 | #5 | E8 喜欢的位置指标 |
| 7 | `obv_sma_20` | 量能-OBV | #5 | #14 | E1 看重 |
| 8 | `return_3d` | 技术-收益率 | #14 | #4 | 短期动量 |
| 9 | `return_14d` | 技术-收益率 | #14 | #5 | 与 funding_rate_14 高度共线 |
| 10 | `macd` | 技术-MACD | #18 | #10 | 经典动量指标 |

---

## 5. 下一步

本文档**只做诊断**，不做修复决策。

完整的改进路线（含 4 个 Phase / 估时 / 风险评估 / MVRV 集成方案 / 验证 SOP）请见：

→ [`feature_engineering_roadmap.md`](../plans/feature_engineering_roadmap.md)
