# FcstLabPro — 比特币周线反转预测系统

## 项目简介

基于 LightGBM Walk-Forward 的 BTC/USDT **日线级别反转预测系统**，生产部署于 Google Cloud Run。

核心能力：每日自动下载行情 → 特征工程 → 模型推理 → 信号 JSON 生成 → 邮件推送。

**当前生产模型**（Cloud Run Job 每日 UTC 00:05 自动触发）：

| 模型 | 标签策略 | Kappa | Sharpe | MaxDD | 定位 |
|------|----------|-------|--------|-------|------|
| **E1** | directional_filtered (终点) | 0.343 | 0.633 | -12.7% | 🛡️ 风控优先 |
| **E8** | touch_filtered (路径触达) | 0.751 | 0.756 | -21.4% | 💰 收益优先 |

> ⚠️ **不要直接对比 E1 与 E8 的 Kappa** —— touch 标签正例率约为 directional 的 2 倍，任务天然更易，Kappa 不可比；横向对比请看 PnL。详见 [`models/production/SUMMARY.md`](models/production/SUMMARY.md)。

**SOTA 候选**：v0308 系列 **E16b**（touch + Savitzky-Golay 平滑仅 close, Kappa **0.7646**）在离线分类指标上超越 E8，PnL 回测尚未完成、暂未晋升生产。详见 [`experiments/weekly/SUMMARY.md`](experiments/weekly/SUMMARY.md)。

---

## 核心设计理念

| 原则 | 说明 |
|------|------|
| **配置驱动** | 每次实验由一个 YAML 完整定义（数据、特征、标签、模型超参） |
| **实验隔离** | 每次实验生成唯一 ID，所有产物存储在独立目录 |
| **可复现** | `seed=42` + git commit hash → bit-exact 复现（已验证） |
| **模型晋升** | 实验 → `promote_model.py` → `models/production/` → 部署 |
| **分层架构** | Layer 0 数据 → Layer 1 标签 → Layer 2 信号 → Layer 3 验证 → Layer 4 组合 → Layer 5 执行 |

---

## 项目结构

```
FcstLabPro/
├── configs/                          # ⚙️ 实验配置
│   ├── base.yaml                     #   默认配置
│   └── experiments/weekly/           #   v0305 (E1-E14) + v0308 (E15, E16a/b/c)
│
├── src/                              # 📦 核心源码
│   ├── data/                         #   数据下载 & 加载
│   ├── features/                     #   特征工程 (technical, volume, flow, market_structure, external)
│   ├── labels/                       #   标签策略 (directional_filtered, touch_filtered, ...)
│   ├── models/                       #   模型 (LightGBM 为主, torch 模型可选)
│   ├── evaluation/                   #   评估 & PnL 回测
│   ├── experiment/                   #   实验运行 & 追踪
│   ├── backtest/                     #   模块化回测引擎
│   ├── llm/                          #   LLM 信号分析增强
│   └── utils/                        #   工具函数
│
├── scripts/                          # 🛠️ 命令行工具 (29 个)
│   ├── run_experiment.py             #   运行实验
│   ├── promote_model.py              #   晋升模型到生产
│   ├── live_signal.py                #   生产推理 (统一入口)
│   ├── build_signal_json.py          #   信号 JSON 构建
│   ├── send_signal_email.py          #   邮件推送
│   ├── enrich_llm_analysis.py        #   LLM 信号增强 (Gemini)
│   ├── pnl_backtest_v0305.py         #   PnL 回测分析
│   ├── sensitivity_e8.py             #   E8 敏感性扫描 (regime/cost/TP)
│   ├── paper_trading_e1_vs_e8.py     #   E1 vs E8 双模型 paper trading
│   ├── consensus_e1_e8.py            #   E1 + E8 共识信号实验
│   ├── ic_analysis_corrected.py      #   IC 统计分析
│   ├── prob_calibration_analysis.py  #   概率校准分析
│   └── ...                           #   其他分析工具 (约 17 个)
│
├── deploy/                           # 🚀 部署
│   ├── Dockerfile                    #   生产镜像 (LightGBM only, 无 torch)
│   ├── deploy.sh                     #   Cloud Run 一键部署 (build/deploy/scheduler)
│   ├── docker_entrypoint.sh          #   容器入口 (MODEL_NAME 环境变量控制)
│   ├── run_signal.sh                 #   本地双模型一键信号脚本 (macOS)
│   ├── com.fcstlab.signal.plist      #   macOS launchd 定时配置 (本地备份运行)
│   └── archive/                      #   历史版本部署文件 (v0215~v0305)
│
├── models/production/                # 🏭 生产模型
│   ├── SUMMARY.md                    #   E1 vs E8 完整对比 (横向对比唯一权威)
│   ├── e1-conservative/              #   E1 模型 + REPORT.md + gpt_REVIEW.md
│   └── e8-touch/                     #   E8 模型 + REPORT.md + gpt_REVIEW.md
│
├── experiments/                      # 🧪 实验产物
│   ├── registry.json                 #   实验注册表
│   ├── weekly/                       #   活跃实验 + SUMMARY.md
│   │   ├── consensus_E1_E8/          #     E1×E8 共识实验
│   │   ├── v0529_E*_endfix/          #     生产模型复现验证
│   │   ├── weekly_bear_v0305_E1*/    #     E1 生产源实验
│   │   ├── weekly_bear_v0305_E8*/    #     E8 challenger 源实验
│   │   └── weekly_bear_v0308_E16b*/  #     SOTA 候选实验
│   └── archive/                      #   历史实验归档
│
├── data/                             # 📊 数据
│   ├── raw/                          #   BTC/USDT 日线 OHLCV
│   └── external/                     #   FGI, 资金费率, 宏观因子
│
├── docs/                             # 📖 文档 & 代码审查
├── tests/                            # 🧪 测试
├── CLAUDE.md                         #   AI 操作手册 (开发规范)
├── pyproject.toml
└── requirements.txt
```

---

## 快速开始

### 1. 安装

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 2. 运行实验

```bash
# 运行 v0305 E1 去污染实验
python scripts/run_experiment.py \
    --config configs/experiments/weekly/exp_weekly_bear_v0305_E1_decontam.yaml \
    --overwrite

# 运行 PnL 回测
python scripts/pnl_backtest_v0305.py \
    --experiment experiments/weekly/weekly_bear_v0305_E1_decontam \
    --data data/raw/btc_binance_BTCUSDT_1d.csv \
    --take-profit --regime-switch
```

### 3. 晋升模型到生产

```bash
python scripts/promote_model.py \
    --experiment experiments/weekly/weekly_bear_v0305_E1_decontam \
    --name e1-conservative \
    --variant conservative

git add models/production/e1-conservative/
git commit -m "promote: e1-conservative"
```

### 4. 部署

**云端（Google Cloud Run，生产主路径）**：

```bash
MODEL_NAME=e1-conservative ./deploy/deploy.sh    # 一键部署 (build + deploy + scheduler)
MODEL_NAME=e8-touch       ./deploy/deploy.sh
```

详见 [`deploy/README.md`](deploy/README.md)。

**本地定时（macOS launchd，云端镜像备份）**：

```bash
# 加载定时任务（双模型串行，每日本地运行）
launchctl load deploy/com.fcstlab.signal.plist

# 手动触发一次
bash deploy/run_signal.sh
```

---

## 生产信号流水线

```
Cloud Run Job (每日触发)
    │
    ├─ 1. 下载最新 BTC/USDT 日线数据 (Binance API)
    ├─ 2. 特征工程 (129 个特征)
    ├─ 3. LightGBM 推理 → 概率 + 信号
    ├─ 4. 生成信号 JSON (data/live/signals/)
    ├─ 5. [可选] LLM 分析增强
    └─ 6. 邮件推送到指定邮箱
```

---

## 实验体系

### v0305 系列（E1–E14）—— 标签与过滤条件探索

| 实验 | 核心变量 | 结论 |
|------|----------|------|
| E1 | directional_filtered + 去污染 | ✅ **生产模型**（风控优先） |
| E2–E7 | 不同过滤/阈值变体 | ❌ 不如 E1 |
| E8 | touch_filtered（路径触达） | ✅ **生产模型**（收益优先） |
| E9 | touch + 低阈值 | ❌ 信号过多 |
| E10–E12 | 真实资金费率 / 宏观因子 | ❌ 劣化 |
| E13–E14 | 特征精简 | ❌ 劣化 |

### v0308 系列（E15–E16）—— Savitzky-Golay 因果平滑消融

灵感来源：arXiv:2506.05764v2 —— 「数据预处理比模型复杂度更重要」。

| 实验 | 配置 | Kappa | 结论 |
|------|------|-------|------|
| E15 | SG 全列 (w=11, p=3) | 0.7167 | ❌ 平滑 volume 有害 |
| E16a | SG 价格列 (w=7, p=2) | 0.7602 | 高 Recall |
| **E16b** | **SG 仅 close (w=11, p=2)** | **0.7646** | ⭐ **新 SOTA（待 PnL 验证）** |
| E16c | SG 全列 (w=21, p=3) | 0.6825 | ❌ 过度平滑 |

详见 [`experiments/weekly/SUMMARY.md`](experiments/weekly/SUMMARY.md)。

---

## 技术栈

- **Python 3.10+** — 运行环境
- **LightGBM** — 梯度提升模型
- **pandas / numpy** — 数据处理
- **scikit-learn** — ML 工具链
- **PyYAML** — 配置管理
- **joblib** — 模型序列化
- **Google Cloud Run** — 生产部署
- **Docker** — 容器化

---

## 关键文档

| 文档 | 说明 |
|------|------|
| [`CLAUDE.md`](CLAUDE.md) | AI/开发操作手册（实验规范、部署流程、复现验证） |
| [`docs/specs/data_pipeline.md`](docs/specs/data_pipeline.md) | 🔥 **数据链路完整文档**（数据源/训练推理同构/生产流水线/故障回退） |
| [`models/production/SUMMARY.md`](models/production/SUMMARY.md) | E1 vs E8 生产模型完整对比 |
| [`models/production/e1-conservative/REPORT.md`](models/production/e1-conservative/REPORT.md) | E1 生产模型深度报告 |
| [`models/production/e1-conservative/gpt_REVIEW.md`](models/production/e1-conservative/gpt_REVIEW.md) | E1 上线 Go/No-Go 评审 |
| [`models/production/e8-touch/REPORT.md`](models/production/e8-touch/REPORT.md) | E8 生产模型深度报告 |
| [`models/production/e8-touch/gpt_REVIEW.md`](models/production/e8-touch/gpt_REVIEW.md) | E8 上线 Go/No-Go 评审 |
| [`experiments/weekly/SUMMARY.md`](experiments/weekly/SUMMARY.md) | 实验总览 + 当前 SOTA |
| [`deploy/README.md`](deploy/README.md) | 部署架构说明（云端 + 本地） |
| [`docs/cr_0308.md`](docs/cr_0308.md) | 代码审查报告 |
