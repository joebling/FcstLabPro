# 📧 E1 邮件模板改造设计稿

**日期**: 2026-03-08  
**状态**: 待确认  
**涉及文件**:
- `scripts/send_signal_email.py` — 邮件模板 + 发送逻辑
- `deploy/docker_entrypoint_v0305.sh` Step 5 — 信号 JSON 生成
- `src/llm/analyst.py` — LLM System Prompt (可选)

---

## 一、问题诊断

当前 `send_signal_email.py` 是 v0302 双模型时代的产物，与 E1 单模型架构有 **7 处不匹配**：

| # | 问题 | 现状 | 影响 |
|---|------|------|------|
| 1 | bull_prob / bear_prob 进度条 | 永远显示 0% | 占位但无信息量 |
| 2 | 信号颜色映射 | BULL/BEAR/NEUTRAL/VOLATILE | E1 用 BUY/HOLD/SELL/SILENT，颜色全灰 |
| 3 | 模型信息区块 | `Bull=N/A, Bear=N/A` | key 对不上，全显示 N/A |
| 4 | 邮件标题 | "Bull T=21天 / Bear T=28天" | E1 是单模型 T=21 |
| 5 | 邮件主题行 | `Bull=N/A, Bear=N/A` | 同上 |
| 6 | 缺少 E1 关键信息 | — | Regime、持仓 PnL、历史胜率、信号原因 |
| 7 | LLM System Prompt | 描述 v0218 双模型 | 应更新为 E1 单模型描述 |

---

## 二、新信号 JSON 格式

**改动位置**: `docker_entrypoint_v0305.sh` Step 5

把现在的 "兼容 v0302" 格式改为 E1 原生格式：

```json
{
  "date": "2026-03-08",
  "price": 85432.10,

  "signal": "BUY",
  "signal_display": "🟢 买入",
  "reason": "模型信号: y_pred=1 (预测跌后反弹)",

  "regime": "非熊市",
  "regime_detail": "63d 滚动收益 = +12.3% (threshold=-10%)",

  "position": {
    "in_position": true,
    "entry_date": "2026-03-08",
    "entry_price": 85432.10,
    "days_held": 0,
    "floating_pnl": 0.0
  },

  "history": {
    "total_trades": 5,
    "wins": 3,
    "win_rate": 0.60,
    "avg_pnl": 0.0123,
    "total_pnl": 0.0615,
    "recent": [
      {"entry": "03-01", "exit": "03-05", "pnl": "+4.2%", "reason": "止盈"},
      {"entry": "02-15", "exit": "02-28", "pnl": "-1.3%", "reason": "到期"}
    ]
  },

  "model": {
    "name": "E1 Conservative",
    "version": "v0305",
    "type": "LightGBM",
    "label": "directional_filtered",
    "features": 129,
    "kappa": 0.19,
    "variant": "止盈+regime",
    "backtest": {
      "cagr": "9.8%",
      "max_dd": "-12.7%",
      "pf": 1.32,
      "sharpe": 0.63
    }
  },

  "strategy": {
    "T": 21,
    "X": 0.04,
    "take_profit": true,
    "regime_switch": true
  },

  "risk_notes": [
    "策略变体: conservative (止盈+regime)",
    "回测 CAGR=9.8%, MaxDD=-12.7%, PF=1.32"
  ],

  "llm_analysis": null
}
```

**变更要点**:
- ❌ 删除: `bull_prob`, `bear_prob`, `position_pct`, `action`
- ❌ 删除: `model_version.bull/bear`, `kappa.bull/bear` 等双模型字段
- ✅ 新增: `reason`, `regime`, `regime_detail`
- ✅ 新增: `position` 对象 (持仓状态)
- ✅ 新增: `history` 对象 (历史战绩汇总 + 最近 2 笔)
- ✅ 新增: `model` 对象 (单模型元信息 + 回测指标)
- ✅ 新增: `strategy` 对象 (策略参数)

---

## 三、新邮件模板设计

### 3.1 邮件主题行

```
旧: [BTC信号] 2026-03-08 🟢 买入 (E1 v0305) — FcstLabPro Bull=N/A, Bear=N/A
新: [BTC] 03-08 🟢 买入 | $85,432 | E1 v0305
```

更简洁，手机通知栏一眼看到关键信息。

### 3.2 HTML 邮件布局

```
┌──────────────────────────────────────────────┐
│  🔮 FcstLabPro E1 每日信号                    │
│  2026-03-08 · BTC/USDT · T=21 止盈+regime    │
├──────────────────────────────────────────────┤
│                                              │
│  ┌─ 价格 ──────────────────────────────────┐ │
│  │  $85,432.10                             │ │
│  └─────────────────────────────────────────┘ │
│                                              │
│  ┌─ 信号 ─ 🟢 绿色左边框 ─────────────────┐ │
│  │  🟢 买入                                │ │
│  │  模型信号: y_pred=1 (预测跌后反弹)       │ │
│  └─────────────────────────────────────────┘ │
│                                              │
│  ┌─ 市场状态 ──────────────────────────────┐ │
│  │  Regime: 🟢 非熊市                      │ │
│  │  63d 滚动收益 = +12.3%                  │ │
│  └─────────────────────────────────────────┘ │
│                                              │
│  ┌─ 持仓状态 (仅持仓中显示) ───────────────┐ │
│  │  买入价: $83,200  |  买入日: 03-05       │ │
│  │  浮盈: +2.68%     |  持仓: 第3天/21天    │ │
│  │  ██████████░░░░░░░░░░  3/21              │ │
│  └─────────────────────────────────────────┘ │
│                                              │
│  ┌─ 历史战绩 ──────────────────────────────┐ │
│  │  已完成 5 笔 | 胜率 60% | 均盈 +1.23%   │ │
│  │  ─────────────────────────────────────   │ │
│  │  03-01→03-05  +4.2%  止盈 ✅            │ │
│  │  02-15→02-28  -1.3%  到期 ❌            │ │
│  └─────────────────────────────────────────┘ │
│                                              │
│  ┌─ 🤖 AI 策略解读 (Gemini) ───────────────┐ │
│  │  (LLM 生成的分析内容)                    │ │
│  └─────────────────────────────────────────┘ │
│                                              │
│  ┌─ 模型信息 (折叠感/小字) ────────────────┐ │
│  │  E1 Conservative | LightGBM | 129特征    │ │
│  │  directional_filtered (去污染)           │ │
│  │  Kappa=0.19 | CAGR=9.8% | MaxDD=-12.7%  │ │
│  │  T=21天 X=4% | 止盈+regime              │ │
│  └─────────────────────────────────────────┘ │
│                                              │
│  ── 免责声明 ────────────────────────────── │
│  ⚠️ 本信号由 FcstLabPro 自动生成，Kappa=0.19│
│  不构成投资建议。                            │
└──────────────────────────────────────────────┘
```

### 3.3 四种信号的视觉设计

| 信号 | Emoji | 颜色 | 左边框 | 场景 |
|------|-------|------|--------|------|
| **BUY** | 🟢 | `#22c55e` 绿 | 绿色 | 模型预测 y=1，开仓 |
| **HOLD** | 🟡 | `#f59e0b` 琥珀 | 琥珀色 | 已持仓，等待退出条件 |
| **SELL** | 🔴 | `#ef4444` 红 | 红色 | 止盈/到期/regime平仓 |
| **SILENT** | ⚪ | `#6b7280` 灰 | 灰色 | 无信号或 regime 静默 |

### 3.4 持仓状态卡片逻辑

| 条件 | 显示 |
|------|------|
| `position.in_position = false` | 不显示持仓卡片 |
| `position.in_position = true` | 显示: 买入价、浮盈、持仓天数进度条 |
| `signal = SELL` | 显示: 平仓信息 (本次盈亏、持仓天数、平仓原因) |

### 3.5 历史战绩卡片逻辑

| 条件 | 显示 |
|------|------|
| `history.total_trades = 0` | 显示: "尚无历史交易" |
| `history.total_trades > 0` | 显示: 总笔数、胜率、均盈 + 最近 2 笔明细 |

---

## 四、纯文本备用 (Plain Text)

```
FcstLabPro E1 每日信号
══════════════════════════════
日期: 2026-03-08
价格: $85,432.10
信号: 🟢 买入
原因: 模型信号: y_pred=1 (预测跌后反弹)
Regime: 非熊市 (63d收益=+12.3%)

持仓: 买入于 03-05 @ $83,200, 浮盈 +2.68%, 第3天
战绩: 5 笔 | 胜率 60% | 均盈 +1.23%

模型: E1 Conservative v0305
  LightGBM | 129特征 | Kappa=0.19
  CAGR=9.8% | MaxDD=-12.7% | PF=1.32
══════════════════════════════
⚠️ 不构成投资建议
```

---

## 五、LLM Prompt 更新 (可选)

`src/llm/analyst.py` 的 `SYSTEM_PROMPT` 还在描述 v0218 双模型架构：
- "Orion-BiX 表格神经网络" → E1 不用 Orion
- "Bull 模型 + Bear 模型" → E1 是单模型
- "信号反转策略" → E1 不反转

**建议**: 重写 System Prompt 为 E1 描述，但这个可以后面单独做，
不影响邮件模板的改造。

---

## 六、改动范围总结

| 文件 | 改动量 | 说明 |
|------|--------|------|
| `scripts/send_signal_email.py` | **重写** | `build_html()` 全新模板；`send_email()` 小改 |
| `deploy/docker_entrypoint_v0305.sh` | **Step 5 重写** | 新 JSON 格式 |
| `src/llm/analyst.py` | 可选 | System Prompt 更新为 E1 描述 |
| `tests/test_email_content.py` | **需更新** | 适配新 JSON 格式 |

### 不动的部分
- `scripts/live_signal.py` — 推理逻辑不变
- `deploy/deploy_v0305.sh` — 部署脚本不变
- SMTP 配置 — 不变
- 邮件发送逻辑 (`smtplib`) — 不变

---

## 七、多模型部署架构

### 7.1 核心思路：一套代码，环境变量切模型

现状问题：`deploy_v0305.sh` 和 `docker_entrypoint_v0305.sh` 全是 E1 硬编码。
如果部署 E8 就得 copy-paste 一套，违反 DRY。

**方案：以 `MODEL_NAME` 环境变量为枢纽，所有组件按约定找对应文件。**

```
models/production/
  ├── e1-conservative/     # manifest.json, model.joblib, config.yaml
  └── e8-touch/            # manifest.json, model.joblib, config.yaml
          │
          └─── MODEL_NAME 由此目录名决定
```

### 7.2 部署指令

```bash
# 部署 E1 (风控优先)
MODEL_NAME=e1-conservative ./deploy/deploy.sh

# 部署 E8 (收益优先)
MODEL_NAME=e8-touch ./deploy/deploy.sh

# 未来的 E15…
MODEL_NAME=e15-whatever ./deploy/deploy.sh
```

### 7.3 资源隔离

每个模型部署后拥有独立的：

| 资源 | E1 | E8 |
|--------|-----|-----|
| Cloud Run Job | `daily-btc-signal-e1-conservative` | `daily-btc-signal-e8-touch` |
| Scheduler | `trigger-e1-conservative` | `trigger-e8-touch` |
| GCS 状态路径 | `gs://bucket/e1-conservative/` | `gs://bucket/e8-touch/` |
| 持仓状态 | 独立的 signal_state.json | 独立的 signal_state.json |
| 邮件主题 | `[BTC] E1 🟢 买入` | `[BTC] E8 🟢 买入` |

**但共享：**
- 同一个 Docker 镜像 (两个模型都打包在里)
- 同一套代码 (`live_signal.py`, `send_signal_email.py`, `docker_entrypoint.sh`)
- 同一个 SMTP 配置

### 7.4 关键流转: 从 manifest.json 自动填充邮件内容

这是最巧妙的部分 —— **邮件模板不需要知道它在渲染哪个模型**。

```
docker_entrypoint.sh
  │
  ├─ 读取 MODEL_NAME 环境变量
  ├─ 加载 models/production/{MODEL_NAME}/manifest.json
  ├─ 调用 live_signal.py --model {MODEL_NAME}/model.joblib --config {MODEL_NAME}/config.yaml
  ├─ 从 manifest.json 提取模型元信息，填充到信号 JSON
  └─ send_signal_email.py 读取 JSON，渲染邮件

manifest.json 提供：
  - name          → 邮件标题 ("E1 Conservative" / "E8 Touch")
  - strategy.*    → 策略信息 (label, T, X)
  - features.*    → 特征信息 (sets, count)
  - metrics.*     → 回测指标 (Kappa, CAGR, MaxDD, PF)
  - model.*       → 模型类型 (lightgbm, sha256)
  - deployment.*  → 部署变体 (conservative, cli_flags)
```

**结果：E8 部署时不需要改一行代码，只需要 `MODEL_NAME=e8-touch`。**

### 7.5 文件变更计划

```
改动前 (E1 硬编码):                    改动后 (模型无关):

deploy/deploy_v0305.sh             →  deploy/deploy.sh          # MODEL_NAME 参数化
deploy/docker_entrypoint_v0305.sh  →  deploy/docker_entrypoint.sh # MODEL_NAME 参数化
deploy/Dockerfile.v0305            →  deploy/Dockerfile          # 打包所有模型
scripts/send_signal_email.py       →  scripts/send_signal_email.py # 渲染 JSON 即可
scripts/live_signal.py             →  (不变)                       # 已经模型无关
```

旧文件的 `_v0305` 后缀可以保留在 `deploy/archive/` 中备查。

---

## 八、兼容性

- 新模板 **不兼容** v0302 的 JSON 格式 (有意为之，v0302 已下线)
- E1 和 E8 共用同一套代码，通过 `MODEL_NAME` 切换
- 未来新模型只需要 `models/production/{name}/` 目录 + `manifest.json` 即可部署

---

## 九、风险点

1. **Gemini LLM 分析**: Walmart 内网不通，GCP 上可通。本地测试时 `llm_analysis=null`，邮件中该区块不显示，无影响。
2. **历史战绩为空**: 首次部署 `history.total_trades=0`，模板会显示 "尚无历史交易"，不会报错。
3. **邮件客户端兼容性**: QQ 邮箱对 HTML 邮件支持良好，进度条用 `div+width%` 实现，不用 `<progress>` 标签。
4. **E1/E8 并行部署**: 状态完全隔离（独立 GCS 路径），互不干扰。但每天会收到两封邮件。
