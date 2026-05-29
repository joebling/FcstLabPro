# Performance Dashboard — VPS 部署指南

> 纯展示层 web 服务。请求时实时回填+聚合 (信号量极小, 毫秒级) + TTL 内存缓存。
> 真相源单一 = `data/signals/archive/` (信号 cron 写的), dashboard 只读不写。

---

## 架构

```
信号 cron (run_daily_nodock.sh)
   └─ 写 data/signals/archive/{model}/{date}.json   ← 真相源
                                  │ 读 (only)
   systemd: fcstlab-dashboard  ───┘
       └─ uvicorn 127.0.0.1:8000  →  实时回填聚合 + TTL缓存  →  浏览器
```

无中间 JSON 产物, 无「谁来刷新」的协调问题 — 信号 cron 写完 archive,
刷新页面即见最新 (缓存过期后)。

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

## 二、数据怎么来 (无需生成步骤)

dashboard 请求时实时读 `data/signals/archive/` 回填计算, **不需要预生成**。
只要信号 cron 在跑 (archive 有数据), dashboard 就能展示。

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

## 五、数据新鲜度 (无需 cron 刷新)

dashboard 请求时实时算, 所以不需要任何「刷新」 cron。信号 cron 每日写完
new archive, 下次请求 (缓存过期后) 自动反映。

缓存 TTL 默认 30 分钟 (`DEFAULT_TTL_SECONDS`)。如果刚跑完信号想立即看到,
等最多 30 分钟, 或重启服务 (`systemctl restart fcstlab-dashboard`) 清缓存。

---

## 六、配置项 (env, 可写进 /opt/fcstlabpro/.env)

| 变量 | 默认 | 说明 |
|---|---|---|
| `DASHBOARD_HOST` | 127.0.0.1 | 绑定地址 (慎改 0.0.0.0) |
| `DASHBOARD_PORT` | 8000 | 端口 (避让 8080) |

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
| 页面提示无数据 | `data/signals/archive/{model}/` 有信号吗？信号 cron 跑过吗 |
| 页面提示计算出错 | `journalctl` 看堆栈；OHLCV 数据/active.yaml 是否完整 |
| 表全是 ⏳ | 正常 — 信号还没满 T+1 天，标签未成熟 |
| CDN 加载慢 | VPS 外网慢；可把 tailwind/chart.js 下到 static/ 改本地引用 |

---

*维护: FcstLabPro 核心架构组 + sam (code-puppy)*
