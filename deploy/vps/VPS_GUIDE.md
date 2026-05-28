# FcstLabPro — VPS 部署指南

> 把每日信号流水线跑在你自己的 VPS 上，无需 Google Cloud。

---

## 架构概览

```
VPS (Ubuntu 22.04+)
│
├── cron (每日 UTC 00:10)
│       │
│       └─ run_daily.sh
│               │
│               └─ docker run fcstlabpro:latest
│                       │
│                       ├─ Step 1: 下载 Binance BTCUSDT 日线
│                       ├─ Step 2: 跳过（无 GCS，使用本地卷）
│                       ├─ Step 3: LightGBM 推理 → 信号
│                       ├─ Step 4: 跳过（本地卷持久化）
│                       ├─ Step 5: 生成信号 JSON
│                       ├─ Step 6: [可选] Gemini LLM 分析
│                       ├─ Step 7: 发送 QQ 邮件
│                       └─ Step 8: 跳过（本地保存）
│
└── /opt/fcstlabpro/
        ├── .env              # 你的配置（密钥/邮箱等）
        ├── state/            # 持仓状态（卷挂载 → 容器 /tmp/state）
        ├── signals/          # 信号 JSON 归档（卷挂载 → 容器 /tmp/signals）
        └── logs/             # 每日运行日志
```

---

## 前置条件

| 要求 | 说明 |
|------|------|
| Ubuntu 22.04 / Debian 12 | 其他发行版需手动安装 Docker |
| 1 vCPU + 1 GB RAM（最低）| 推荐 2 vCPU + 2 GB |
| 能访问 Binance API | VPS IP 不在 Binance 封禁区域 |
| QQ 邮箱授权码 | 用于发送信号邮件 |

---

## 快速开始（4 步）

### Step 1：SSH 登录 VPS，克隆项目

```bash
ssh root@<your-vps-ip>

# 克隆项目
git clone <your-repo-url> /opt/fcstlabpro-repo
cd /opt/fcstlabpro-repo
```

### Step 2：一键初始化

```bash
bash deploy/vps/setup_vps.sh
```

脚本会自动：
- 安装 Docker
- 创建 `/opt/fcstlabpro/` 数据目录
- 生成 `.env` 配置模板
- 构建 Docker 镜像
- 注册 cron 定时任务

### Step 3：填写配置

```bash
nano /opt/fcstlabpro/.env
```

**必填项：**

```ini
MODEL_NAME=e1-conservative     # 或 e8-touch
STRATEGY_VARIANT=conservative  # base / moderate / conservative

SMTP_USER=your_qq@qq.com
SMTP_PASS=your_qq_smtp_authcode   # QQ 邮箱「授权码」，不是登录密码
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
MAIL_TO=your_email@example.com
```

**可选项：**

```ini
GEMINI_API_KEY=      # 填入则启用 LLM 分析，留空跳过
COINGECKO_API_KEY=   # CoinGecko API Key
COINGLASS_API_KEY=   # Coinglass API Key
```

> ⚠️ `STATE_BUCKET=` 保持**空值**——VPS 模式用本地卷代替 GCS。

### Step 4：手动测试一次

```bash
bash /opt/fcstlabpro-repo/deploy/vps/run_daily.sh
```

看到 `✅ 运行完成` 就大功告成！之后 cron 会每天 UTC 00:10（北京时间 08:10）自动触发。

---

## 常用运维命令

```bash
# 手动触发信号
bash /opt/fcstlabpro-repo/deploy/vps/run_daily.sh

# 查看今日日志
tail -f /opt/fcstlabpro/logs/daily_$(date +%Y%m%d).log

# 查看最新信号
ls -lt /opt/fcstlabpro/signals/ | head -5
cat /opt/fcstlabpro/signals/signal_*.json | python3 -m json.tool | head -50

# 查看持仓状态
cat /opt/fcstlabpro/state/signal_state.json | python3 -m json.tool

# 查看 cron 注册情况
crontab -l

# 修改 cron 时间（默认 UTC 00:10）
crontab -e

# 查看 Docker 镜像
docker images | grep fcstlabpro

# 重建镜像（代码更新后）
cd /opt/fcstlabpro-repo
git pull
docker build -t fcstlabpro:latest .
```

---

## 更新流程（代码有更新时）

```bash
cd /opt/fcstlabpro-repo

# 1. 拉取最新代码
git pull

# 2. 重建镜像
docker build -t fcstlabpro:latest .

# 3. 下次 cron 会自动使用新镜像，或手动触发
bash deploy/vps/run_daily.sh
```

---

## 切换模型

编辑 `/opt/fcstlabpro/.env`，修改：

```ini
MODEL_NAME=e8-touch          # 改为 e8-touch（收益优先）
STRATEGY_VARIANT=conservative
```

无需重建镜像，下次运行立即生效。

---

## 故障排查

### Binance API 不可用

部分 VPS 机房 IP 被 Binance 限制。解决方案：
- 换用支持 Binance 的 VPS 地区（香港、新加坡、日本等）
- 或配置代理：在 `.env` 加入 `HTTP_PROXY=` / `HTTPS_PROXY=`

### 邮件发送失败

```bash
# 检查 QQ 邮箱授权码是否正确（不是登录密码！）
# QQ 邮箱 → 设置 → 账户 → POP3/SMTP → 生成授权码

# 测试 SMTP 连通性
nc -zv smtp.qq.com 465
```

### 内存不足

```bash
# 检查内存
free -h

# 降低内存限制（run_daily.sh 里修改 --memory 参数）
# 或升级 VPS 套餐
```

### 查看容器实时日志

```bash
# 运行时实时查看
docker ps                        # 找到容器名
docker logs -f <container-name>
```

---

## 与 Cloud Run 的差异

| 特性 | Cloud Run（原方案）| VPS（本方案）|
|------|-------------------|-------------|
| 状态持久化 | GCS Bucket | 本地 Docker 卷 |
| 调度 | Cloud Scheduler | cron |
| 费用 | 按量付费 | 固定月费 |
| 运维 | 托管 | 自行维护 |
| 数据安全 | GCS 冗余 | 本地磁盘（建议备份） |
| Binance 访问 | GCP IP | VPS IP |

---

## 文件说明

```
deploy/vps/
├── VPS_GUIDE.md    ← 本文件
├── setup_vps.sh    ← 一键初始化（在 VPS 上运行一次）
└── run_daily.sh    ← 每日信号运行（cron 调用）
```
