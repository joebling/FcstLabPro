# v0302 实验计划：Alpha 真实性验证

> 基于 v0301 Review（plans/v0301_report_review.md）的 Action Items 制定。
> 目标：用"毁灭性测试"攻击现有结果，幸存下来的才是真 alpha。
>
> 创建日期：2026-02-20

---

## 零、背景与动机

v0301 实验达到了以下指标：

| 指标 | 值 |
|------|-----|
| Spearman IC | +0.65 |
| IC t-stat | 4.75 |
| Sharpe | 1.24 |
| MaxDD | 13.96% |

但两位独立审阅者的共识是：**"好到可疑"**。

核心质疑：
1. IC=0.65 是二分类 label 结构性抬高的结果，还是真实 alpha？
2. Sharpe=1.24 主要来自 Triple MA 过滤器，还是模型信号？
3. t-stat=4.75 是缩短训练集人为扩大样本量的产物，还是统计真实？
4. 信号方向是事后反转的，是否存在 data snooping？

本计划通过 **12 个实验** 逐一回答这些问题。

---

## 一、实验总览

| Phase | 实验 | 优先级 | 目的 | 预估耗时 |
|-------|------|--------|------|---------|
| **P0** | E01 随机标签测试 | 🔴 | 排除 pipeline 泄露 | 0.5 天 |
| **P0** | E02 纯收益排序 IC | 🔴 | 区分 crash timing vs alpha | 0.5 天 |
| **P0** | E03 去 MA 纯模型测试 | 🔴 | 量化模型 vs 过滤器贡献 | 0.5 天 |
| **P0** | E04 init_train 敏感性 | 🔴 | 验证 t-stat 稳健性 | 1 天 |
| **P1** | E05 Newey-West t-stat | 🟡 | 修正自相关高估 | 0.5 天 |
| **P1** | E06 Bootstrap IC CI | 🟡 | 量化 IC 不确定性 | 0.5 天 |
| **P1** | E07 阈值敏感性 | 🟡 | 参数鲁棒性 | 0.5 天 |
| **P1** | E08 Horizon 敏感性 | 🟡 | 参数鲁棒性 | 0.5 天 |
| **P1** | E09 多资产验证 (ETH) | 🟡 | 排除标的特有性 | 1-2 天 |
| **P1** | E10 Bear Regime 详细报告 | 🟡 | 验证 IC=-0.94 是否噪音 | 0.5 天 |
| **P2** | E11 分年 OOS | 🟢 | 排除单一行情主导 | 0.5 天 |
| **P2** | E12 特征 Ablation | 🟢 | 特征重要性验证 | 1 天 |

**总预估工作量**：6-8 天

---

## 二、公共基础设施

### 2.1 基准配置

所有实验基于 v4 Extended OOS 配置：

```yaml
# configs/experiments/weekly/exp_weekly_bull_v27_orion_v4_extended_oos.yaml
data:
  path: data/raw/btc_binance_BTCUSDT_1d.csv
features:
  sets: [technical, volume, flow, market_structure, external_fgi, regime]
label:
  strategy: reversal
  T: 21
  X: 0.05
  map: {0: 0, 1: 0, 2: 1}
model:
  type: orion_bix
  params: {n_estimators: 16, random_state: 42}
evaluation:
  init_train: 800
  oos_window: 63
  step: 21
```

### 2.2 输出目录约定

```
experiments/weekly/v0302_validation/
├── e01_random_label/
├── e02_continuous_ic/
├── e03_no_ma/
├── e04_init_train_sensitivity/
├── e05_newey_west/
├── e06_bootstrap_ci/
├── e07_threshold_sensitivity/
├── e08_horizon_sensitivity/
├── e09_eth_validation/
├── e10_bear_regime_detail/
├── e11_yearly_oos/
├── e12_feature_ablation/
└── summary_report.md
```

### 2.3 公共工具模块

创建 `scripts/v0302_utils.py`，包含所有实验共用的函数，避免重复代码。

```python
# scripts/v0302_utils.py
# 包含：
# - load_base_data(config_path) -> df, feature_cols, labels
# - walk_forward_predict(X, y, config) -> predictions, fold_metrics
# - non_overlapping_ic(preds, returns, step=21) -> ic, p_val
# - monthly_ic_series(preds, returns, dates, step=21) -> ic_list
# - newey_west_tstat(ic_series, max_lag=3) -> t_stat
# - bootstrap_ci(preds, returns, n_boot=1000) -> (lower, upper)
# - backtest_strategy(signals, prices, step, ma_filter=None) -> metrics
```

---

## 三、P0 实验详细方案

### E01：随机标签测试

**目的**：如果打乱标签后 IC 仍然显著，说明 pipeline 存在数据泄露。

**方法**：
```python
# scripts/v0302_e01_random_label.py

# 1. 加载 v4 配置和数据
df, feature_cols, _ = load_base_data(CONFIG_PATH)

# 2. 生成随机标签（保持类别比例）
N_PERMUTATIONS = 100
results = []
for seed in range(N_PERMUTATIONS):
    rng = np.random.RandomState(seed)
    y_shuffled = rng.permutation(y_original)

    # 3. 完整 walk-forward + IC
    preds = walk_forward_predict(X, y_shuffled, config)
    ic, p_val = non_overlapping_ic(preds, returns, step=21)
    results.append({'seed': seed, 'ic': ic, 'p_val': p_val})

# 4. 与真实 IC 对比
real_ic = 0.65  # v4 结果
p_empirical = np.mean([abs(r['ic']) >= abs(real_ic) for r in results])
```

**验收标准**：

| 结果 | 判定 |
|------|------|
| 100 次随机 IC 均值 ≈ 0，无一次 ≥ 0.65 | ✅ Pipeline 无泄露 |
| 有 > 5% 次数 IC ≥ 0.65 | ❌ Pipeline 存在泄露 |

**输出**：
- `experiments/weekly/v0302_validation/e01_raabel/results.csv`
- `experiments/weekly/v0302_validation/e01_random_label/ic_distribution.png`
- `experiments/weekly/v0302_validation/e01_random_label/report.md`

**执行**：
```bash
python scripts/v0302_e01_random_label.py
```

---

### E02：纯收益排序 IC（Continuous Return IC）

**目的**：区分模型是 "crash timing" 还是 "continuous alpha"。

**方法**：
```python
# scripts/v0302_e02_continuous_ic.py

# 1. 使用 v4 walk-forward 预测概率
proba = walk_forward_predict_proba(X, y, config)  # 输出 P(label=1)

# 2. 计算未来 21 天连续收益
future_returns = (close[t+21] - close[t]) / close[t]  # 非 threshold

# 3. Non-overlapping Spearman IC
for i in range(0, len(proba) - 21, 21):
    signals.append(proba[i])
    returns.append(future_returns[i])

ic_continuous, p_val = spearmanr(signals, returns)

# 4. 与二分类 IC 对比
print(f"二分类 IC:   {0.65:.4f}")
print(f"连续收益 IC: {ic_continuous:.4f}")
```

**验收标准**：

| 连续 IC 结果 | 判定 |
|-------------|------|
| IC > 0.10 | ✅ 模型有真实排序能力 |
| 0.05 < IC < 0.10 | ⚠️ 弱 alpha，主要是 crash timing |
| IC < 0.05 | ❌ 本质是 crash timing，不是 continuous alpha |

**关键区别**：
- v0301 的 IC=0.65 是 `spearmanr(proba, binary_label)`
- E02 的 IC 是 `spearmanr(proba, continuous_return)`
- 如果后者远小于前者，说明模型只会预测"大跌/不大跌"，不会对收益排序

**输出**：
- `experiments/weekly/v0302_validation/e02_continuous_ic/report.md`

**执行**：
```bash
python scripts/v0302_e02_continuous_ic.py
```

---

### E03：去 MA 纯模型测试

**目的**：量化 Sharpe 提升中，模型信号 vs Triple MA 过滤器各贡献多少。

**方法**：
```python
# scripts/v0302_e03_no_ma.py

strategies = {
    'A_triple_ma':  backtest(signal, prices, ma_filter='triple'),
    'B_ma200':      backtest(signal, prices, ma_filter='ma200'),
    'C_model_only': backtest(signal, prices, ma_filter=None),
    'D_ma_only':    backtest(ma_signal_only, prices, ma_filter='triple'),
    'E_buy_hold':   backtest_buy_hold(prices),
}

# 关键对比:
# model_alpha = C.sharpe - E.sharpe   (模型纯信号 vs 买入持有)
# ma_boost    = A.sharpe - C.sharpe   (加 MA 后提升)
# ma_alone    = D.sharpe              (纯 MA 无模型)
```

**验收标准**：

| 指标 | 目标 |
|------|------|
| C (纯模型) Sharpe > 0.3 | ✅ 模型有独立 alpha |
| C Sharpe < 0.3 | ⚠️ alpha 主要来自 MA |
| D (纯 MA) Sharpe > A (MA+模型) | ❌ 模型反而拖累 |

**新增对比**：策略 D（纯 MA 无模型信号）是新增项。如果 D 的 Sharpe 已经接近 A，则说明模型对策略贡献甚微。

**输出**：
- `experiments/weekly/v0302_validation/e03_no_ma/strategy_comparison.csv`
- `experiments/weekly/v0302_validation/e03_no_ma/report.md`

**执行**：
```bash
python scripts/v0302_e03_no_ma.py
```

---

### E04：init_train 敏感性测试

**目的**：回答"t-stat 从 0.35 暴涨到 4.75 是否合理"。

**方法**：
```python
# scripts/v0302_e04_init_train_sensitivity.py

init_trains = [600, 700, 800, 900, 1000, 1200, 1500]

for init_train in init_trains:
    # 1. 完整 walk-forward
    preds = walk_forward_predict(X, y, config, init_train=init_train)

    # 2. 计算 IC + t-stat
    ic, p_val = non_overlapping_ic(preds, returns, step=21)
    monthly_ic = monthly_ic_series(preds, returns, dates, step=21)
    t_stat = newey_west_tstat(monthly_ic)  # 用 Newey-West！

    # 3. 计算特征/样本比
    feature_sample_ratio = n_features / init_train

    results.append({
        'init_train': init_train,
        'n_folds': n_folds,
        'n_non_overlap': n_samples,
        'test_years': test_years,
        'ic': ic,
        'p_val': p_val,
        'nw_t_stat': t_stat,
        'feature_sample_ratio': feature_sample_ratio,
        'positive_kappa_ratio': pos_kappa,
    })
```

**验收标准**：

| 结果 | 判定 |
|------|------|
| IC 在所有 init_train 下均 > 0.10 | ✅ alpha 对训练集长度鲁棒 |
| IC 在 init_train ≥ 1000 时消失 | ⚠️ 短训练集过拟合 |
| Newey-West t-stat 在所有配置下 > 2 | ✅ 统计显著性真实 |

**额外检查**：
- init_train=600 时 feature/sample = 148/600 = 24.7%（过高，预期过拟合）
- init_train=1500 时 feature/sample = 148/1500 = 9.9%（合理）
- 观察 IC 随 init_train 增大的变化曲线是否单调

**输出**：
- `experiments/weekly/v0302_validation/e04_init_train_sensitivity/sensitivity.csv`
- `experiments/weekly/v0302_validation/e04_init_train_sensitivity/ic_vs_init_train.png`
- `experiments/weekly/v0302_validation/e04_init_train_sensitivity/report.md`

**执行**：
```bash
python scripts/v0302_e04_init_train_sensitivity.py
```

---

## 四、P1 实验详细方案

### E05：Newey-West 调整 t-stat

**目的**：月度 IC 序列大概率有自相关，普通 t-test 高估显著性。

**方法**：
```python
# scripts/v0302_e05_newey_west.py

from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.regression.linear_model import OLS, newey_west

# 1. 计算月度 IC 序列
monthly_ic = monthly_ic_series(preds, returns, dates, step=21)

# 2. 检测自相关
lb_test = acorr_ljungbox(monthly_ic, lags=[1, 2, 3], return_df=True)
print("Ljung-Box 自相关检验:")
print(lb_test)

# 3. Newey-West 调整 t-stat
# H0: E[IC] = 0
model = OLS(monthly_ic, np.ones(len(monthly_ic)))
result = model.fit(cov_type='HAC', cov_kwds={'maxlags': 3})
nw_t_stat = result.tvalues[0]
nw_p_val = result.pvalues[0]

print(f"原始 t-stat:      {naive_t_stat:.4f}")
print(f"Newey-West t-stat: {nw_t_stat:.4f}")
```

**验收标准**：

| 结果 | 判定 |
|------|------|
| NW t-stat > 2 | ✅ 调整后仍显著 |
| 1.5 < NW t-stat < 2 | ⚠️ 边缘显著 |
| NW t-stat < 1.5 | ❌ 原始 t-stat 被自相关严重高估 |

**依赖**：`pip install statsmodels`（已在 requirements.txt 中）

**输出**：
- `experiments/weekly/v0302_validation/e05_newey_west/report.md`

**执行**：
```bash
python scripts/v0302_e05_newey_west.py
```

---

### E06：Bootstrap IC 置信区间

**目的**：量化 IC=0.65 的不确定性，给出 95% CI。

**方法**：
```python
# scripts/v0302_e06_bootstrap_ci.py

N_BOOT = 10000

# Non-overlapping (signal, return) pairs
pairs = list(zip(signals, returns))  # 58 个样本

boot_ics = []
for _ in range(N_BOOT):
    # 有放回抽样
    idx = np.random.choice(len(pairs), size=len(pairs), replace=True)
    boot_signals = [pairs[i][0] for i in idx]
    boot_returns = [pairs[i][1] for i in idx]
    ic, _ = spearmanr(boot_signals, boot_returns)
    boot_ics.append(ic)

# 95% CI (percentile method)
ci_lower = np.percentile(boot_ics, 2.5)
ci_upper = np.percentile(boot_ics, 97.5)

# Block bootstrap (保留时间结构)
BLOCK_SIZE = 4  # 4 个 non-overlapping periods ≈ 季度
for _ in range(N_BOOT):
    n_blocks = len(pairs) // BLOCK_SIZE + 1
    block_starts = np.random.choice(
        len(pairs) - BLOCK_SIZE + 1, size=n_blocks, replace=True
    )
    boot_idx = np.concatenate(
        [np.arange(s, s + BLOCK_SIZE) for s in block_starts]
    )[:len(pairs)]
    # ... 同上计算 IC
```

**验收标准**：

| 结果 | 判定 |
|------|------|
| 95% CI 下界 > 0.10 | ✅ IC 稳健为正 |
| 95% CI 包含 0 | ❌ IC 不可靠 |
| Block Bootstrap CI 比 IID Bootstrap 宽 > 50% | ⚠️ 时间依赖性严重 |

**输出**：
- `experiments/weekly/v0302_validation/e06_bootstrap_ci/ic_bootstrap.png`
- `experiments/weekly/v0302_validation/e06_bootstrap_ci/report.md`

**执行**：
```bash
python scripts/v0302_e06_bootstrap_ci.py
```

---

### E07：阈值敏感性测试

**目的**：验证 alpha 对 label 阈值参数不敏感。

**方法**：
```python
# scripts/v0302_e07_threshold_sensitivity.py

thresholds = [0.03, 0.04, 0.05, 0.06, 0.08, 0.10]

for X in thresholds:
    # 1. 用新阈值生成 label
    labels = generate_reversal_labels(df, T=21, X=X)
    labels = labels.map({0: 0, 1: 0, 2: 1})

    # 2. 完整 walk-forward
    preds = walk_forward_predict(features, labels, config)

    # 3. IC + 回测
    ic, p_val = non_overlapping_ic(preds, returns, step=21)
    metrics = backtest_strategy(preds, prices, step=21, ma_filter='triple')

    results.append({
        'threshold': X,
        'label_1_ratio': (labels == 1).mean(),
        'ic': ic, 'p_val': p_val,
        'sharpe': metrics['sharpe'],
        'max_dd': metrics['max_drawdown'],
    })
```

**验收标准**：

| 结果 | 判定 |
|------|------|
| 所有阈值 IC > 0.05 且 p < 0.10 | ✅ 参数鲁棒 |
| 仅 X=0.05 显著，其余不显著 | ❌ 过拟合到特定阈值 |
| IC 随阈值单调变化 | ⚠️ 可解释但需说明 |

**输出**：
- `experiments/weekly/v0302_validation/e07_threshold_sensitivity/sensitivity.csv`
- `experiments/weekly/v0302_validation/e07_threshold_sensitivity/report.md`

**执行**：
```bash
python scripts/v0302_e07_threshold_sensitivity.py
```

---

### E08：Horizon 敏感性测试

**目的**：验证 alpha 对预测窗口 T 不敏感。

**方法**：
```python
# scripts/v0302_e08_horizon_sensitivity.py

horizons = [7, 14, 21, 28, 42]

for T in horizons:
    # 1. 用新 horizon 生成 label
    labels = generate_reversal_labels(df, T=T, X=0.05)
    labels = labels.map({0: 0, 1: 0, 2: 1})

    # 2. Walk-forward (step = T，保持 non-overlapping)
    config_mod = config.copy()
    config_mod['evaluation']['step'] = T
    config_mod['evaluation']['oos_window'] = T * 3
    preds = walk_forward_predict(features, labels, config_mod)

    # 3. IC (step = T)
    ic, p_val = non_overlapping_ic(preds, returns, step=T)
```

**验收标准**：

| 结果 | 判定 |
|------|------|
| T=14/21/28 均 IC > 0.05 | ✅ 多 horizon 有效 |
| 仅 T=21 显著 | ❌ 过拟合到特定窗口 |

**注意**：不同 T 的 IC 不能直接比较绝对值（horizon 不同），主要看是否显著 > 0。

**输出**：
- `experiments/weekly/v0302_validation/e08_horizon_sensitivity/sensitivity.csv`
- `experiments/weekly/v0302_validation/e08_horizon_sensitivity/report.md`

**执行**：
```bash
python scripts/v0302_e08_horizon_sensitivity.py
```

---

### E09：多资产验证（ETHUSDT）

**目的**：验证 alpha 不是 BTCUSDT 特有的。

**方法**：
```python
# scripts/v0302_e09_eth_validation.py

# 1. 下载 ETHUSDT 日线数据
from src.data.downloader import download_binance_klines
download_binance_klines('ETHUSDT', '1d', '2018-01-01', '2025-12-31',
                        output='data/raw/btc_binance_ETHUSDT_1d.csv')

# 2. 用完全相同的配置（仅改 data path）
config_eth = config.copy()
config_eth['data']['path'] = 'data/raw/btc_binance_ETHUSDT_1d.csv'
config_eth['data']['symbol'] = 'ETHUSDT'

# 3. 完整 pipeline
df_eth = load_csv(config_eth['data']['path'])
df_eth = build_features(df_eth, config_eth['features']['sets'])
# ... 完整 walk-forward + IC

# 4. 对比
print(f"BTC IC: {btc_ic:.4f}")
print(f"ETH IC: {eth_ic:.4f}")
```

**验收标准**：

| 结果 | 判定 |
|------|------|
| ETH IC > 0.05 且 p < 0.10 | ✅ alpha 跨资产有效 |
| ETH IC ≈ 0 | ⚠️ alpha 可能是 BTC 特有的 |
| ETH IC 显著为负 | ❌ 模型无泛化能力 |

**前置依赖**：
- 需下载 ETHUSDT 1d 数据
- 部分特征（如 FGI）可能不适用于 ETH，需检查
- Funding Rate 数据需替换为 ETH 版本

**输出**：
- `data/raw/btc_binance_ETHUSDT_1d.csv`
- `experiments/weekly/v0302_validation/e09_eth_validation/report.md`

**执行**：
```bash
python scripts/v0302_e09_eth_validation.py
```

---

### E10：Bear Regime 详细报告

**目的**：验证 IC=-0.94 是信号还是小样本噪音。

**方法**：
```python
# scripts/v0302_e10_bear_regime_detail.py

# 1. Regime 定义 (与 v0301 一致)
df['regime'] = np.where(
    df['close'] > df['close'].rolling(200).mean(), 'bull',
    np.where(df['close'] < df['close'].rolling(200).mean() * 0.95,
             'bear', 'sideway')
)

# 2. 分 regime 统计
for regime in ['bull', 'bear', 'sideway']:
    mask = df_test['regime'] == regime
    n_samples = mask.sum()  # 总天数
    n_non_overlap = n_samples // 21  # non-overlapping 样本数

    # 具体时间段
    regime_dates = df_test.index[mask]
    date_ranges = find_continuous_ranges(regime_dates)

    # IC
    if n_non_overlap >= 5:
        ic, p_val = spearmanr(preds[mask_no], returns[mask_no])

    print(f"{regime}:")
    print(f"  总天数: {n_samples}")
    print(f"  Non-overlap 样本: {n_non_overlap}")
    print(f"  时间段: {date_ranges}")
    print(f"  IC: {ic:.4f} (p={p_val:.4f})")
```

**验收标准**：

| 结果 | 判定 |
|------|------|
| Bear non-overlap ≥ 15 且 IC < -0.3 | ✅ Bear IC 有统计意义 |
| Bear non-overlap < 10 | ⚠️ IC=-0.94 很可能是噪音 |
| Bear 仅覆盖 2022 单一时段 | ⚠️ 受单一事件主导 |

**输出**：
- `experiments/weekly/v0302_validation/e10_bear_regime_detail/report.md`

**执行**：
```bash
python scripts/v0302_e10_bear_regime_detail.py
```

---

## 五、P2 实验详细方案

### E11：分年 OOS

**目的**：排除 alpha 被 2022 或某一年的极端行情主导。

**方法**：
```python
# scripts/v0302_e11_yearly_oos.py

years = [2021, 2022, 2023, 2024, 2025]

for year in years:
    mask = (dates >= f'{year}-01-01') & (dates < f'{year+1}-01-01')
    if mask.sum() < 5:
        continue
    ic, p_val = spearmanr(preds[mask], returns[mask])
    metrics = backtest_strategy(preds[mask], prices[mask], step=21)
    # ...
```

**验收标准**：

| 结果 | 判定 |
|------|------|
| ≥ 3/5 年 IC > 0 | ✅ alpha 跨年有效 |
| 仅 1 年 IC >> 0，其余 ≈ 0 | ❌ alpha 由单一年份驱动 |

**输出**：
- `experiments/weekly/v0302_validation/e11_yearly_oos/yearly_breakdown.csv`
- `experiments/weekly/v0302_validation/e11_yearly_oos/report.md`

**执行**：
```bash
python scripts/v0302_e11_yearly_oos.py
```

---

### E12：特征 Ablation Study

**目的**：识别哪些特征集对 alpha 贡献最大，是否存在单一特征过拟合。

**方法**：
```python
# scripts/v0302_e12_feature_ablation.py

# 基线: 全部 6 个特征集
all_sets = ['technical', 'volume', 'flow', 'market_structure',
            'external_fgi', 'regime']

# Leave-one-out ablation
for drop_set in all_sets:
    remaining = [s for s in all_sets if s != drop_set]
    df_ablation = build_features(df_raw.copy(), remaining)
    # ... walk-forward + IC
    results.append({
        'dropped': drop_set,
        'n_features': len(feature_cols),
        'ic': ic,
        'sharpe': sharpe,
    })

# 最小特征集测试
minimal_sets = [
    ['technical'],
    ['technical', 'external_fgi'],
    ['technical', 'external_fgi', 'regime'],
]
for sets in minimal_sets:
    # ... 同上
```

**验收标准**：

| 结果 | 判定 |
|------|------|
| 删除任一特征集后 IC 仍 > 0.05 | ✅ 不依赖单一特征 |
| 删除 FGI 后 IC 消失 | ⚠️ alpha 主要来自 FGI |
| 仅 technical IC > 0.05 | ✅ 技术指标足以捕获信号 |

**输出**：
- `experiments/weekly/v0302_validation/e12_feature_ablation/ablation.csv`
- `experiments/weekly/v0302_validation/e12_feature_ablation/report.md`

**执行**：
```bash
python scripts/v0302_e12_feature_ablation.py
```

---

## 六、执行顺序与依赖

```
Phase 0: 基础设施
  └── scripts/v0302_utils.py (公共工具)

Phase 1: P0 毁灭性测试 (并行)
  ├── E01 随机标签 (独立)
  ├── E02 连续 IC  (独立)
  ├── E03 去 MA    (独立)
  └── E04 init_train (独立)

Phase 2: P1 统计验证 (依赖 Phase 1 通过)
  ├── E05 Newey-West  (独立)
  ├── E06 Bootstrap   (独立)
  ├── E07 阈值敏感性  (独立)
  ├── E08 Horizon     (独立)
  ├── E09 ETH 验证   (需下载数据)
  └── E10 Bear 详情  (独立)

Phase 3: P2 深度分析 (依赖 Phase 2)
  ├── E11 分年 OOS    (独立)
  └── E12 Ablation    (独立)

Phase 4: 汇总报告
  └── summary_report.md
```

**关键规则**：
- P0 的 4 个实验**任一失败**，则停止后续实验，回到 pipeline debug
- P1 的实验在 P0 全部通过后才有意义
- 所有实验均使用 `v0302_utils.py` 的公共函数，避免重复代码

---

## 七、脚本清单

| 脚本 | 状态 | 说明 |
|------|------|------|
| `scripts/v0302_utils.py` | 🔲 待创建 | 公共工具模块 |
| `scripts/v0302_e01_random_label.py` | 🔲 待创建 | 随机标签测试 |
| `scripts/v0302_e02_continuous_ic.py` | 🔲 待创建 | 纯收益排序 IC |
| `scripts/v0302_e03_no_ma.py` | 🔲 待创建 | 去 MA 纯模型测试 |
| `scripts/v0302_e04_init_train_sensitivity.py` | 🔲 待创建 | init_train 敏感性 |
| `scripts/v0302_e05_newey_west.py` | 🔲 待创建 | Newey-West 调整 |
| `scripts/v0302_e06_bootstrap_ci.py` | 🔲 待创建 | Bootstrap 置信区间 |
| `scripts/v0302_e07_threshold_sensitivity.py` | 🔲 待创建 | 阈值敏感性 |
| `scripts/v0302_e08_horizon_sensitivity.py` | 🔲 待创建 | Horizon 敏感性 |
| `scripts/v0302_e09_eth_validation.py` | 🔲 待创建 | 多资产验证 |
| `scripts/v0302_e10_bear_regime_detail.py` | 🔲 待创建 | Bear Regime 详情 |
| `scripts/v0302_e11_yearly_oos.py` | 🔲 待创建 | 分年 OOS |
| `scripts/v0302_e12_feature_ablation.py` | 🔲 待创建 | 特征 Ablation |

---

## 八、最终判定矩阵

当所有实验完成后，按以下矩阵做最终判定：

### 必须全部通过（P0）

| 条件 | 通过标准 | 结果 |
|------|---------|------|
| E01 随机标签 IC ≈ 0 | 100 次排列无一次 IC ≥ 真实 IC | 🔲 |
| E02 连续 IC > 0.05 | 纯收益排序有预测力 | 🔲 |
| E03 纯模型 Sharpe > 0.3 | 模型有独立 alpha | 🔲 |
| E04 IC 在多 init_train 下稳定 | 非人为扩大样本 | 🔲 |

### 至少 4/6 通过（P1）

| 条件 | 通过标准 | 结果 |
|------|---------|------|
| E05 NW t-stat > 2 | 调整后仍显著 | 🔲 |
| E06 95% CI 下界 > 0.10 | IC 稳健为正 | 🔲 |
| E07 ≥ 4/6 阈值 IC > 0.05 | 参数鲁棒 | 🔲 |
| E08 ≥ 3/5 horizon IC > 0 | 窗口鲁棒 | 🔲 |
| E09 ETH IC > 0.05 | 跨资产有效 | 🔲 |
| E10 Bear 样本 ≥ 15 | IC=-0.94 非噪音 | 🔲 |

### 最终判定

| P0 结果 | P1 结果 | 判定 |
|---------|---------|------|
| 4/4 ✅ | ≥ 4/6 ✅ | **Institutional Alpha** — 可部署 |
| 4/4 ✅ | 2-3/6 ✅ | **Conditional Alpha** — 需限制使用场景 |
| 3/4 ✅ | - | **Questionable** — 需进一步调查 |
| ≤ 2/4 ✅ | - | **No Alpha** — 回到研究阶段 |

---

## 九、风险与注意事项

1. **计算资源**：E01（100 次排列 walk-forward）和 E04（7 组 init_train）计算量较大，预估各需 1-2 小时
2. **ETH 数据**：E09 需要下载 ETHUSDT 数据，部分外部数据（FGI、Funding Rate）可能不适用，需处理
3. **实验独立性**：所有实验必须使用 v4 配置作为基线，不得交叉使用其他实验的结果
4. **结果记录**：每个实验完成后立即更新本文档第八节的判定矩阵
5. **Git 提交**：每完成一个实验，commit 一次，message 格式 `v0302: E0X <实验名> - <结果>`

---

*计划创建: 2026-02-20*
*基于: plans/v0301_report_review.md*
*版本: v0302*