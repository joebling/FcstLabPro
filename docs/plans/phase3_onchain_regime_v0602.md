# Phase 3: 链上指标的正确用法 — Regime / 配置 / 极值

> **日期**: 2026-06-02
> **作者**: sam (with Qiu)
> **状态**: 设计文档 (未实现)
> **前置**: Phase 2.5 §9.1 认知校正 — 链上指标在"日频 directional T=21"任务无效, 但失败的是 *(指标 × 任务)* 组合, 非指标本身.

---

## 0. 核心范式转变

| | Phase 2.5 (E18-E23) | **Phase 3** |
|---|---|---|
| 链上指标角色 | **预测特征** (喂 LightGBM) | **决策规则 / 状态开关** |
| 任务 | 日频 directional T=21 | regime 判定 / 月度配置 / 极值事件 |
| 结果 | 全败 (尺度错配/冗余/信号弱) | 待验证 (任务对齐) |

> **一句话**: E18-E23 把链上指标当"预测特征"喂模型 → 失败.
> Phase 3 把它当"决策规则/状态开关"用 → 对症.

---

## 1. 数据资产盘点 (2026-06-02)

现有 `data/external/onchain/` 15 个指标, 覆盖充分:

| 指标 | 行数 | 范围 | Phase 3 用途 |
|---|---|---|---|
| `mvrv_zscore_data` | 5620 | 2011-2026 | ⭐ Regime gating 主指标 |
| `sopr_data` | 5256 | 2012-2026 | ⭐ 极值抄底 (<1) |
| `puell_multiple_data` | 5119 | 2012-2026 | ⭐ 极值逃顶 (>4) |
| `mvrv_data` | 5254 | 2012-2026 | Regime 辅助 |
| `nupl_data` | 4888 | 2013-2026 | Regime 辅助 (净未实现盈亏) |
| `reserve_risk` | 5101 | 2012-2025 | 长期配置 |
| 其余 (lth/sth/cdd/aviv) | — | — | 备用 |

**关键值域 (用于阈值设计)**:
- MVRV-Z: min=-0.69, max=10.66, mean=1.49, 当前=0.67; p10=-0.13, p50=1.20, p90=3.35
- SOPR: min=0.828, max=1.631, 当前=0.988, <1 占比 35.2%

---

## 2. 现有基础设施 (Phase 3 不从零开始)

| 已有 | 位置 | Phase 3 如何复用 |
|---|---|---|
| `build_regime_features` (纯价格 regime) | `src/features/regime.py` | 扩展: 增加链上 regime 维度 |
| `is_bear_market` (63d 滚动收益) | `scripts/live_signal.py:125` | 升级: 价格 regime → 价格+链上 regime |
| `--regime-switch` 开关 | `live_signal.py` / `weekly_signal.py` | 复用: gating 决策入口 |
| E20c production 模型 | `models/production/e20c-conservative-prune/` | 被 gating 包裹增强 |

**现状**: regime 判定**纯价格** (200MA 位置 + 63d 滚动收益). Phase 3 = 引入**链上维度**.

---

## 3. 三种用法详解

### 3.1 Case A: Regime Gating (MVRV-Z 判牛熊) ⭐ 优先级 1

**定位**: 不预测, 而是分类当前市场状态, 不同 regime 用不同策略/仓位.

**Regime 划分** (用滚动历史分位, 禁用全样本分位避免未来函数):
```
MVRV-Z > rolling_p90  → 顶部区  → 防御 (减仓 / 只做空 / 用 bear 模型)
MVRV-Z ∈ [p10, p90]   → 正常区  → 跑 E20c directional
MVRV-Z < rolling_p10  → 底部区  → 进攻 (加仓 / 只做多 / 用 bull 模型)
```

**两种落地路径**:
- **A1 硬切换**: MVRV-Z 决定"用哪个模型". 呼应 §4.1 Regime-Specific.
- **A2 软加权**: `position = base_signal × f(MVRV-Z)`, 越接近顶部仓位越小. (推荐先做, 更平滑)

**为什么这次可能成**: regime 是月级状态判断, 正好匹配 MVRV 的有效周期 (数月). 指标没变, 任务对了.

**验证**: 对比 "E20c + gating" vs "E20c 裸跑" 的 Sharpe / MaxDD. **重点看回撤** — gating 的价值主要在顶部躲大跌.

**坑**:
- 🔴 阈值必须用**滚动历史分位**或**固定先验** (0 / 3.5), 严禁全样本分位 (未来函数!)
- 🔴 regime 切换加**滞后/缓冲带** (hysteresis), 否则阈值附近反复横跳 → 成本爆炸
- 🟡 backtest 时 MVRV-Z 需 `shift(1)` (Layer 0 防护, 当日收盘后才知)

> **CONCLUSION (2026-06-02, Phase 3a 首轮回测)** ⚠️ **条件性负面 — 验证窗口不具备条件, 非方法失败**
>
> **工程状态**: regime 判定核心 (`src/strategy/onchain_regime.py`) + 回测脚本
> (`scripts/regime_gating_backtest.py`) 均已就绪, 6 单测过, sanity check 完美
> (top 精准命中 2013/2017/2021 牛顶, bottom 命中 2015/2018/2022 熊底)。
>
> **回测结果**: E20c 裸跑 vs +MVRV-Z gating 在 OOS (2022-09~2025-11) 上 **指标零变化**
> (Sharpe 0.49, MaxDD -20.4% 两者一致)。
>
> **真因 (关键)**: OOS 期间 MVRV-Z 范围 [-0.36, 3.35], **最高值恰好只到顶部阈值 p90=3.35**,
> 加 hysteresis 后 **一天顶部区都没触发** (regime 占比: normal 94.7% + bottom 5.3%, top=0)。
> 2021 牛市顶在 OOS 之前 (被 init_train=800 吃掉), 而 gating 的主战场是顶部防御 →
> **没有顶, 防御无用武之地**。底部加仓 (bottom_mult 1.2~1.5) 亦无效 (E20c 在底部区多为空仓, 乘子作用于 0)。
>
> **与 E22/E23 的根本区别**: E22/E23 是方法被证伪 (信号冗余/太弱);
> 本次是 **验证窗口本身缺乏要验证的东西 (无牛顶)**, 不能据此判定 gating 无效。
>
> **正确验证路径 (待做)**:
> 1. **含顶部的 OOS**: 缩小 init_train 或用更早起始 (含 2021 顶), 但需衡量 negative transfer (lesson_0601).
> 2. **全样本 walk-forward** (从 2017 起): 覆盖多个牛熊周期, 才能公平检验顶部防御.
> 3. **或转向 Case C 极值择时**: 同样需含极值事件的窗口, 但门槛更低 (只防尾部).


---

### 3.2 Case B: 月度配置 (降频, 非 21 天) — 优先级 2

**定位**: 把 horizon 从"21天方向"改成"1个月配置权重". 资产配置思路, 非择时.

**流程**:
```
每月初:
  读 MVRV-Z / SOPR / Puell 当前状态
  → 映射为 BTC 配置权重 (0% ~ 100%)
  → 持有到月末, 不动 (月度再平衡)
```

**为什么这次可能成**: 日频 directional 把链上慢信号切碎成噪音. 月频聚合后信号才显现. 同样数据, 降采样 = 提信噪比.

**坑**:
- 🔴 **样本量骤减** (6 年 = 72 个月). 严禁 ML 过参数化, 只能纯规则或 1-2 参数线性映射, 否则必欠拟合.
- 🔴 需单独建月度评估框架 (现有 weekly T=21 非重叠采样不适用).
- 🟡 月度再平衡的成本/滑点模型与日频不同.

---

### 3.3 Case C: 极值二元择时 (SOPR<1 抄底 / Puell>4 逃顶) — 优先级 3

**定位**: 纯规则, 不用 ML. 平时不动, 只在极端时刻出手. 事件驱动叠加层.

**规则**:
```
SOPR < 1.0    → 持有者整体亏损抛售 → 恐慌底 → 抄底
Puell > 4.0   → 矿工抛压极大 → 周期顶 → 逃顶
MVRV-Z > 7    → 极度泡沫 → 清仓
MVRV-Z < 0    → 深度低估 → 满仓
```

**落地**: 盖在主策略 (E20c) 之上的覆盖层. 平时跑 E20c, 极值触发时强制覆盖主信号.

**为什么这次可能成**: 极值罕见但高确信. 之前全程喂模型, 95% 时间 SOPR 在 [0.95,1.05] 是噪音, 淹没了 5% 极值价值. 只取极值 = 滤噪留信.

**坑**:
- 🔴 极值事件极少 (几年几次) → 统计显著性几乎无法验证. 这更像**风险管理规则**而非可回测 alpha.
- 🔴 阈值 (1.0/4.0) 是业界经验值, **不能在自己数据上调优** (否则 overfit 历史). 用经验值或滚动分位.

---

## 4. 三者对比与实施顺序

| | 复杂度 | 样本量需求 | 验证难度 | 最适合 |
|---|---|---|---|---|
| A Regime Gating | 中 | 中 | 中 | **增强现有 E20c 回撤** |
| B 月度配置 | 低 | 低(样本少) | 高 | 长期配置 |
| C 极值择时 | 最低 | 极少 | 最难 | 风险管理/尾部保护 |

**推荐顺序: A → C → B**
1. **A 先做**: 直接增强 E20c (非另起炉灶), 验证清晰 (Sharpe/MaxDD), 样本量够, 复用现有 regime 基础设施.
2. **C 次之**: 作为 A 的极值补充层, 实现最简单, 当风险管理规则用.
3. **B 最后**: 需新建月度框架 + 样本少, 单独立项.

---

## 5. Phase 3a (Case A) 实施草案

> 仅当决定动手时展开, 当前为占位.

**步骤**:
1. 扩展 `src/features/regime.py`: 新增 `build_onchain_regime_features` (MVRV-Z 滚动分位 → regime label), `shift(1)` 防未来函数.
2. 新建 `src/strategy/regime_gate.py`: `apply_gate(signal, regime, mode)` — A1 硬切换 / A2 软加权.
3. 回测对比脚本: `scripts/regime_gating_backtest.py` — E20c 裸跑 vs +gating, 输出 Sharpe/MaxDD/Calmar 对比表.
4. 验证门槛: gating 后 **MaxDD 改善 ≥ 10%** 且 **Sharpe 不劣化**. 达标才进 live_signal `--regime-switch` 升级.

**反 overfitting 纪律** (沿用 §8.3):
- ❌ 反复调 MVRV-Z 分位阈值让回测变好
- ✅ 阈值用先验 (p10/p90 滚动) 或业界经验值, 固定后只验证一次
- ✅ 失败则写 CONCLUSION 关闭, 不强救

---

## 6. 重要边界 (引自 §9.1)

> 「某因子在条件 X 下无效」≠「某因子无效」.
> Phase 2.5 关闭的是 *(链上指标 × 日频 directional)* 组合.
> Phase 3 换任务设定后, 链上指标应**重新评估**, 不受 Phase 2.5 判决约束.

---

*本文档为 Phase 3 总蓝图. 各 Case 动手时在对应 §3.x 下加 CONCLUSION 段落, 保持单一权威性.*
