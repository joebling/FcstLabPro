# v0302 统一 Pipeline 重构方案

> 基于 v0301 实验报告 review 和架构讨论，解决三个核心问题：
> 1. 模型本质在"猜底"，Alpha 来自后置规则而非模型本身
> 2. Triple MA 是后置硬编码过滤器，应融入模型
> 3. Gemini 是信号美化器，没有增量信息

*创建日期: 2026-02-20*
*分支: refactor/v0302-unified-pipeline*

---

## 一、问题诊断

### 1.1 当前系统的 Alpha 归因

| 组件 | Sharpe 贡献 | 说明 |
|------|-------------|------|
| Orion-BiX 模型 | 0.70 (无过滤) | 模型本身的预测能力 |
| 信号反转 | 内含在 0.70 中 | 事后 hack，模型方向是反的 |
| Triple MA 过滤 | **+0.54** (0.70→1.24) | 人工规则贡献了 **43%** 的 Sharpe |
| Gemini LLM | 0 | 零 alpha，纯叙事包装 |

**结论**: 接近一半的 Sharpe 来自 bash 脚本里的一个 if/else。

### 1.2 当前 Pipeline 的五个结构性问题

#### 问题 ①：Label 语义错位

```
Label 定义:  P(未来21天跌幅 > 5%) → label=1
交易逻辑:  label=1 → 买入 (反转策略)
模型学到:  P(要跌了) = 高
实际使用:  P(要跌了) 高 → 买入
```

模型在预测"会不会跌"，但交易需要的是"跌完会不会弹"。这两个问题不等价：
- 熊市里跌 5% 之后可能再跌 20%
- 牛市回调 5% 之后大概率反弹

Triple MA 过滤器在帮模型补上这个缺失的判断。

#### 问题 ②：信号反转 = 承认模型方向错误

```python
# docker_entrypoint.sh 里的 inline Python
if invert_signal:
    bull_on = not bull_on  # 模型说涨 → 实际做空，模型说跌 → 实际做多
```

这不应该存在。如果模型方向是反的，说明 label 定义和交易逻辑之间有语义断裂。

#### 问题 ③：Triple MA 是事后选择的最优过滤器

A/B 测试了 4 种过滤器，选了最好的：

| 过滤器 | Sharpe |
|--------|--------|
| Triple MA | **1.24** ← 选了这个 |
| MA200 | 0.54 |
| Vol Filter | -0.29 |
| No Filter | 0.70 |

这是 **selection bias**：在策略空间中过拟合。

#### 问题 ④：Gemini 没有增量信息

Gemini 的输入（7天K线 + 技术指标）和模型的输入（148个技术特征）**完全重叠**。
Gemini 看不到任何模型看不到的东西（无链上数据、无新闻、无宏观）。
它的输出本质上是对模型信号的自然语言包装，增加虚假信心。

#### 问题 ⑤：200 行 Python 嵌入 bash heredoc

`docker_entrypoint.sh` 的 Step 1D 是 ~200 行 inline Python：
- 信号合并逻辑
- Triple MA 过滤
- Gemini 调用
- JSON 序列化

全部写在 `python3 - << 'PYEOF'` 里。无测试、无类型检查、改一行要重建镜像。

---

## 二、重构目标

| 目标 | 度量 | 标准 |
|------|------|------|
| 模型自身 Sharpe | 无后置过滤时 | > 1.0 |
| 消除信号反转 | 代码中不存在 invert | ✅ |
| MA 信息融入模型 | 作为特征而非过滤器 | ✅ |
| Gemini 增量价值 | 提供模型看不到的信息 | ✅ |
| 工程质量 | 无 inline Python in bash | ✅ |
| IC t-stat | 无后置过滤 | > 2 |

---

## 三、重构方案

### Phase 1: Label 重新定义（核心）

**目标**: 让模型直接回答"该不该买"，而不是"会不会跌"。

#### 方案 A：风险调整收益 Label（推荐）

```python
# 当前 label（有语义错位）
label = 1 if min_return_21d < -0.05 else 0  # "会不会跌 5%"

# 新 label：直接预测收益方向
# 方案 A1: 简单正负收益
label = 1 if forward_return_21d > 0 else 0  # "21天后是涨还是跌"

# 方案 A2: 超额收益（推荐）
# 用 rolling mean return 作为基准，预测是否跑赢
rolling_mean = df['return_21d'].rolling(63).mean()
label = 1 if forward_return_21d > rolling_mean else 0  # "是否跑赢近期均值"

# 方案 A3: 回归（最直接）
label = forward_return_21d  # 直接预测收益率，用回归模型
```

**为什么 A2 最好**：
- 消除了"预测跌幅"和"决定买入"之间的语义断裂
- 不需要信号反转
- 模型直接学习"什么情况下未来收益高于平均"
- rolling baseline 自适应 regime

#### 方案 B：Dip-and-Recovery Label

如果你坚持做反转策略，label 应该同时编码"跌"和"弹"：

```python
# 当前: 只看跌幅
label = 1 if min_return_21d < -0.05 else 0

# 改进: 跌了之后要弹回来才算 1
dip = (df['low'].rolling(21).min().shift(-21) - df['close']) / df['close']
recovery = (df['close'].shift(-21) - df['low'].rolling(21).min().shift(-21)) / df['low'].rolling(21).min().shift(-21)

label = 1 if (dip < -0.05) and (recovery > 0.03) else 0
# "未来21天先跌5%以上，然后从低点反弹3%以上"
```

**好处**: 模型需要同时学会识别"会跌"和"跌完会弹"，不需要外部 MA 过滤。

#### 方案 C：回归 + 分位数

```python
# 直接预测未来21天收益率
y = forward_return_21d  # 连续值

# 模型输出收益率预测
pred_return = model.predict(X)

# 交易规则: 预测收益率 > 某阈值时买入
buy_signal = pred_return > threshold  # threshold 通过 CV 确定
```

**好处**: 最简洁，无分类边界问题，IC 直接有意义。

### Phase 2: Triple MA 融入模型

**目标**: 让模型自己学会"什么时候该抄底，什么时候不该"。

#### 2.1 构造交互特征

```python
def add_ma_regime_features(df):
    """将 Triple MA 逻辑转化为模型特征."""
    # 已有特征
    # price_vs_sma_50, price_vs_sma_200, sma_cross_50_200

    # 新增: Triple MA 对齐状态
    df['triple_ma_aligned'] = (
        (df['close'] > df['sma_50']) &
        (df['sma_50'] > df['sma_100']) &
        (df['sma_100'] > df['sma_200'])
    ).astype(int)

    # MA 排列强度 (连续值，比 0/1 更有信息)
    df['ma_alignment_score'] = (
        (df['close'] - df['sma_50']) / df['sma_50'] +
        (df['sma_50'] - df['sma_100']) / df['sma_100'] +
        (df['sma_100'] - df['sma_200']) / df['sma_200']
    ) / 3

    # MA50 动量 (原 Triple MA 的 ma50_up 条件)
    df['ma50_momentum_5d'] = df['sma_50'].pct_change(5)
    df['ma50_momentum_10d'] = df['sma_50'].pct_change(10)

    # 价格离 MA 的标准化距离
    df['price_ma50_zscore'] = (
        (df['close'] - df['sma_50']) /
        df['close'].rolling(50).std()
    )

    # MA 扇形展开/收敛
    df['ma_spread'] = (df['sma_50'] - df['sma_200']) / df['sma_200']
    df['ma_spread_change'] = df['ma_spread'].diff(5)

    return df
```

#### 2.2 验证实验

```bash
# 实验: 对比有无 MA 交互特征的模型
python scripts/run_experiment.py \
    --features baseline           # 原 148 特征
    --label new_label_A2           # 新 label
    --name v0302_baseline

python scripts/run_experiment.py \
    --features baseline+ma_regime  # 148 + MA 交互特征
    --label new_label_A2
    --name v0302_ma_integrated

# 对比: 两个模型都不用后置 MA 过滤
# 如果 ma_integrated 版本的 Sharpe > baseline，说明模型学会了 MA 信息
```

#### 2.3 成功标准

| 指标 | 当前 (模型+后置MA) | 目标 (模型内置MA) |
|------|-------------------|------------------|
| Sharpe (无后置过滤) | 0.70 | > 1.0 |
| Sharpe (有后置过滤) | 1.24 | N/A (不再需要) |
| IC (无后置过滤) | 未测 | > 0.05 |
| IC t-stat | 4.75 (含过滤) | > 2 (纯模型) |

### Phase 3: Gemini 角色重新定义

**目标**: Gemini 提供模型看不到的增量信息，或者去掉。

#### 方案 A：增量信息注入（推荐）

```python
# 新的 Gemini system prompt
SYSTEM_PROMPT = """
你是一位加密货币风险分析师。你的任务不是解读模型信号，
而是提供模型看不到的外部信息。

模型只看技术面特征，不包含：
- 宏观经济事件 (FOMC、CPI、非农)
- 监管政策变动
- 重大链上事件 (交易所暴雷、大额转账)
- 市场情绪极端事件

你的输出格式：
1. 【外部风险】: 未来 7 天是否有模型看不到的重大风险事件
2. 【信心调整】: 基于外部信息，模型信号的可信度是否需要调整
   - 维持 / 降低 / 大幅降低
3. 【理由】: 一句话说明

不要重复模型已经知道的技术面信息。
不要给出具体的入场/止损/目标位。
"""
```

#### 方案 B：去掉 Gemini

如果不能提供增量信息（Gemini 在 Cloud Run 里也不能联网搜索新闻），那就去掉。
邮件里直接放：

```
信号: BULL | 置信度: 中 | Kappa: 0.12
⚠️ 模型仅基于技术面，不含宏观/链上数据，仅供参考。
```

比 250 字的 AI 编故事更诚实。

#### 方案 C：Gemini 做信号置信度校准

```python
# 基于历史 regime 的置信度校准
USER_PROMPT = """
以下是模型信号和当前市场状态。

模型历史表现:
- Bull regime IC: -0.37 (不显著)
- Bear regime IC: -0.94 (极强)
- Sideway regime IC: 样本不足

当前状态:
- Regime: {current_regime}
- 模型信号: {signal}

请判断：基于模型在当前 regime 下的历史表现，
这个信号的可信度是 高/中/低？
"""
```

### Phase 4: 工程重构

**目标**: 消除 inline Python in bash，统一为可测试的 Python pipeline。

#### 4.1 新的目录结构

```
FcstLabPro/
├── src/
│   ├── data/
│   │   └── downloader.py          # 已有
│   ├── features/
│   │   ├── technical.py           # 从 run_orion_experiment.py 提取
│   │   └── ma_regime.py           # 新增: MA 交互特征
│   ├── labels/
│   │   └── label_factory.py       # 新增: 统一 label 定义
│   ├── models/
│   │   └── predictor.py           # 新增: 统一预测接口
│   ├── signals/
│   │   └── signal_generator.py    # 新增: 概率 → 信号 (无后置过滤)
│   ├── llm/
│   │   └── analyst.py             # 重构: 增量信息模式
│   └── pipeline/
│       └── daily_pipeline.py      # 新增: 替代 docker_entrypoint.sh 中的 inline Python
├── scripts/
│   └── docker_entrypoint.sh       # 简化: 只调用 python -m src.pipeline.daily_pipeline
└── tests/
    ├── test_label_factory.py
    ├── test_signal_generator.py
    └── test_daily_pipeline.py
```

#### 4.2 docker_entrypoint.sh 简化目标

```bash
#!/usr/bin/env bash
# 重构后的 entrypoint: 干净、简洁、可读
set -euo pipefail

echo "🔮 FcstLabPro v0302 — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"

# 所有逻辑在 Python 中
python -m src.pipeline.daily_pipeline \
    --bull-dir "${BULL_DIR}" \
    --bear-dir "${BEAR_DIR}" \
    --out-dir "${OUT_DIR:-/tmp/signals}"

# 上传 (可选)
if [ -n "${OUT_BUCKET:-}" ]; then
    gsutil -m cp "${OUT_DIR}"/signal_*.json "${OUT_BUCKET%/}/"
fi

echo "🎉 完成"
```

从 300+ 行 → **15 行**。

---

## 四、实验计划

### 实验 1: Label 对比实验

| 实验 | Label | 信号反转 | MA 过滤 |
|------|-------|---------|--------|
| E1-baseline | 原始 (跌幅>5%) | 有 | 有 (后置) |
| E1-A1 | 正负收益 | 无 | 无 |
| E1-A2 | 超额收益 | 无 | 无 |
| E1-B | Dip+Recovery | 无 | 无 |
| E1-C | 回归 | N/A | 无 |

**验收**: 找到一个无需信号反转、无需后置 MA 过滤，Sharpe > 1.0 的 label。

### 实验 2: MA 特征融合实验

| 实验 | 特征集 | 后置 MA |
|------|--------|--------|
| E2-baseline | 原始 148 | 有 |
| E2-ma_feat | 148 + MA 交互特征 | 无 |
| E2-ma_feat_filtered | 148 + MA 交互特征 | 有 (对比用) |

**验收**: E2-ma_feat 的 Sharpe ≥ E2-baseline (含后置 MA) 的 Sharpe。

### 实验 3: Gemini 增量价值验证

| 实验 | Gemini 模式 | 度量 |
|------|-------------|------|
| E3-none | 无 Gemini | 基准 |
| E3-narrative | 当前模式 (叙事) | 用户调查 |
| E3-risk | 增量风险模式 | 是否避开了重大事件 |

**验收**: E3-risk 在重大事件期间的回撤 < E3-none。

---

## 五、执行顺序

```
Phase 1: Label 重定义 (1-2 天)
  ├─ 实现 label_factory.py (A1/A2/B/C 四种 label)
  ├─ 跑 Walk-Forward 对比实验
  └─ 选出最优 label

Phase 2: MA 特征融合 (1 天)
  ├─ 实现 ma_regime.py
  ├─ 跑对比实验
  └─ 验证无后置过滤时 Sharpe > 1.0

Phase 3: Pipeline 重构 (1 天)
  ├─ 提取 inline Python → signal_generator.py + daily_pipeline.py
  ├─ 简化 docker_entrypoint.sh
  └─ 写测试

Phase 4: Gemini 重定义 (0.5 天)
  ├─ 重写 system prompt (增量信息模式)
  └─ 或决定去掉

Phase 5: 集成验证 (0.5 天)
  ├─ E2E 测试
  ├─ Docker build + 本地运行
  └─ 对比 v0301 指标
```

---

## 六、风险与回退

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 新 label 性能不如旧的 | 无法上线 | 保留 v0301 作为 fallback |
| MA 特征融合后模型过拟合 | Sharpe 下降 | 监控 OOS IC，特征选择 |
| 去掉 Gemini 用户不满 | 体验下降 | 方案 C (置信度校准) 作为折中 |
| 重构引入 bug | 信号错误 | 对比测试：新旧 pipeline 输出一致性 |

---

## 七、成功定义

### 最低标准 (Must Have)

- [ ] 消除信号反转 (`invert_signal` 不再存在)
- [ ] 消除后置 MA 过滤 (模型自身 Sharpe > 1.0)
- [ ] inline Python 从 bash 中提取到独立模块
- [ ] IC t-stat > 2 (纯模型，无后置处理)

### 理想标准 (Nice to Have)

- [ ] 统一 Bull/Bear 为单一模型 (同算法、同 horizon)
- [ ] Gemini 提供可验证的增量价值
- [ ] 完整测试覆盖 (label、signal、pipeline)
- [ ] 模型自身 Sharpe > 1.5

---

## 八、方案评估（客观分析）

### 8.1 做得好的部分

| 优点 | 说明 |
|------|------|
| **问题定位准确** | 5个结构性问题诊断清晰，核心痛点抓得准 |
| **方案有层次** | Label → MA → Gemini → 工程，逻辑递进清晰 |
| **有实验验证** | 每个改进都有对照实验设计，不是拍脑袋 |
| **有回退方案** | 保留 v0301 作为 fallback，风险意识好 |

### 8.2 需要质疑的部分

#### 1. 目标过于乐观

| 目标 | 当前 | 预期 | 评估 |
|------|------|------|------|
| Sharpe (无MA) | 0.21 | >1.0 | **可能达不到** |

**分析**：
- v0303 实验结论：纯模型 Sharpe 仅 0.21
- 改 Label + 加 MA 特征后，Sharpe 就能翻 5 倍？
- 建议调整为 ">0.5" 更现实

#### 2. Alpha 归因可能有问题

```
当前: 模型 0.70 + Triple MA +0.54 = 1.24
```

**问题**：
- 0.70 是用"预测跌幅"的 label 算的
- 如果换成"预测收益"的 label，基准线就不是 0.70 了
- 新 label 可能让模型完全换个味道

#### 3. Label 方案的隐患

| 方案 | 问题 |
|------|------|
| A1: 正负收益 | 类别严重不平衡（BTC 长期牛市）|
| A2: 超额收益 | rolling mean 本身有 regimes，又引入新问题 |
| B: Dip+Recovery | 样本极少，模型学不到 |
| C: 回归 | IC 直接有意义，但偏离了二分类框架 |

#### 4. MA 特征融合是"头痛医头"

```python
# 原来: 后置 if/else
if triple_ma_aligned: 执行交易

# 现在: 特征工程
df['triple_ma_aligned'] = ...
```

**本质**：只是把 hard code 换成了特征，模型学不学得会是另一回事。

#### 5. Gemini 方案不现实

方案 A 要求 Gemini "提供模型看不到的信息"，但：
- Cloud Run 环境无法联网
- Gemini 训练数据有时效性
- "验证增量价值"很难量化

### 8.3 客观评级

| 维度 | 评分 | 说明 |
|------|------|------|
| **问题诊断** | ⭐⭐⭐⭐⭐ | 5个问题抓得准 |
| **方案设计** | ⭐⭐⭐☆☆ | 有层次但部分不现实 |
| **可行性** | ⭐⭐⭐☆☆ | 目标偏高，需调整 |
| **风险意识** | ⭐⭐⭐⭐☆ | 有回退方案 |
| **完整性** | ⭐⭐⭐⭐☆ | 覆盖全面 |

**综合评分**：⭐⭐⭐⭐ (4/5) — **良好，但需下调预期**

### 8.4 建议修改

1. **目标调整**：
   - Sharpe 目标从 ">1.0" 改为 ">0.5"
   - IC 目标从 ">0.05" 改为 ">0.03"

2. **Label 方案**：
   - 先做 A1（简单正负）验证可行性
   - A2 作为进阶，不要一开始就用

3. **MA 特征**：
   - 不要预期过高，当作"锦上添花"
   - 保留后置 MA 作为 fallback

4. **Gemini**：
   - 直接选方案 B（去掉）或简化
   - 不要花时间验证"增量价值"

---

## 九、实验落地计划

### 9.1 调整后的目标

| 指标 | 原目标 | 调整后 | 说明 |
|------|--------|--------|------|
| Sharpe (纯模型) | >1.0 | >0.5 | 更现实 |
| IC | >0.05 | >0.03 | 考虑类别不平衡 |
| IC t-stat | >2 | >1.5 | 放宽要求 |

### 9.2 实验清单

#### 实验 R1: Label 基础验证（优先）

```
目标: 验证 A1/A2/B/C 哪种 label 更有潜力

步骤:
1. 实现 label_factory.py (支持 A1/A2/B/C 四种 label)
2. 用原 148 特征 + 新 label 跑 walk-forward
3. 记录每种 label 的: IC, IC t-stat, Sharpe (无 MA)
4. 选出 top 2 进入下一轮

验收标准:
- 任一 label 的 IC t-stat > 1.5
- Sharpe > 0.3 (无 MA)

时间: 1-2 天
```

#### 实验 R2: MA 特征融合

```
目标: 验证 MA 特征能否提升纯模型表现

步骤:
1. 用 R1 选出的最优 label
2. 对比: 148 特征 vs 148+MA特征
3. 两种都不加后置 MA 过滤

验收标准:
- MA特征版本的 Sharpe ≥ 无MA特征版本
- 或 MA特征版本的 IC 提升 > 10%

时间: 1 天
```

#### 实验 R3: 后置 MA 的边际贡献

```
目标: 确定是否还需要后置 MA

步骤:
1. 用 R2 的最优配置
2. 对比: 有后置 MA vs 无后置 MA

验收标准:
- 无后置 MA Sharpe > 0.5 → 可考虑去掉 MA
- 无后置 MA Sharpe < 0.3 → 保留后置 MA

时间: 0.5 天
```

#### 实验 R4: 简化 Gemini

```
目标: 确定 Gemini 的处理方式

方案:
A. 直接去掉，只保留信号 + 指标
B. 保留但简化 prompt，只做置信度提示

时间: 0.5 天
```

#### 实验 R5: 工程重构

```
目标: 消除 inline Python

步骤:
1. 提取 signal_generator.py
2. 提取 daily_pipeline.py
3. 简化 docker_entrypoint.sh
4. 对比测试: 新旧输出完全一致

验收标准:
- 新旧信号输出 100% 一致
- docker_entrypoint.sh < 50 行

时间: 1 天
```

### 9.3 执行顺序

```
Week 1:
├── Day 1-2: 实验 R1 (Label 基础验证)
│   └── 输出: 最优 label 候选
├── Day 3: 实验 R2 (MA 特征融合)
│   └── 输出: 是否需要 MA 特征
├── Day 4: 实验 R3 (后置 MA 边际贡献)
│   └── 输出: 是否保留后置 MA
└── Day 5: 实验 R4 (Gemini 简化)
    └── 输出: Gemini 处理方案

Week 2:
├── Day 1-2: 实验 R5 (工程重构)
│   └── 输出: 可测试的模块
└── Day 3-5: 集成测试 + 部署验证
```

### 9.4 决策节点

| 节点 | 条件 | 决策 |
|------|------|------|
| R1 后 | 无 label IC t-stat > 1.5 | 回退，用原 v0301 |
| R2 后 | MA 特征无效 | 只用原特征 |
| R3 后 | 无后置 MA Sharpe < 0.3 | 保留后置 MA |
| R5 后 | 新旧输出不一致 | 回退，检查原因 |

### 9.5 成功标准（修订版）

#### 最低标准 (Must Have)

- [ ] 存在一种 label 的 IC t-stat > 1.5
- [ ] 纯模型 Sharpe > 0.3 (无后置 MA)
- [ ] inline Python 从 bash 中提取到独立模块

#### 理想标准 (Nice to Have)

- [ ] 纯模型 Sharpe > 0.5 (无后置 MA)
- [ ] IC t-stat > 2 (纯模型)
- [ ] 去掉后置 MA 后 Sharpe 下降 < 30%

---

*评估日期: 2026-02-20*
*基于: v0302 实验结论*

*方案作者: sam 🐶 + Qiu*
*核心洞察: Alpha 来自后置规则，不是模型*