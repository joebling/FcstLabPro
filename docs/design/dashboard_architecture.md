# Dashboard Web 服务架构设计

> **日期**: 2026-05-29
> **作者**: sam (code-puppy)
> **关联**: `docs/design/performance_tracking.md` (数据闭环, 本文档的数据来源)
> **部署目标**: VPS (Ubuntu, 无 Docker, 与信号 cron 同机)
> **技术栈**: FastAPI + Jinja2 + HTMX + Tailwind (CDN) + Chart.js (CDN)

> ⚠️ **架构修订 (2026-05-29, 实施时)**: 初版设计为「performance 层预生成
> JSON 文件 → dashboard 只读文件」。实施时对齐 RiskDetect 后改为
> **「dashboard 请求时实时算 + TTL 内存缓存」**, 取消中间 JSON 产物和
> `build_performance.py`。
>
> 原因: RiskDetect 并无预生成 JSON 这一步 — 它请求时实时查 DB + 24h 缓存。
> FcstLabPro 信号量极小 (每天每模型 1 条), 回填聚合是毫秒级, 没必要多一层
> 文件产物 + 「谁来刷新」的协调问题。真相源单一 = `data/signals/archive/`
> (类比 RiskDetect 的 Postgres)。
>
> **下文凡提到 batches.json / cron 写文件 / D-0 产出 JSON / stale(文件 mtime)
> 的部分均为初版设计, 已被实时算取代。实际实现见**:
> - `src/performance/service.py` — 实时算入口 (resolve label.T + 缓存)
> - `src/performance/cache.py` — TTL 缓存 (抄 RiskDetect cached())
> - `src/dashboard/data_access.py` — 调 service, 不读文件

---

## 0. 一句话定位

Dashboard 是 **纯展示层**：请求时实时调 performance 服务 (回填+聚合) 并
用 TTL 缓存挡重复请求，不碰模型、不影响信号生成。挂了重启即可，无状态。

---

## 1. 核心架构原则

### 1.1 严格只读 + 关注点分离

```text
信号 cron (run_production_pipeline)
   │  写
   ▼
data/live/performance/{model}/batches.json   ← performance 层产物 (P-1~P-2)
   │  读 (only)
   ▼
Dashboard (FastAPI)  ──渲染──▶  浏览器
```

- Dashboard **从不**调 model / 算 backfill。那是 performance 层的活。
- 两个进程解耦：cron 写文件，web 读文件。文件即接口。
- Dashboard 崩溃 → 信号照常生成。信号 cron 崩溃 → dashboard 显示陈旧数据 + 明确标记 stale。

### 1.2 无构建步骤 (no-build frontend)

Tailwind 和 Chart.js 走 CDN，不引入 npm/webpack/node_modules。
理由：数据量小、页面少、VPS 资源紧。符合 Walmart flat-report 规则。

> ⚠️ CDN 依赖外网。VPS 能访问 Binance API 说明外网通，CDN 没问题。
> 若要离线，把 tailwind.min.css / chart.min.js 下到 static/ 即可（一行改动）。

### 1.3 技术栈选型理由

| 选择 | 为什么 | 排除了什么 |
|---|---|---|
| **FastAPI** | 长期常驻服务 + Walmart 默认栈 + async | flat HTML(无法常驻/无路由) |
| **Jinja2 + HTMX** | 服务端渲染, 局部刷新, 零前端构建 | React/Vue(过重, 要构建) |
| **Tailwind CDN** | 快速样式 + WCAG 友好 | 手写 CSS(慢) |
| **Chart.js CDN** | 趋势图 (hit_rate/IC 时序) | D3(过度工程) |
| **文件读取** | 数据量小, 读多写少 | DB(YAGNI, 每天每模型 1 条) |

---

## 2. 目录结构

```text
src/dashboard/
  __init__.py
  app.py                  # FastAPI app 工厂 + 启动配置
  config.py               # 路径/端口/刷新间隔 (env 可覆盖)
  data_access.py          # ★ 唯一读 performance JSON 的地方 (DRY)
  routes/
    __init__.py
    pages.py              # 整页路由 (GET /)
    partials.py           # HTMX 局部路由 (GET /partial/batches 等)
  templates/
    base.html             # 布局 + Tailwind/Chart.js CDN + 导航
    index.html            # 主页 (extends base)
    partials/
      batch_table.html    # ★ Score Batch Detail 表 (对标 RiskDetect)
      kpi_row.html        # 顶部 KPI 卡片
      ic_chart.html       # IC/hit_rate 趋势图 canvas
  static/
    app.css               # 极少量自定义 (data-bar 等 Tailwind 补充)
    sort_table.js         # 表格排序/CSV 导出 (抄 RiskDetect 交互)

scripts/
  serve_dashboard.py      # 启动入口: uvicorn src.dashboard.app:app

deploy/vps/
  fcstlab-dashboard.service  # systemd unit (常驻)
  DASHBOARD_GUIDE.md         # 部署文档
```

**文件行数纪律**: 每个文件 < 600 行。data_access.py 预计 ~150 行，
routes 各 ~80 行，templates 各 ~100 行。无超标风险。

---

## 3. 数据访问层 (data_access.py) — 唯一真相入口

所有读文件的逻辑收口到这里，routes 不直接碰文件系统 (DRY + 可测试)。

```python
# src/dashboard/data_access.py
"""Dashboard 唯一的数据读取层 — 只读 performance 层产物, 不计算."""
from __future__ import annotations
import json
import os
from pathlib import Path
from datetime import datetime, timezone

from src.serving.active_config import load_active_models

PERF_DIR = Path(os.environ.get("FCST_DATA_DIR", "/opt/fcstlabpro")) / "performance"

def list_models() -> list[str]:
    """从 active.yaml 取模型列表 (单一真相源, 不硬编码)."""
    return [m.name for m in load_active_models().values()]

def load_batches(model_name: str) -> dict:
    """读 batches.json. 带 stale 检测 (文件 mtime vs 今天)."""
    path = PERF_DIR / model_name / "batches.json"
    if not path.exists():
        return {"rows": [], "stale": True, "reason": "no_data"}
    rows = json.loads(path.read_text())
    age_h = (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / 3600
    return {
        "rows": rows,
        "stale": age_h > 26,          # 日更, 超 26h 没更新 = 异常
        "generated_age_hours": round(age_h, 1),
    }

def load_summary(model_name: str) -> dict:
    """读 summary.json (滚动 hit_rate / IC / Sharpe)."""
    path = PERF_DIR / model_name / "summary.json"
    return json.loads(path.read_text()) if path.exists() else {}
```

**关键设计**:
- `list_models()` 从 active.yaml 读 → 模型增减自动反映，不改 dashboard 代码
- `stale` 检测 → 页面能区分「真没数据」vs「cron 挂了显示陈旧」(诚实优于好看)

---

## 4. 路由设计

### 4.1 整页 (pages.py)

```python
@router.get("/", response_class=HTMLResponse)
def index(request: Request, model: str | None = None):
    models = data_access.list_models()
    active = model or models[0]
    return templates.TemplateResponse("index.html", {
        "request": request,
        "models": models,
        "active_model": active,
        "batches": data_access.load_batches(active),
        "summary": data_access.load_summary(active),
    })
```

### 4.2 HTMX 局部 (partials.py)

模型切换、排序后只换表格区，不整页刷新：

```python
@router.get("/partial/batches", response_class=HTMLResponse)
def batches_partial(request: Request, model: str):
    return templates.TemplateResponse("partials/batch_table.html", {
        "request": request,
        "batches": data_access.load_batches(model),
    })
```

前端切模型：
```html
<select hx-get="/partial/batches" hx-target="#batch-area" name="model">
```

**路由极简**：1 个整页 + 2-3 个 partial。不做用户系统、不做写操作 (纯只读)。

---

## 5. Score Batch Detail 表 (照搬 RiskDetect 三精髓)

`partials/batch_table.html` 复刻那张表的核心交互，但适配 FcstLabPro 语义：

| RiskDetect 列 | FcstLabPro 对应 | 来源 |
|---|---|---|
| Score Date | score_date | ledger |
| Sellers | n_signals | ledger |
| Critical/High/... 分布 | BUY/SILENT 分布 | ledger |
| **AUC** | **Rank IC (rolling)** | performance |
| **Critical Term%** | **hit_rate** | performance |
| (新增) | **avg_realized_return** | performance |
| Model | model_hash | ledger provenance |

抄的三个交互细节：
1. **成熟度三态**: `⏳` PENDING (未到 T+1 天) / `—` 无数据 / 彩色数字
2. **in-cell data bar**: `--bar` CSS 变量按列归一，分布一眼可见
3. **颜色门槛对齐机构手册**:
   - Rank IC ≥ 0.02 绿 / 0~0.02 灰 / <0 红
   - hit_rate ≥ 55% 绿 / 45~55% 琥珀 / <45% 红
   - 用 Walmart 色: green.100=#2a8703 / spark.140=#995213 / red.100=#ea1100

WCAG 2.2 AA: 颜色不单独承载信息 (配 ⏳/—/数字符号)，对比度 ≥4.5:1。

---

## 6. 部署 (VPS, systemd 常驻)

### 6.1 systemd unit

```ini
# deploy/vps/fcstlab-dashboard.service
[Unit]
Description=FcstLabPro Performance Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/FcstLabPro
EnvironmentFile=/opt/fcstlabpro/.env
ExecStart=/root/FcstLabPro/.venv/bin/python scripts/serve_dashboard.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now fcstlab-dashboard
sudo systemctl status fcstlab-dashboard
journalctl -u fcstlab-dashboard -f   # 看日志
```

### 6.2 网络暴露方式 (二选一)

| 方式 | 适用 | 说明 |
|---|---|---|
| **A. 绑 127.0.0.1 + SSH 隧道** | 自己看 | `uvicorn --host 127.0.0.1 --port 8000`, 本地 `ssh -L 8000:localhost:8000` |
| **B. nginx 反代 + TLS + basic auth** | 长期/多人 | nginx 转 127.0.0.1:8000, Let's Encrypt 证书, htpasswd |

**推荐起步用 A**(零额外组件, 最安全)，需要常态访问再上 B。
绝不直接 `--host 0.0.0.0` 裸暴露公网无认证。

> ⚠️ 端口避让: 不用 8080 (Walmart 规则保留)。dashboard 用 8000。

### 6.3 数据更新触发

performance JSON 由信号 cron 顺带生成 (performance_tracking.md 的 P-5)。
Dashboard 无需定时任务——它只在 HTTP 请求时读最新文件。
**cron 写 → 浏览器刷新即见最新**，零耦合。

---

## 7. 与 performance 层的接口契约

Dashboard 依赖 performance 层产出这些文件 (performance_tracking.md §4 定义)：

```text
/opt/fcstlabpro/performance/{model}/
  batches.json     # 必需: 批次表数据源
  summary.json     # 必需: KPI 卡片 + 趋势图数据源
  outcomes.csv     # 可选: "导出明细" 按钮直接下载
```

**契约即文件 schema**。performance 层改 schema → 同步改 data_access.py 一处。
建议加 `tests/test_dashboard_data_access.py` 锁 schema (给假 JSON, 断言解析不崩)。

---

## 8. 开发顺序 (增量, 每步可独立验证)

| 步 | 任务 | 验证 | 依赖 |
|---|---|---|---|
| **D-0** | performance 层 P-1/P-2 (产出 batches.json) | JSON 存在且结构对 | — |
| **D-1** | data_access.py + 单测 | pytest 解析假数据 | D-0 |
| **D-2** | app.py + 整页路由 + base/index 模板 | 本地 curl localhost:8000 出 HTML | D-1 |
| **D-3** | batch_table.html (表格 + 三态 + data bar) | 浏览器看到表 | D-2 |
| **D-4** | KPI 卡片 + Chart.js 趋势图 | 图渲染 | D-2 |
| **D-5** | HTMX 模型切换 partial | 切模型不整页刷 | D-3 |
| **D-6** | systemd unit + DASHBOARD_GUIDE | VPS 常驻可访问 | D-3 |

**D-0 是前提**：没有 batches.json，后面全是空壳。所以**先做 performance 闭环**。

---

## 9. YAGNI 边界 (明确不做)

| 不做 | 原因 |
|---|---|
| 用户登录/权限系统 | 个人 dashboard, SSH 隧道或 basic auth 足够 |
| 数据库 | 文件即数据, 读多写少 |
| 实时 WebSocket 推送 | 日更模型, 刷新页面足矣 |
| 前端框架 (React/Vue) | 页面少, HTMX 够, 避免构建链 |
| 写操作 (改配置/触发训练) | dashboard 严格只读, 写操作走 CLI/SOP |
| 多语言 i18n | 单人用 |

---

## 10. 风险与防线

| 风险 | 防线 |
|---|---|
| cron 没跑 → 数据陈旧 | data_access 的 `stale` 标记 + 页面 banner 警示 |
| batches.json 损坏 | data_access try/except → 返回空 + reason, 页面不白屏 |
| CDN 不可达 | 文档说明如何切本地 static (一行改) |
| 端口冲突 | 用 8000, 避让 8080/Teams |
| 公网裸暴露 | 默认 127.0.0.1, 文档强调别用 0.0.0.0 |
| dashboard 拖慢 VPS | 纯读 + Restart=on-failure, 资源占用极低 |

---

## 11. 与现有代码的衔接

- **数据源**: performance 层 (`src/performance/`, 待建) 的 JSON 产物
- **模型列表**: `src/serving/active_config.py::load_active_models` (已有)
- **路径约定**: `FCST_DATA_DIR` env (与 pipeline 一致, 默认 /opt/fcstlabpro)
- **部署**: 复用 `deploy/vps/` 目录 + .venv + .env 体系

---

*本方案保存于 docs/design，等 owner review 后再决定是否实施。*
*实施时严格遵循 experiment_sop.md 的增量提交纪律，dashboard 代码与 performance 层分开 commit。*
