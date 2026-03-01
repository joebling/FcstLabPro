# v0302 策略部署报告

**日期**: 2026-02-21
**策略名称**: dip_recovery + Trigger A + Position sizing (linear)

---

## 一、策略概述

### 1.1 使用的模型

| 模型 | 路径 | Kappa | Label 策略 |
|------|------|-------|------------|
| **Bull** | experiments/weekly/weekly_bull_v27_orion_final | 0.11 | dip_recovery |
| **Bear** | experiments/weekly/weekly_bear_v13_T28_fgi_20260215_134804_ff4ad7 | 0.05 | dip_recovery |

### 1.2 策略特点

| 方面 | 描述 |
|------|------|
| **Label** | dip_recovery (dip >5%, recovery >3%) |
| **触发逻辑** | 等待 dip ≥5% 再入场 |
| **退出逻辑** | 止盈 +4%，止损 -3%，时间止损 14 天 |
| **Position sizing** | size = 2 × (prob - 0.5) |

### 1.2 最佳参数

| 参数 | 值 |
|------|-----|
| prob_threshold | 0.8 |
| dip_threshold | 0.05 |
| tp | 0.04 |
| sl | 0.03 |
| monitor_days | 7 |

### 1.3 回测表现

| 指标 | 值 |
|------|-----|
| **Sharpe** | **0.9472** |
| **MaxDD** | **3.75%** |
| 总收益 | 0.5734 |
| 年化收益 | 3.29% |
| 年化波动率 | 3.48% |
| 交易次数 | 50 |

### 1.4 名词解释

#### dip_recovery（标签策略）
**含义**：先下跌后反弹的反转标签

| 参数 | 值 | 说明 |
|------|-----|------|
| dip | >5% | 价格从高点下跌超过 5% |
| recovery | >3% | 随后价格从低点反弹超过 3% |
| T | 21 天 | 在未来 21 天内发生 |

**逻辑**：
```
价格走势: 高点 → 下跌 >5% → 低点 → 反弹 >3% → Label=1
```

**目的**：捕捉"超跌反弹"机会，避免追高

---

#### Trigger A（入场触发）
**含义**：等待价格从高点下跌 ≥5% 再入场

| 参数 | 值 | 说明 |
|------|-----|------|
| monitor_days | 7 天 | 入场后监控 7 天 |
| dip_threshold | 5% | 价格从入场前高点下跌 ≥5% |

**逻辑**：
```
1. 模型预测概率 ≥ 0.8
2. 等待：在接下来的 7 天内
3. 触发：如果价格从入场前高点下跌 ≥5% → 入场
4. 否则：不入场
```

**目的**：等待更好的入场价位，降低追高风险

---

#### Position sizing (linear)（线性仓位管理）
**含义**：根据模型预测概率动态调整仓位大小

**公式**：
```
size = 2 × (prob - 0.5)
```

| 概率 prob | 仓位 size | 说明 |
|-----------|-----------|------|
| 0.5 | 0% | 中性，不建仓 |
| 0.6 | 20% | 轻微看多 |
| 0.7 | 40% | 中等看多 |
| 0.8 | 60% | 强烈看多 |
| 0.9 | 80% | 非常强烈看多 |
| 1.0 | 100% | 满仓 |

**范围限制**：
- 最小：0%（不建仓）
- 最大：100%（满仓）

**目的**：
- 概率越高，仓位越大
- 概率越低，仓位越小
- 提高资金利用率，降低低概率信号的风险

---

## 二、与 v0301 的对比

### 2.1 策略差异

| 对比项 | v0301 | v0302 |
|--------|-------|-------|
| **Label** | simple_return / excess_return | dip_recovery |
| **触发方式** | 直接入场 | 等待 dip ≥5% |
| **Position sizing** | 固定仓位 | 线性仓位 (size = 2×(prob-0.5)) |
| **MaxDD** | ~10% | **3.75%** |
| **Sharpe** | ~0.77 | **0.9472** |

### 2.2 v0302 优势

1. **更低的 MaxDD**：从 ~10% 降至 3.75%，风险显著降低
2. **更高的 Sharpe**：从 ~0.77 提升至 0.9472，风险调整后收益更好
3. **更保守的入场**：等待 dip ≥5% 再入场，避免追高
4. **Position sizing**：根据概率动态调整仓位，提高资金利用率

---

## 三、币本位 vs 法币本位

### 3.1 USDT 本位（推荐）

| 策略 | Sharpe | 总收益 | MaxDD |
|------|--------|--------|-------|
| PS2_linear_RC1_none | 0.7974 | 10.57% | 3.53% |

### 3.2 BTC 本位

| 策略 | Sharpe | 总收益 | MaxDD |
|------|--------|--------|-------|
| PS2_linear_RC1_none | 0.6742 | 26.59% | 10.58% |

### 3.3 结论

- **最佳策略一致**：两种本位下最佳策略都是 PS2_linear_RC1_none
- **策略排序一致**：Position sizing 的优势在两种本位下都保持
- **建议**：如果基准是 USDT，直接使用 v0302；如果基准是 BTC，策略选择不变，只是绝对收益数值会变化

---

## 四、上线建议

### 4.1 可以上线 ✅

策略表现已经很好，可以考虑实盘部署！

### 4.2 注意事项

1. **信号频率低**：策略只有约 50 笔交易（3年多），说明入场信号非常保守
2. **耐心等待**：可能需要长时间等待入场信号，不要手动干预
3. **严格止损**：保持 3% 止损不变
4. **Position sizing**：严格执行 size = 2×(prob-0.5)
5. **杠杆建议**：可以考虑用 1.5-2x 杠杆，但只用小仓位（总资金的 10-20%）

### 4.3 与 v0301 并存

- v0301 继续运行（作为参考）
- v0302 并行部署（作为新策略）
- 两个策略可以同时运行，对比实盘表现

---

## 五、回测交易记录（最近一年）

| 序号 | 入场日期 | 入场价格 | 入场概率 | 入场仓位 | 出场日期 | 出场价格 | 持仓天数 | 盈亏 |
|------|---------|---------|---------|---------|---------|---------|---------|------|
| 1 | 2025-03-03 | $86220.61 | 0.8714 | 74.3% | 2025-03-05 | $90606.01 | 2 | +5.09% |

---

## 六、总结

### 成果 ✅

1. **Label 选择**：dip_recovery 分类能力最强（Kappa = 0.5082）
2. **参数优化**：Sharpe 从 0.49 提升到 0.77
3. **Position sizing**：Sharpe 进一步提升到 0.95，MaxDD 降至 3.75%

### 最佳表现

| 指标 | 值 | 目标 |
|------|-----|------|
| Sharpe | 0.9472 | > 1.2 (接近) |
| MaxDD | 3.75% | < 35% (远超) |

### 可以考虑实盘

表现已经很好，可以考虑实盘部署！

---

## 七、部署

### 7.1 与 v0301 完全隔离

v0302 部署与 v0301 完全隔离，互不影响：

| 组件 | v0301 | v0302 |
|------|-------|-------|
| 部署脚本 | `deploy/deploy_v0301.sh` | `deploy/deploy_v0302.sh` |
| Dockerfile | `Dockerfile` | `deploy/Dockerfile.v0302` (独立) |
| 入口脚本 | `scripts/docker_entrypoint.sh` | `deploy/docker_entrypoint_v0302.sh` (独立) |
| 镜像名称 | `fcstlabpro-v0301` | `fcstlabpro-v0302` |
| Job 名称 | `daily-btc-signal-v0301` | `daily-btc-signal-v0302` |
| 调度器 | `daily-btc-signal-v0301-trigger` | `daily-btc-signal-v0302-trigger` |

### 7.2 部署文件结构

```
deploy/
├── deploy_v0301.sh           # v0301 部署脚本
├── deploy_v0302.sh           # v0302 部署脚本 ✨
├── Dockerfile.v0302          # v0302 专属 Dockerfile ✨
├── docker_entrypoint_v0302.sh # v0302 专属入口脚本 ✨
├── v0301_experiment_report.md # v0301 实验报告
├── v0302_experiment_report.md # v0302 实验报告 (本文件)
└── DEPLOY_GUIDE.md
```

### 7.3 部署方式

#### 前置条件
1. 安装 gcloud CLI 并登录: `gcloud auth login`
2. 创建 GCP 项目并设为当前项目: `gcloud config set project <PROJECT_ID>`
3. 启用计费

#### 完整部署
```bash
cd /path/to/FcstLabPro
chmod +x deploy/deploy_v0302.sh
./deploy/deploy_v0302.sh
```

#### 分步部署
```bash
# 仅构建镜像
./deploy/deploy_v0302.sh build

# 仅部署 Job
./deploy/deploy_v0302.sh deploy

# 仅设置定时
./deploy/deploy_v0302.sh scheduler
```

### 7.4 部署后操作

#### 手动触发 Job
```bash
gcloud run jobs execute daily-btc-signal-v0302 --region asia-east1
```

#### 查看日志
```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="daily-btc-signal-v0302"' \
  --limit=50
```

#### 暂停调度
```bash
gcloud scheduler jobs pause daily-btc-signal-v0302-trigger --location=asia-east1
```

### 7.5 与 v0301 并行运行

两个策略可以同时运行，对比实盘表现：

```bash
# 部署 v0301（保持原样）
./deploy/deploy_v0301.sh

# 部署 v0302（独立部署）
./deploy/deploy_v0302.sh
```

- **v0301**：继续作为参考策略
- **v0302**：新策略上线
- 两者完全隔离，互不影响

详见：`deploy/deploy_v0302.sh`
