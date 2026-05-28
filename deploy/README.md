# deploy/ — FcstLabPro 部署指南

> **模型无关架构**: 所有模型共享同一套镜像、入口脚本和部署流程，仅通过 `MODEL_NAME` 环境变量切换。

---

## 目录结构

```
deploy/
├── README.md                 ← 本文件
├── Dockerfile                ← 通用镜像（所有模型共享）
├── deploy.sh                 ← 一键部署脚本（build / deploy / scheduler）
├── docker_entrypoint.sh      ← 容器入口（8 步流水线）
└── archive/                  ← 历史版本存档（v0215 ~ v0305）
```

## 架构全景

```
┌────────────────────────────────────────────────┐
│  Cloud Scheduler (每天 UTC 00:05)             │
│  trigger-<MODEL_NAME>                          │
└───────────────────────┬────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────┐
│  Cloud Run Job                                  │
│  daily-btc-signal-<MODEL_NAME>                  │
│  ┌────────────────────────────────────────────┐│
│  │ docker_entrypoint.sh                        ││
│  │                                              ││
│  │ 1. 下载 Binance BTCUSDT 日线数据          ││
│  │ 2. 从 GCS 恢复持仓状态                   ││
│  │ 3. live_signal.py → 模型推理             ││
│  │ 4. 保存持仓状态到 GCS                    ││
│  │ 5. build_signal_json.py → 信号 JSON      ││
│  │ 6. enrich_llm_analysis.py (可选 Gemini)   ││
│  │ 7. send_signal_email.py → QQ 邮箱         ││
│  │ 8. 上传信号 JSON 到 GCS 归档             ││
│  └────────────────────────────────────────────┘│
└────────────────────────────────────────────────┘
        │                       │
        ▼                       ▼
   📧 QQ 邮箱              ☁️ GCS Bucket
   (smtp.qq.com)         gs://...
```

---

## 快速开始

### 前置条件

- `gcloud` CLI 已安装并登录
- GCP 项目已开通 Cloud Run / Artifact Registry / Cloud Scheduler
- 模型目录已就绪（见下方「新模型上线」）

### 一键部署

```bash
# 部署 E1 保守版（完整流程: 构建镜像 + 部署 Job + 设置定时）
MODEL_NAME=e1-conservative ./deploy/deploy.sh

# 部署 E8
MODEL_NAME=e8-touch ./deploy/deploy.sh
```

### 分步执行

```bash
# 仅构建镜像（所有模型共享，只需构建一次）
MODEL_NAME=e1-conservative ./deploy/deploy.sh build

# 仅部署 Cloud Run Job
MODEL_NAME=e1-conservative ./deploy/deploy.sh deploy

# 仅设置定时调度
MODEL_NAME=e1-conservative ./deploy/deploy.sh scheduler
```

---

## 新模型上线流程

### Step 1: 准备模型目录

```
models/production/<MODEL_NAME>/
├── model.joblib        # 训练完成的模型文件
├── config.yaml         # 实验配置（特征列表、标签参数 T/X）
└── manifest.json       # 模型元信息（Kappa、CAGR、策略参数等）
```

### Step 2: 部署

```bash
MODEL_NAME=<新模型名> ./deploy/deploy.sh
```

就这两步。所有元信息从 `manifest.json` 自动读取，零硬编码。

### manifest.json 必填字段

```jsonc
{
  "name": "e1-conservative",                 // 模型名
  "model": { "type": "lightgbm" },            // 模型类型
  "strategy": {
    "label": "directional_filtered",          // 标签策略
    "T": 21,                                  // 前瞻窗口
    "X": 0.04                                 // 反弹阈值
  },
  "features": { "count": "129" },             // 特征数
  "metrics": {
    "classification": { "cohen_kappa": 0.19 },
    "pnl": {
      "策略(止盈+regime)": {
        "cagr": 0.139,
        "max_drawdown": -0.127,
        "profit_factor": 2.13,
        "sharpe": 1.32
      }
    }
  },
  "source_experiment": { "id": "weekly_bear_v0305_E1_decontam" }
}
```

---

## 环境变量

### 部署时（deploy.sh）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MODEL_NAME` | **必填** | 模型名，对应 `models/production/<NAME>` |
| `STRATEGY_VARIANT` | `conservative` | 策略变体: base / moderate / conservative |
| `GCP_PROJECT_ID` | `forecastlab-prod` | GCP 项目 ID |
| `STATE_BUCKET` | `gs://...-signals/<NAME>` | GCS 状态桶 |

### 运行时（docker_entrypoint.sh）

| 变量 | 说明 |
|------|------|
| `MODEL_NAME` | 模型名 |
| `STRATEGY_VARIANT` | 策略变体 |
| `STATE_BUCKET` | GCS 状态桶 |
| `SMTP_USER` | QQ 邮箱账号 |
| `SMTP_PASS` | QQ 邮箱授权码 |
| `SMTP_HOST` | SMTP 服务器（默认 smtp.qq.com） |
| `SMTP_PORT` | SMTP 端口（默认 465） |
| `MAIL_TO` | 收件人邮箱 |
| `GEMINI_API_KEY` | Gemini API Key（可选，用于 LLM 分析） |

---

## 策略变体

| 变体 | 止盈 | Regime 开关 | 说明 |
|------|------|-------------|------|
| `base` | ✖ | ✖ | 原始模型信号，持仓 T 天到期平仓 |
| `moderate` | ✔ | ✖ | +止盈（涨幅达 X% 即平仓） |
| `conservative` | ✔ | ✔ | +止盈 +regime（63天收益≤-10% 时静默） |

---

## 运维命令

```bash
# 手动触发
gcloud run jobs execute daily-btc-signal-e1-conservative --region asia-east1

# 查看日志
gcloud logging read 'resource.labels.job_name="daily-btc-signal-e1-conservative"' \
    --limit=50 --format='table(timestamp,textPayload)'

# 查看持仓状态
gsutil cat gs://forecastlab-prod-signals/e1-conservative/signal_state.json \
    | python3 -m json.tool

# 查看最新信号
gsutil ls -l gs://forecastlab-prod-signals/e1-conservative/signals/

# 暂停/恢复调度
gcloud scheduler jobs pause  trigger-e1-conservative --location=asia-east1
gcloud scheduler jobs resume trigger-e1-conservative --location=asia-east1

# 删除 Job（下线模型）
gcloud run jobs delete daily-btc-signal-e1-conservative --region asia-east1
gcloud scheduler jobs delete trigger-e1-conservative --location=asia-east1
```

---

## 流水线详解（docker_entrypoint.sh 8 步）

| Step | 脚本 | 说明 | 失败处理 |
|------|------|------|----------|
| 1 | 内联 Python | 下载 Binance 日线 + FGI | 回退本地缓存 |
| 2 | gsutil | 从 GCS 恢复持仓状态 | 初始化空仓 |
| 3 | `live_signal.py` | 模型推理 + 状态更新 | 失败即退出 |
| 4 | gsutil | 保存持仓状态到 GCS | - |
| 5 | `build_signal_json.py` | 生成信号 JSON | 跳过 |
| 6 | `enrich_llm_analysis.py` | LLM 策略解读 | 跳过（可选） |
| 7 | `send_signal_email.py` | 发送 QQ 邮件 | 跳过 |
| 8 | gsutil | 上传信号 JSON 到 GCS | 跳过 |

---

## 当前已部署模型

| 模型 | 定位 | Kappa | CAGR | MaxDD |
|------|------|-------|------|-------|
| `e1-conservative` | 🛡️ 风控优先 | 0.19 | 13.9% | -12.7% |
| `e8-touch` | 💰 收益优先 | 0.75 | 23.3% | -21.4% |

详见 [`models/production/SUMMARY.md`](../models/production/SUMMARY.md)

---

## VPS 自建部署

如果你不想依赖 Google Cloud，可以把整套流水线跑在任意 VPS 上：

```bash
# 在 VPS 上 clone 项目后，一键初始化（无 Docker）
sudo bash deploy/vps/setup_vps_nodock.sh

# 手动触发测试
bash deploy/vps/run_daily_nodock.sh
```

详见 [`deploy/vps/VPS_GUIDE.md`](vps/VPS_GUIDE.md)

| 方案 | 调度 | 状态持久化 | 适用场景 |
|------|------|-----------|----------|
| Cloud Run（默认）| Cloud Scheduler | GCS Bucket | 托管、按量付费 |
| VPS（无 Docker）| cron | 本地文件 | 固定月费、完全自控 |

---

## archive/ 目录

包含 v0215 ~ v0305 的历史部署脚本、Dockerfile、实验报告。
仅供回溯参考，不再维护。
