# FcstLabPro 部署指南

> **最后更新**: 2026-06-02
> **现役生产链路**: VPS 无 Docker (见下方 §1)

---

## ⚠️ 三条链路速查 (防搞错)

| 链路 | 入口 | 状态 | 真相源 |
|---|---|---|---|
| **VPS 无 Docker** | `deploy/vps/run_daily_nodock.sh` | ✅ **现役生产** | `models/production/active.yaml` |
| macOS 本地 launchd | `deploy/run_signal.sh` + `com.fcstlab.signal.plist` | 🟡 本地辅助 | `active.yaml` |
| ~~Cloud Run~~ | ~~`deploy.sh` + `docker_entrypoint.sh`~~ | ⛔ **已停用** | ~~MODEL_NAME 环境变量~~ |

> Cloud Run 整套已于 2026-06-02 归档到 `deploy/archive/DEPRECATED_cloudrun_*`，
> **请勿运行**。它用旧的 `MODEL_NAME`/`STRATEGY_VARIANT` 环境变量（多处真相源），
> 与现架构 `active.yaml` 单一真相源不兼容。

---

## 1. 现役链路: VPS 无 Docker ✅

```bash
# VPS 上由 cron/systemd 定时触发
deploy/vps/run_daily_nodock.sh
```

**编排全收敛到** `scripts/run_production_pipeline.py`:

```
run_daily_nodock.sh
  └─ run_production_pipeline.py --include-paper
        ├─ load_active_models()            ← active.yaml【单一真相源】
        ├─ 数据新鲜度强校验 (decision A: 缺失/超SLA → FATAL)
        └─ 每个 status∈{live,paper} 模型:
              ├─ live_signal.run_for_model()   ← 推理 + regime + 写 state
              ├─ build_signal_json()           ← 读 state 生成 JSON
              ├─ enrich_llm_analysis()         ← LLM 解读 (可选)
              └─ send_signal_email()           ← 邮件 (可选)
```

### 切换模型 / 回滚

改 `models/production/active.yaml` 的 `artifact_dir` + `status`，然后:

```bash
git add models/production/active.yaml
git commit -m "switch: primary → <new_model>"
# 回滚 = git revert 那个 commit
```

### variant → 策略 flags 映射 (`src/serving/active_config.py`)

| variant | flags | regime 开关 |
|---|---|---|
| base | (无) | ❌ |
| moderate | `--take-profit` | ❌ |
| **conservative** | `--take-profit --regime-switch` | ✅ |

> 启动时 `active_config.py` 强校验 variant 与模型 `manifest.json` 一致，不一致直接 fail。

### 市场状态 (regime) 判断

**conservative variant 启用**，规则在 `live_signal.is_bear_market()`:

```
过去 63 天滚动收益 ≤ -10%  →  熊市
  ├─ 有持仓 → 强制平仓 (SELL)
  └─ 无持仓 → 策略静默 (SILENT)
```

邮件用 🔴(熊市) / 🟢(非熊市) 圆点展示，详情来自 state 的 `last_regime_detail`。

---

## 2. macOS 本地 launchd 🟡

本地 Mac 用 `launchd` 定时跑 `deploy/run_signal.sh`（同样读 `active.yaml`）。
`com.fcstlab.signal.plist` 是 launchd 配置（路径指向 Mac 本地）。

---

## 3. 已归档 (deploy/archive/) 🗄️

| 前缀 | 含义 |
|---|---|
| `DEPRECATED_cloudrun_*` | Cloud Run 整套 (2026-06-02 停用) |
| `~*` / `v030x*` | 历史各版本 (v0215~v0305) |

历史备查用，**均不可运行**。

---

## 当前生产模型 (active.yaml)

| 槽位 | 模型 | variant | status |
|---|---|---|---|
| primary | e20c-conservative-prune | conservative | live |
| challenger | e8-touch | conservative | paper |
| candidate | e21b-touch-prune | conservative | offline_only |
