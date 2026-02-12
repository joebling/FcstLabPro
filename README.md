# FcstLabPro — 比特币价格预测实验平台

## 项目简介

基于机器学习的比特币价格反转预测系统，核心设计目标：**实验可追溯、版本可对比、配置驱动、模块解耦**。

当前支持日线级别预测，架构预留周线预测扩展能力。

## 核心设计理念

| 原则 | 说明 |
|------|------|
| **配置驱动** | 每次实验由一个 YAML 配置文件完整定义（数据源、特征集、标签参数、模型超参） |
| **实验隔离** | 每次实验生成唯一 `experiment_id`，所有产物（模型、指标、报告）存储在独立目录 |
| **自动报告** | 训练/回测完成后自动生成 Markdown 实验报告 |
| **对比分析** | 内置实验对比工具，可跨版本对比指标、特征重要性、equity curve |
| **可复现** | 配置 + git commit hash + 随机种子 → 完全可复现 |

## 项目结构

```
FcstLabPro/
├── configs/                          # ⚙️ 实验配置（YAML）
│   ├── base.yaml                     #   基础默认配置
│   └── experiments/                  #   每次实验的配置文件
│       ├── exp_001_baseline.yaml
│       └── exp_002_flow_features.yaml
│
├── src/                              # 📦 核心源码（Python包）
│   ├── __init__.py
│   ├── data/                         #   数据层
│   │   ├── __init__.py
│   │   ├── downloader.py             #     数据下载（Binance/Yahoo）
│   │   ├── loader.py                 #     数据加载与校验
│   │   └── splitter.py               #     数据集划分（WalkForward等）
│   ├── features/                     #   特征工程层
│   │   ├── __init__.py
│   │   ├── registry.py               #     特征集注册表
│   │   ├── technical.py              #     技术指标特征
│   │   ├── volume.py                 #     成交量特征
│   │   ├── flow.py                   #     资金流特征
│   │   └── builder.py                #     特征构建器（按配置组装）
│   ├── labels/                       #   标签层
│   │   ├── __init__.py
│   │   ├── reversal.py               #     反转标签生成
│   │   └── registry.py               #     标签策略注册表
│   ├── models/                       #   模型层
│   │   ├── __init__.py
│   │   ├── registry.py               #     模型注册表
│   │   ├── lgbm.py                   #     LightGBM 实现
│   │   └── base.py                   #     模型基类
│   ├── evaluation/                   #   评估层
│   │   ├── __init__.py
│   │   ├── metrics.py                #     评估指标计算
│   │   ├── backtest.py               #     回测引擎
│   │   └── comparison.py             #     实验对比分析
│   ├── experiment/                   #   实验管理层（核心）
│   │   ├── __init__.py
│   │   ├── config.py                 #     配置加载与合并
│   │   ├── runner.py                 #     实验运行器
│   │   ├── tracker.py                #     实验追踪器（记录全流程）
│   │   └── reporter.py               #     报告生成器
│   └── utils/                        #   工具函数
│       ├── __init__.py
│       ├── io.py                     #     文件读写
│       ├── logging.py                #     日志配置
│       └── reproducibility.py        #     可复现性工具
│
├── scripts/                          # 🛠️ 命令行入口
│   ├── run_experiment.py             #   运行单次实验
│   ├── compare_experiments.py        #   对比多个实验
│   ├── download_data.py              #   下载数据
│   ├── predict.py                    #   生产预测
│   └── param_search.py              #   参数搜索
│
├── data/                             # 📊 数据文件（git忽略大文件）
│   └── raw/                          #   原始数据
│
├── experiments/                      # 🧪 实验产物（核心目录）
│   ├── registry.json                 #   实验注册表（索引）
│   └── {experiment_id}/              #   每个实验独立目录
│       ├── config.yaml               #     本次实验的完整配置快照
│       ├── meta.json                 #     元信息（时间、git hash、耗时等）
│       ├── metrics.json              #     评估指标
│       ├── fold_metrics.csv          #     Walk-Forward 各 fold 指标
│       ├── feature_importance.csv    #     特征重要性
│       ├── model.joblib              #     模型文件
│       ├── predictions.csv           #     预测结果
│       └── report.md                 #     自动生成的实验报告
│
├── reports/                          # 📋 对比报告
│   └── compare_{id1}_vs_{id2}.md     #   实验对比报告
│
├── tests/                            # 🧪 单元测试
│   ├── test_features.py
│   ├── test_labels.py
│   ├── test_models.py
│   └── test_experiment.py
│
├── notebooks/                        # 📓 探索性分析
│
├── requirements.txt
├── pyproject.toml
└── .gitignore
```

## 快速开始

### 1. 安装
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 2. 下载数据
```bash
python scripts/download_data.py --symbol BTCUSDT --interval 1d --start 2018-01-01
```

### 3. 运行实验
```bash
# 使用配置文件运行
python scripts/run_experiment.py --config configs/experiments/exp_001_baseline.yaml

# 快速覆盖参数
python scripts/run_experiment.py --config configs/experiments/exp_001_baseline.yaml \
  --override label.T=21 label.X=0.08
```

### 4. 对比实验
```bash
python scripts/compare_experiments.py --ids exp_001 exp_002 --output reports/
```

## 实验工作流

```
编写/复制 YAML 配置
        │
        ▼
  run_experiment.py
        │
        ├─ 1. 加载配置 + 生成 experiment_id
        ├─ 2. 下载/加载数据
        ├─ 3. 特征工程（按配置选择特征集）
        ├─ 4. 标签生成（按配置选择 T, X）
        ├─ 5. Walk-Forward 训练 + 评估
        ├─ 6. 保存模型 + 指标 + 预测结果
        ├─ 7. 生成实验报告 (Markdown)
        └─ 8. 更新实验注册表 registry.json
```

## 配置示例

```yaml
experiment:
  name: "baseline_T14_X8"
  description: "基线模型，14天窗口，8%阈值"
  tags: ["baseline", "v1"]

data:
  source: "binance"
  symbol: "BTCUSDT"
  interval: "1d"
  start: "2018-01-01"
  end: "2025-12-31"
  path: "data/raw/btc_binance_BTCUSDT_1d.csv"

features:
  sets: ["technical", "volume"]    # 使用的特征集
  # sets: ["technical", "volume", "flow"]  # 加入资金流特征

label:
  strategy: "reversal"
  T: 14        # 窗口长度
  X: 0.08      # 阈值

model:
  type: "lightgbm"
  params:
    n_estimators: 500
    max_depth: 6
    learning_rate: 0.05
    num_leaves: 31
    subsample: 0.8
    colsample_bytree: 0.8

evaluation:
  method: "walk_forward"
  init_train: 1500
  oos_window: 63
  step: 21
  metrics: ["accuracy", "f1_macro", "precision", "recall"]

seed: 42
```

## 技术栈
- Python 3.10+
- pandas / numpy — 数据处理
- LightGBM — 梯度提升模型
- scikit-learn — ML工具
- PyYAML — 配置管理
- joblib — 模型序列化
- tabulate — 报告格式化
