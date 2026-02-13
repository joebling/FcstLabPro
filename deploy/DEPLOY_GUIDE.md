# FcstLabPro v6 — Google Cloud 部署指南

## 概览

| 项目 | 说明 |
|------|------|
| **模型版本** | v6 (reversal, T=14, X=0.05, SPW, 5特征集) |
| **预测目标** | 未来 14 天 BTC 价格是否出现 ≥5% 的大涨/大跌反转 |
| **调度频率** | 每天 08:00（北京时间） |
| **运行环境** | Google Cloud Run Job + Cloud Scheduler |
| **预估费用** | < $1/月（每天运行一次，约 30 秒完成） |

---

## 1. 数据源分析

### v6 唯一数据源：Binance 公开 API

| 字段 | 来源 | 说明 |
|------|------|------|
| `open` | Binance Klines API | 开盘价 |
| `high` | Binance Klines API | 最高价 |
| `low` | Binance Klines API | 最低价 |
| `close` | Binance Klines API | 收盘价 |
| `volume` | Binance Klines API | 成交量 (BTC) |
| `quote_volume` | Binance Klines API | 成交额 (USDT) |
| `trades` | Binance Klines API | 成交笔数 |

**API 端点**: `https://api.binance.com/api/v3/klines`
- ✅ **无需 API Key**（公开接口）
- ✅ **无需付费**
- ✅ **无频率限制问题**（每周只调一次）
- ✅ **全球可访问**（Cloud Run 在 GCP 网络内，延迟极低）

### 5 个特征集的数据依赖

| 特征集 | 输入字段 | 外部数据? | 说明 |
|--------|----------|-----------|------|
| `technical` | OHLCV | ❌ 无 | SMA/EMA/RSI/MACD/BB/ATR/动量/K-D 等 |
| `volume` | volume, quote_volume | ❌ 无 | 成交量均线/OBV/VWAP/量价相关性 |
| `flow` | volume, quote_volume, trades | ❌ 无 | 净买入估算/单笔成交/资金流强度/量价背离 |
| `sentiment` | OHLCV | ❌ 无 | FGI代理/GTrend代理/VIX代理（均为价格行为派生） |
| `market_structure` | OHLCV, quote_volume, trades | ❌ 无 | 模拟资金费率/OI代理/CVD/买入压力 |

> **结论：v6 所有特征均来自 Binance 日线 K线的 7 个字段，不依赖任何外部 API 或付费数据源。**

---

## 2. 架构图

```
┌─────────────────┐     每天 08:00 CST
│ Cloud Scheduler │─────────────────────┐
└─────────────────┘                     │
                                        ▼
                              ┌──────────────────┐
                              │  Cloud Run Job   │
                              │  (fcstlabpro-v6) │
                              └────────┬─────────┘
                                       │
                         ┌─────────────┼─────────────┐
                         ▼             ▼             ▼
                  ┌────────────┐ ┌──────────┐ ┌──────────┐
                  │ Binance    │ │ Bull v6  │ │ Bear v6  │
                  │ API (免费) │ │ model    │ │ model    │
                  └────────────┘ └──────────┘ └──────────┘
                         │             │             │
                         └─────────────┼─────────────┘
                                       ▼
                              ┌──────────────────┐
                              │   signal JSON    │
                              │ (Bull/Bear概率    │
                              │  + 仓位建议)      │
                              └────────┬─────────┘
                                       │
                         ┌─────────────┼─────────────┐
                         ▼             ▼             ▼
                   ┌──────────┐ ┌──────────┐ ┌──────────┐
                   │ GCS 存储 │ │ Webhook  │ │ 控制台   │
                   │ (可选)   │ │ 通知     │ │ 日志     │
                   └──────────┘ └──────────┘ └──────────┘
```

---

## 3. 部署步骤

### 3.1 前置条件

```bash
# 1. 安装 gcloud CLI
# https://cloud.google.com/sdk/docs/install

# 2. 登录
gcloud auth login

# 3. 创建/选择项目
gcloud projects create forecastlab-prod  # 或用现有项目
gcloud config set project forecastlab-prod

# 4. 启用计费
# https://console.cloud.google.com/billing
```

### 3.2 一键部署

```bash
cd /path/to/FcstLabPro

# 赋予执行权限
chmod +x deploy/gcloud_deploy.sh

# 部署（可选：配置 GCS 和通知）
export OUT_BUCKET="gs://your-bucket/signals"        # 可选
export NOTIFICATION_URL="https://hooks.slack.com/..." # 可选
./deploy/gcloud_deploy.sh
```

### 3.3 本地测试

```bash
# 不下载数据（用本地 CSV）
python scripts/weekly_signal.py

# 下载最新数据 + 保存信号
python scripts/weekly_signal.py --download --save

# Docker 本地测试
docker build -t fcstlabpro-v6 .
docker run --rm fcstlabpro-v6
```

---

## 4. 调度说明

| 参数 | 值 | 说明 |
|------|------|------|
| Cron 表达式 | `0 8 * * *` | 每天 |
| 时区 | `Asia/Shanghai` | 北京时间 08:00 |
| 超时 | 600s | 充足（通常 30s 完成） |
| 重试 | 2 次 | Binance API 偶尔超时 |

### 为什么选每天 08:00？

1. **Binance 日线收盘**: UTC 00:00 (北京时间 08:00)，刚好拿到完整的前一天日线数据
2. **每日更新**: 虽然预测窗口是 14 天，但每天跑可以捕捉最新市场状态变化，信号更及时
3. **早盘决策**: 08:00 出信号，可以在当天做出交易决策

---

## 5. 信号输出示例

```json
{
  "date": "2026-02-13",
  "price": 97029.99,
  "bull_prob": 0.456,
  "bear_prob": 0.412,
  "signal": "NEUTRAL",
  "signal_display": "⏸️ 震荡",
  "position_pct": 50,
  "action": "维持当前仓位，无需操作",
  "risk_level": "🟢 较低",
  "risk_notes": [
    "ℹ️ 两个方向的信号均较弱，模型信心不足",
    "📊 模型 Kappa≈0.05，预测力有限，仅作辅助参考"
  ],
  "model_version": "v6",
  "prediction_window": "14 days",
  "data_source": "Binance BTCUSDT 1d",
  "generated_at": "2026-02-13T21:52:00"
}
```

---

## 6. 运维手册

### 常用命令

```bash
# 手动触发
gcloud run jobs execute daily-btc-signal-v6 --region asia-east1

# 查看执行历史
gcloud run jobs executions list --job=daily-btc-signal-v6 --region=asia-east1

# 查看日志
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="daily-btc-signal-v6"' \
  --limit=50

# 暂停/恢复调度
gcloud scheduler jobs pause daily-btc-signal-trigger --location=asia-east1
gcloud scheduler jobs resume daily-btc-signal-trigger --location=asia-east1
```

### 更新模型

```bash
# 1. 训练新模型后，更新 Dockerfile 中的路径，或更新环境变量
# 2. 重新构建并推送镜像
gcloud builds submit --tag asia-east1-docker.pkg.dev/forecastlab-prod/fcstlabpro/fcstlabpro-v6:latest .

# 3. 更新 Job 镜像
gcloud run jobs update daily-btc-signal-v6 \
  --image asia-east1-docker.pkg.dev/forecastlab-prod/fcstlabpro/fcstlabpro-v6:latest \
  --region asia-east1
```

### 添加通知

在部署时设置环境变量即可：

```bash
# Slack Webhook
export NOTIFICATION_URL="https://hooks.slack.com/services/T00/B00/xxx"

# 飞书 Webhook
export NOTIFICATION_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"

# Telegram Bot (需要额外适配)
```

---

## 7. 费用估算

| 资源 | 单价 | 月用量 | 月费 |
|------|------|--------|------|
| Cloud Run Job | $0.00002400/vCPU·s | ~30次×30s = 900s | ~$0.022 |
| Cloud Run Job (内存) | $0.00000250/GiB·s | ~30次×30s×2GiB = 1800s | ~$0.005 |
| Cloud Build | 120分钟/天免费 | 极少 | $0 |
| Cloud Scheduler | 3个免费 | 1个 | $0 |
| Artifact Registry | 0.5GB免费 | <0.5GB | $0 |
| **合计** | | | **< $0.03/月** |

> 几乎免费。即使算上偶尔的手动测试触发，月费也不会超过 $1。

---

## 8. 与 ForecastLab 旧项目的差异

| 对比项 | ForecastLab (旧) | FcstLabPro v6 (新) |
|--------|-----------------|-------------------|
| 调度频率 | 每天 08:15 | 每天 08:00 |
| 预测窗口 | 1天/14天/21天 | 14 天 |
| 模型数 | 多个 candidate | 2个 (Bull + Bear) |
| 标签类型 | 多种 | reversal (T=14, X=0.05) |
| 数据源 | 相同 (Binance) | 相同 (Binance) |
| 输出格式 | CSV | JSON (更易集成) |
| GCP 项目 | forecastlab-prod | 复用同一项目 |
| Cloud Run Job | forecast-daily | daily-btc-signal-v6 |
