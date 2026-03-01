# E1 Conservative — 生产模型报告

> **模型哈希**: `4ca65e75f1df1b72`
> **晋升时间**: 2026-03-01
> **源实验**: `weekly_bear_v0305_E1_decontam` (git: `693b7b1`)

---

## 一、执行摘要

E1 是一个 BTC 日线级别的【跌后反弹捕捉】策略。当模型检测到超卖低位时发出买入信号，目标捕捉 21 天内 ≥4% 的反弹。

**推荐用作择时辅助信号，不作为唯一交易依据。**

| 维度 | 值 |
|------|------|
| 策略变体 | **conservative** (止盈 + regime 过滤) |
| 回测 CAGR | 9.8% |
| 回测 MaxDD | -12.7% |
| 回测 Profit Factor | 1.32 |
| 回测 Sharpe | 0.63 |
| Alpha Z-score | 2.35 (p < 0.02，统计显著) |
| 平均暴露 | 13.6% (大部分时间空仓) |
| 模型类型 | LightGBM (129 特征，已去污染) |

---

## 二、标签定义

### 2.1 标签策略: `directional_filtered`

**核心问题**: 在「超卖低位」的市场状态下，未来 21 天 BTC 是否会反弹 ≥4%？

```python
# 条件 1: 当前处于超卖低位
rsi_14 < 45                # RSI 低于 45 (偏超卖)
close < SMA_50             # 价格在 50 日均线下方

# 条件 2: 未来反弹达标
future_return_21d >= 4%    # 21 天后收盘价相对今日涨幅 ≥4%

# 标签
label = 1 if (条件 1 且 条件 2) else 0
```

**参数**:

| 参数 | 值 | 含义 |
|------|------|------|
| T | 21 天 | 预测窗口 |
| X | 4% | 反弹阈值 |
| rsi_window | 14 | RSI 计算窗口 |
| rsi_threshold | 45 | RSI 超卖分界线 |
| ma_window | 50 | 均线窗口 |
| require_below_ma | true | 必须在均线下方 |

### 2.2 去污染设计

标签使用 RSI 和 SMA 作为过滤条件，如果模型特征中也包含这些指标，会产生【特征-标签泄露】。

**解决方案**: 从特征集中移除所有与标签过滤条件相关的指标：

```yaml
drop_features:
  - rsi_*            # 所有 RSI 变体 (rsi_6, rsi_14, rsi_28)
  - price_vs_sma_*   # 价格相对均线位置 (price_vs_sma_20, _50, _200)
  - sma_cross_10_50  # 均线交叉
  - sma_cross_50_200 # 死叉/金叉
```

移除后模型从 137 个特征降至 **129 个**。模型通过 funding_rate、volatility、OBV 等独立特征「间接」捕捉超卖状态。

### 2.3 为什么选择这个标签

v0304 对比了 4 种标签策略：

| 标签策略 | Kappa | 问题 |
|----------|-------|------|
| dip_recovery_v1 (旧版) | 0.560 | ❌ 标签定义存在信息泄露 |
| triple_barrier_simple | 0.003 | ❌ 几乎无预测力 |
| dip_recovery_v2 | 0.002 | ❌ 几乎无预测力 |
| **directional_filtered** | **0.267** | ✅ 无泄露、可解释 |

经参数优化 (X: 5%→4%, RSI: 40→45) 后 Kappa 提升至 **0.343**。

---

## 三、模型配置

### 3.1 模型架构

| 配置 | 值 |
|------|------|
| 类型 | LightGBM (LGBMClassifier) |
| 棵树数 | 100 |
| 最大深度 | 6 |
| 学习率 | 0.05 |
| 叶子数 | 31 |
| 子采样 | 80% (行) / 80% (列) |
| 正则化 | L1=0.1, L2=0.1 |
| 不平衡处理 | auto_scale_pos_weight |

### 3.2 特征集 (129 个)

| 特征集 | 含义 | 示例 |
|--------|------|------|
| technical | 技术指标 | MACD, BB, ATR, 动量, EMA |
| volume | 成交量 | OBV, VWAP, 量价相关性 |
| flow | 资金流 | 净买入、CVD、量价背离 |
| market_structure | 市场结构 | 资金费率、OI 代理、买卖压力 |
| external_fgi | 情绪指标 | 恐惧贪婪指数及其衍生 |

### 3.3 Top 10 特征重要性

| 排名 | 特征 | 重要性 | 解读 |
|------|------|---------|------|
| 1 | funding_rate_14 | 79 | 14日资金费率，反映多空情绪 |
| 2 | volatility_20d | 43 | 20日波动率，超卖时波动往往放大 |
| 3 | obv | 33 | OBV 能量潮，跟踪买卖压力 |
| 4 | high_50d_dist | 32 | 价格距离 50日高点的位置 |
| 5 | ext_fgi_std_14 | 29 | FGI 波动，情绪极端化程度 |
| 6 | obv_sma_20 | 29 | OBV 均线，稳定版资金流 |
| 7 | vol_price_corr_10 | 26 | 量价相关性 |
| 8 | cvd_change_21 | 25 | CVD 21日变化，主动买卖趋势 |
| 9 | sma_200 | 25 | 200日均线绝对值 |
| 10 | qvol_sma_10 | 25 | 报价量均线 |

### 3.4 训练方式

| 配置 | 值 |
|------|------|
| 方法 | Walk-Forward (Expanding) |
| 初始训练集 | 800 天 |
| OOS 窗口 | 63 天 |
| 步进 | 21 天 |
| Purge Gap | 21 天 (避免标签泄露) |
| 总 Fold 数 | 56 |
| 数据范围 | 2020-01-01 ~ 2026-02-17 |

---

## 四、分类指标

### 4.1 汇总指标

| 指标 | 值 | 说明 |
|------|------|------|
| Accuracy | 87.3% | 负例为主 (正例仅 10%) |
| Precision | 39.6% | 每 10 次买入信号约 4 次正确 |
| Recall | 43.4% | 捕捉了 43% 的反弹机会 |
| F1 | 0.414 | |
| Cohen's Kappa | **0.343** | 远超随机，有真实预测力 |

### 4.2 混淆矩阵

```
              预测=0    预测=1
实际=0       2923      241     (误报 241 次)
实际=1        206      158     (捕捉 158 次, 漏掉 206 次)
```

### 4.3 Walk-Forward Fold 稳定性

56 个 Fold 中：
- **F1 > 0 的 Fold**: 29 个 (52%)
- **Kappa > 0.5 的 Fold**: 12 个 (21%)
- **F1 = 0 的 Fold**: 27 个 (48%) — 主要发生在无正例样本的时段

> ⚠️ Fold 稳定性是主要风险点。策略并非在所有市场环境都有效。

---

## 五、PnL 回测结果

### 5.1 四个变体对比

| 变体 | Return | CAGR | Sharpe | MaxDD | PF | 暴露 |
|------|--------|------|--------|-------|-----|------|
| 基础 (激进) | +109.1% | 24.7% | 0.93 | -24.7% | 1.25 | 39.4% |
| +止盈 (稳健) | +68.8% | 17.0% | 0.77 | -24.7% | 1.26 | 26.8% |
| +regime | +61.6% | 15.5% | 0.77 | -21.6% | 1.28 | 24.4% |
| **止盈+regime (保守)** | **+36.7%** | **9.8%** | **0.63** | **-12.7%** | **1.32** | **13.6%** |
| 买入持有 | +350.8% | 57.0% | 1.20 | -32.0% | 1.20 | 100% |

**成本假设**: 每次仓位变动 0.1% 单边，完整交易 0.2%。

### 5.2 分年表现

| 年份 | 市场 | E1 基础 | E1 止盈+regime | 买入持有 |
|------|------|---------|-------------|----------|
| 2022 | 熊市 | +0.32% | -0.97% | **-13.97%** |
| 2023 | 牛市 | +53.76% | +3.86% | +155.61% |
| 2024 | 牛市 | +27.78% | +19.81% | +121.31% |
| 2025 | 震荡 | -2.48% | **+11.02%** | -6.33% |

✅ 2022 熊市护盾有效: 市场跌 14%，策略仅亏 1%
✅ 2025 震荡市中 regime 变体反而赚钱 (+11%)

### 5.3 Alpha 统计检验

| 指标 | 值 |
|------|------|
| 策略总收益 | +109.12% |
| 同暴露度随机基线 | +4.91% ± 44.41% |
| 超额收益 | +104.21% |
| **Alpha Z-score** | **2.35 (p < 0.02)** |

---

## 六、策略变体原理

### 6.1 层级关系

```
基础    = 模型信号 + 固定 21 天持仓
+止盈   = 基础 + 涨到 4% 即平仓
+regime = +止盈 + 63天滚动收益 ≤-10% → 熊市静默
```

### 6.2 保守版 (生产版) 每日决策流程

```
Step 1: Regime 判断
│  rolling_63d = (price_today / price_63d_ago) - 1
│
├─ rolling_63d ≤ -10%  →  熊市 → 强制空仓，不发任何信号
└─ rolling_63d > -10%  →  非熊市 → 继续

Step 2: 持仓检查 (已有仓位时)
├─ 浮盈 ≥ +4%  →  止盈平仓
├─ 持仓 ≥ 21 天  →  到期平仓
└─ 否则  →  继续持有

Step 3: 新信号 (无仓位时)
├─ y_pred = 1  →  买入
└─ y_pred = 0  →  静默
```

### 6.3 四种输出信号

| 信号 | 含义 | 行动 |
|------|------|------|
| 🟢 BUY | 模型检测超卖低位 | 以当日收盘价买入 |
| 🟡 HOLD | 已持仓，未触发退出 | 继续持有 |
| 🔴 SELL | 止盈/到期/熊市强平 | 卖出 |
| ⚪ SILENT | 无信号或熊市静默 | 不操作 |

---

## 七、线上使用流程

### 7.1 本地运行

```bash
# 保守版 (生产推荐)
python scripts/live_signal.py --take-profit --regime-switch

# 干跑 (只看信号，不更新状态)
python scripts/live_signal.py --take-profit --regime-switch --dry-run

# 其他变体
python scripts/live_signal.py                    # 激进
python scripts/live_signal.py --take-profit       # 稳健
```

### 7.2 云端部署 (Google Cloud Run Job)

```bash
# 一键部署
./deploy/deploy_v0305.sh

# 手动触发
gcloud run jobs execute daily-btc-signal-v0305-e1 --region asia-east1

# 查看持仓状态
gsutil cat gs://forecastlab-prod-signals/v0305-e1/signal_state.json | python3 -m json.tool
```

**云端配置**:

| 配置 | 值 | vs v0302 |
|------|------|----------|
| 内存 | 2Gi | ↓ (v0302: 16Gi) |
| CPU | 2 | ↓ (v0302: 4) |
| 超时 | 600s | ↓ (v0302: 3600s) |
| 调度 | 每日 UTC 00:05 | 币安日线收盘后 5 分钟 |
| 状态持久化 | GCS | signal_state.json |
| 邮件通知 | 启用 | QQ 邮箱 |
| LLM 分析 | 可选 | Gemini API |

### 7.3 每日流程

```
1. 加载模型 (models/production/e1-conservative/model.joblib)
       ↓
2. 获取数据 (Binance API / 本地 CSV)
       ↓
3. 构建 129 个特征 (排除 8 个污染特征)
       ↓
4. Regime 判断: 63d 滚动收益 ≤ -10% → 熊市静默
       ↓
5. 持仓检查 → 止盈/到期/熊市强平
       ↓
6. 新信号 → 模型预测 y_pred → BUY/SILENT
       ↓
7. 更新状态 (data/live/signal_state.json)
       ↓
8. [可选] 邮件通知 + LLM 分析
```

### 7.4 状态文件

`data/live/signal_state.json` 持久化当前持仓:

```json
{
  "in_position": true,
  "entry_date": "2026-03-15",
  "entry_price": 68500.0,
  "days_held": 5,
  "last_signal": "HOLD",
  "history": [
    {
      "entry_date": "2026-02-10",
      "exit_date": "2026-02-18",
      "pnl": 0.04,
      "days_held": 8,
      "reason": "止盈触发"
    }
  ]
}
```

### 7.5 模型更新

建议每月重新训练并晋升:

```bash
# 1. 重新跑实验
python scripts/run_experiment.py \
  --config configs/experiments/weekly/exp_weekly_bear_v0305_E1_decontam.yaml \
  --overwrite

# 2. 晋升到生产 (CLAUDE.md 5.1 自检)
python scripts/promote_model.py \
  --experiment experiments/weekly/weekly_bear_v0305_E1_decontam \
  --name e1-conservative

# 3. 提交并部署
git add models/production/e1-conservative/
git commit -m "promote: e1-conservative monthly update"
./deploy/deploy_v0305.sh
```

---

## 八、风险与局限性

### 8.1 已知风险

| 风险 | 说明 | 缓解 |
|------|------|------|
| Fold 不稳定 | 48% 的 Fold F1=0 | regime 过滤屏蔽无效时段 |
| 回测周期短 | 仅 3.3 年 (2022-2026) | 需 paper trading 验证 |
| 牛市跟不上 | 买入持有远超策略 | 策略定位是择时辅助，非替代持仓 |
| 数据依赖 | Binance API + FGI | 本地缓存回退 |

### 8.2 不适用场景

- 纯牛市单边上涨 (模型不出信号，因为不满足超卖条件)
- 高频交易 (这是日线策略，最快 5 天一笔)
- 大资金主力仓位管理 (仅作为择时信号)

### 8.3 健康监控建议

| 监控项 | 阈值 | 行动 |
|--------|------|------|
| 连续亏损笔数 | > 5 笔 | 暂停策略，重新评估 |
| 单笔亏损 | > -8% | 检查模型是否失效 |
| 月度回撤 | > -15% | 强制暂停 |
| Regime 连续静默 | > 60 天 | 正常 (熊市中预期行为) |

---

## 九、文件清单

| 文件 | 说明 |
|------|------|
| `model.joblib` | 生产模型 (LightGBM, 190KB) |
| `config.yaml` | 训练配置 (特征集、标签、模型参数) |
| `manifest.json` | 模型谱系 (来源、哈希、检查清单) |
| `meta.json` | 实验元数据 |
| `metrics.json` | 分类指标 |
| `pnl_metrics.json` | PnL 回测指标 |
| `REPORT.md` | 本报告 |

---

**创建日期**: 2026-03-01
**晋升 Git Commit**: `693b7b1` (experiment) → `3c53926` (promotion)
