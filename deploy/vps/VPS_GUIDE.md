# FcstLabPro — VPS 部署指南（无 Docker）

> VPS 是自己的机器，直接跑 Python 就行。Docker 版已经移除，别给 cron 套娃了，小狗反对无意义复杂度 🐶

---

## 架构概览

```
VPS (Ubuntu 22.04+)
│
├── cron (每日 UTC 00:10 / 北京时间 08:10)
│       │
│       └─ run_daily_nodock.sh
│               │
│               └─ .venv/bin/python
│                       │
│                       ├─ 下载 Binance BTCUSDT 日线
│                       ├─ LightGBM 推理
│                       ├─ 生成信号 JSON
│                       ├─ [可选] Gemini LLM 分析
│                       └─ [可选] 发送邮件
│
├── /root/FcstLabPro/.venv/       # Python 虚拟环境
└── /opt/fcstlabpro/
        ├── .env                  # 密钥/邮箱/模型配置
        ├── state/                # 持仓状态 signal_state.json
        ├── signals/              # 信号 JSON 归档
        └── logs/                 # 每日运行日志
```

---

## 前置条件

| 要求 | 说明 |
|------|------|
| Ubuntu 22.04+ | 当前脚本用 apt |
| Python 3.10+ | Ubuntu 24.04 默认 3.12 也可 |
| 1 vCPU + 1GB RAM | 推荐 2 vCPU + 2GB |
| 可访问 Binance API | 你已验证 IP 可访问 |
| QQ 邮箱授权码 | 用于邮件推送 |

---

## 快速开始

### 1. SSH 登录 VPS，拉取最新代码

```bash
ssh root@<your-vps-ip>
cd ~/FcstLabPro

git pull
```

### 2. 初始化无 Docker 部署

```bash
sudo bash deploy/vps/setup_vps_nodock.sh
```

脚本会自动：
- 安装系统依赖：`python3`, `python3-venv`, `pip`, `libgomp1`
- 创建 `.venv`
- 安装 Python 依赖
- 生成 `/opt/fcstlabpro/.env`
- 注册每日 cron

### 3. 填写配置

```bash
nano /opt/fcstlabpro/.env
```

必填：

```ini
# 串行运行两个模型
MODEL_NAMES=e1-conservative,e8-touch
STRATEGY_VARIANT=conservative

SMTP_USER=your_qq@qq.com
SMTP_PASS=your_qq_smtp_authcode
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
MAIL_TO=your_receive@example.com

STATE_BUCKET=
```

注意：`SMTP_PASS` 是 QQ 邮箱 SMTP 授权码，不是 QQ 登录密码。

### 4. 手动测试一次

```bash
bash deploy/vps/run_daily_nodock.sh
```

看到 `🎉 全部模型完成！` 就成功。两个模型会串行运行，互不覆盖状态和信号。

---

## 常用命令

```bash
# 手动触发
bash ~/FcstLabPro/deploy/vps/run_daily_nodock.sh

# 查看今日日志
tail -f /opt/fcstlabpro/logs/daily_$(date +%Y%m%d).log

# 查看最新信号（E1）
ls -lt /opt/fcstlabpro/signals/e1-conservative/ | head

# 查看最新信号（E8）
ls -lt /opt/fcstlabpro/signals/e8-touch/ | head

# 查看持仓状态（每个模型独立）
cat /opt/fcstlabpro/state/e1-conservative_state.json | python3 -m json.tool
cat /opt/fcstlabpro/state/e8-touch_state.json | python3 -m json.tool

# 查看 cron
crontab -l

# 修改定时
crontab -e
```

---

## 更新流程

```bash
cd ~/FcstLabPro

git pull
sudo bash deploy/vps/setup_vps_nodock.sh
bash deploy/vps/run_daily_nodock.sh
```

---

## 配置运行模型

编辑 `/opt/fcstlabpro/.env`。

串行运行两个模型：

```ini
MODEL_NAMES=e1-conservative,e8-touch
STRATEGY_VARIANT=conservative
```

只运行一个模型：

```ini
MODEL_NAMES=e1-conservative
STRATEGY_VARIANT=conservative
```

保存后下次运行自动生效。

---

## 故障排查

### `Cannot import setuptools.backends._legacy`

旧版本 `pyproject.toml` 使用了不兼容 backend。修复方式：

```bash
cd ~/FcstLabPro
git pull
rm -rf .venv
sudo bash deploy/vps/setup_vps_nodock.sh
```

### 邮件发送失败

```bash
nc -zv smtp.qq.com 465
```

再确认 `/opt/fcstlabpro/.env` 里的 `SMTP_PASS` 是授权码。

### Binance API 不可用

你当前 IP 已测通；如果以后换机房，先测：

```bash
curl -s --max-time 10 https://api.binance.com/api/v3/ping && echo OK
```

---

## 文件说明

```
deploy/vps/
├── VPS_GUIDE.md             # 本文件
├── setup_vps_nodock.sh      # VPS 初始化
└── run_daily_nodock.sh      # 每日运行脚本
```
