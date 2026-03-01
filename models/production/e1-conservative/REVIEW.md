# E1 Conservative — 生产评审（Review）

> 评审对象：`models/production/e1-conservative/`
>
> - 模型哈希：`4ca65e75f1df1b72`
> - 晋升时间：2026-03-01
> - 源实验：`weekly_bear_v0305_E1_decontam`（git: `693b7b1`）
> - 生产变体：`conservative`（CLI：`--take-profit --regime-switch`）
>
> 本文为“可上线性/可运营性”视角的专业评审结论，便于后续上线审批与复盘。

---

## 1. 结论（Go / No-Go）

- ✅ **作为“线上信号服务”上线：Go**
  - 工程产物齐全、谱系清楚（manifest/config/metrics/pnl）
  - 标签定义与“去污染”处理正确，降低了离线虚高风险
  - 保守变体回撤控制优（MaxDD -12.7%）

- ⚠️ **作为“自动实盘交易策略”直接全量上线：No-Go（建议先灰度/paper trading）**
  - 样本量与稳定性不足（fold 约 48% F1=0；交易数 23 笔）
  - 回测假设与真实执行可能存在偏差（成本/滑点/触发路径）

---

## 2. 标签定义与泄露风险

### 2.1 标签策略：`directional_filtered`

标签含义：当处于“超卖低位”时，预测未来 21 天是否能达到 ≥4% 的反弹（定义见 `config.yaml`）。

关键参数：
- T=21
- X=0.04
- RSI(14) < 45
- close < SMA(50)

### 2.2 去污染（关键亮点）

由于标签使用 RSI/SMA 作为过滤条件，如果特征中包含 RSI、price_vs_sma、sma_cross 等，会造成“特征-标签泄露”的捷径学习。

本模型在 `features.drop_features` 中移除了：
- `rsi_*`
- `price_vs_sma_*`
- `sma_cross_10_50`
- `sma_cross_50_200`

这一步显著提高了线上可用性可信度。

### 2.3 需要确认的专业问题（标签与交易目标不完全一致）

生产策略启用 `--take-profit`，止盈触发逻辑是“未来 T 天内是否触及 +4%”。
而标签更像“第 21 天收盘是否 ≥ +4%”（路径无关）。

这会带来目标不一致：
- 标签可能判负，但路径上其实早就触发过 TP
- 标签判正，但路径上可能先大幅回撤（对真实资金体验不友好）

建议补做：
- label 版本：`touch_X_within_T`（是否在窗口内触达 +X%）对照

---

## 3. 离线分类效果（metrics.json）

汇总指标：
- accuracy: 0.8733
- precision: 0.3960
- recall: 0.4341
- f1: 0.4142
- **kappa: 0.3433**

专业解读：
- Kappa 0.34 在金融序列任务里属于“有真实信息含量”的区间（明显优于随机）
- 但模型稳定性风险显著：walk-forward folds 中约 48% F1=0（报告中已提示）

上线影响：
- 线上会呈现“时灵时不灵”的 regime 依赖特征
- 需要在运营层面补监控与熔断，而不是只看一组汇总指标

建议补充离线诊断：
- 分年份/分 regime 的 precision、recall、kappa
- PR 曲线 / 阈值扫描（不要只用固定阈值输出 0/1）
- 概率校准（Platt/Isotonic），用于更稳健的交易阈值

---

## 4. PnL 回测效果（pnl_metrics.json）

生产变体（止盈+regime）：
- total_return: 0.3667
- **cagr: 0.0981**
- sharpe: 0.6333
- **max_drawdown: -0.1266**
- **profit_factor: 1.3183**
- num_trades: 23
- exposure: 0.1363

专业解读：
- 回撤压得很低（-12.7%）是该变体最核心价值
- PF 1.32 表示盈亏比结构健康
- 但交易数 23 笔偏少，统计显著性不足以支持“直接自动实盘”

重要注意：
- 项目中提到的 Alpha Z-score=2.35 看起来来自“基础版”统计，不能直接为生产保守版背书。
  建议对止盈+regime 版本单独计算显著性/bootstrapping 置信区间。

---

## 5. 工程与可运营性

优点：
- 生产模型打包完整（model/config/manifest/metrics/pnl）
- `manifest.json` 提供谱系（来源实验、哈希、指标、检查清单）
- 生产路径固定 `models/production/...`，部署镜像可包含模型

需要改进：
- `manifest.json` 中 `promotion_git.dirty=true`：建议正式上线前确保晋升时 git workspace clean，提升审计可信度。

---

## 6. 上线建议（分阶段）

### 6.1 Phase A：上线为信号服务（推荐）
- 产出 BUY/HOLD/SELL/SILENT + regime 值 + 触发原因
- 不直接自动下单

### 6.2 Phase B：paper trading（4~8 周）
必须记录：
- 每笔交易 MFE/MAE（最大浮盈/最大回撤）
- 触发时的 regime 分布、信号密度
- 成本/滑点敏感性（0.1% 单边 → 0.2%/0.3% 压力测试）

### 6.3 Phase C：灰度实盘（如需）
- 小仓位、强风控熔断
- 连续亏损、月度回撤触发自动暂停

---

## 7. 必补验证清单（上线前）

1. ✅ 成本敏感性：手续费/滑点 0.1%→0.3% 单边
2. ✅ 阈值敏感性：regime 阈值 -8%/-10%/-12%，TP 3%/4%/5%
3. ✅ 分 regime 的分类与 PnL：熊/震荡/牛
4. ✅ 生产变体的显著性：对“止盈+regime”单独做 bootstrap / 随机基线检验
5. ✅ 数据缺失/异常回退：Binance API 失败时的处理策略

---

## 8. 附：评审依据文件

- `manifest.json`
- `config.yaml`
- `metrics.json`
- `pnl_metrics.json`
- `REPORT.md`

---

评审日期：2026-03-01
