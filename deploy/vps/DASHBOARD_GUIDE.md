# Performance Dashboard — VPS 部署指南

> 纯展示层 web 服务，只读 performance 层产物 (`batches.json` / `summary.json`)。
> 与信号 cron 解耦：cron 写文件，dashboard 读文件，互不影响。

---

## 架构

```
信号 cron (run_daily_nodock.sh)
   └─ scripts/build_performance.py  →  /opt/fcstlabpro/performance/{model}/*.json
                                            │ 读 (only)
   systemd: fcstlab-dashboard  ───────────┘
       └─ uvicorn 127.0.0.1:8000  →  浏览器
```

---

## 一、安装依赖

```bash
cd ~/FcstLabPro
git pull

# dashboard 需要 fastapi/jinja2/uvicorn (信号链路不需要)
uv pip install --python .venv/bin/python fastapi jinja2 uvicorn \
  --index-url https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple \
  --allow-insecure-host pypi.ci.artifacts.walmart.com
```

## 二、先生成一次数据

```bash
.venv/bin/python scripts/build_performance.py
# → /opt/fcstlabpro/performance/{e1-conservative,e8-touch}/batches.json
```

> ⚠️ 早期信号都是 PENDING (距今 < T+1=22 天)，表里显示 ⏳ 是正常的。
> 等信号满 22 天后回填才会出命中率/实现收益。

## 三、注册 systemd 常驻服务

```bash
sudo cp deploy/vps/fcstlab-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fcstlab-dashboard
sudo systemctl status fcstlab-dashboard      # 看是否 active (running)
journalctl -u fcstlab-dashboard -f           # 实时日志
```

## 四、访问 (二选一)

### A. SSH 隧道 (推荐，最安全，零额外组件)

服务默认绑 `127.0.0.1:8000`，只有本机能访问。本地电脑开隧道：

```bash
ssh -L 8000:localhost:8000 root@<vps-ip>
# 然后本地浏览器打开 http://localhost:8000
```

### B. nginx 反代 + TLS + 认证 (长期/多人)

```nginx
server {
    listen 443 ssl;
    server_name dash.example.com;
    ssl_certificate     /etc/letsencrypt/live/dash.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dash.example.com/privkey.pem;

    auth_basic "FcstLabPro";
    auth_basic_user_file /etc/nginx/.htpasswd;   # htpasswd -c 生成

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
}
```

> ❌ 绝不要把 `DASHBOARD_HOST=0.0.0.0` 裸暴露公网无认证。

---

## 五、让 cron 每日刷新 performance 数据

在 `deploy/vps/run_daily_nodock.sh` 信号生成后追加一行 (信号 archive 写完才有数据可回填)：

```bash
.venv/bin/python scripts/build_performance.py --out-dir /opt/fcstlabpro/performance
```

dashboard 无需重启——它每次请求都读最新文件。**cron 写 → 刷新页面即见最新**。

---

## 六、配置项 (env, 可写进 /opt/fcstlabpro/.env)

| 变量 | 默认 | 说明 |
|---|---|---|
| `DASHBOARD_HOST` | 127.0.0.1 | 绑定地址 (慎改 0.0.0.0) |
| `DASHBOARD_PORT` | 8000 | 端口 (避让 8080) |
| `FCST_DATA_DIR` | /opt/fcstlabpro | performance 数据根目录 |
| `DASHBOARD_STALE_HOURS` | 26 | 超此小时未更新 → 页面警示 stale |

---

## 七、常用命令

```bash
sudo systemctl restart fcstlab-dashboard   # 改代码后重启
sudo systemctl stop fcstlab-dashboard      # 停服务
journalctl -u fcstlab-dashboard --since "1 hour ago"
curl -s localhost:8000 | grep "Score Batch Detail"   # 健康检查
```

---

## 八、故障排查

| 现象 | 排查 |
|---|---|
| 502 / 连不上 | `systemctl status` 看是否 running；`journalctl` 看报错 |
| 页面提示无数据 | 跑过 `build_performance.py` 吗？`/opt/fcstlabpro/performance/` 有 json 吗 |
| 页面提示 stale | cron 没跑 → + 信号日志 |
| 表全是 ⏳ | 正常 — 信号还没满 T+1 天，标签未成熟 |
| CDN 加载慢 | VPS 外网慢；可把 tailwind/chart.js 下到 static/ 改本地引用 |

---

*维护: FcstLabPro 核心架构组 + sam (code-puppy)*
