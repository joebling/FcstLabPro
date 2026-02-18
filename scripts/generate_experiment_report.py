#!/usr/bin/env python3
"""生成实验报告."""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import json
import yaml
import pandas as pd
from datetime import datetime

# 导入 PnL 计算模块
from src.evaluation.pnl import calculate_pnl_metrics


def run_pnl_backtest(exp_dir):
    """运行 PnL 回测."""
    pred_path = f'{exp_dir}/predictions.csv'
    if not os.path.exists(pred_path):
        return None

    pred_df = pd.read_csv(pred_path)

    prices_df = pd.read_csv('data/raw/btc_binance_BTCUSDT_1d.csv')
    prices_df['date'] = pd.to_datetime(prices_df['date'])
    prices_df = prices_df.sort_values('date').reset_index(drop=True)

    y_true = pred_df['y_true'].values
    y_pred = pred_df['y_pred'].values
    prices = prices_df['close']

    min_len = min(len(y_true), len(prices))
    y_true = y_true[:min_len]
    y_pred = y_pred[:min_len]
    prices = prices.iloc[:min_len]

    pnl = calculate_pnl_metrics(
        y_true=y_true,
        y_pred=y_pred,
        prices=prices,
        position_size=1.0,
        transaction_cost=0.001,
        risk_free_rate=0.0,
        periods_per_year=52.0,
    )

    return {
        'cagr': pnl.cagr,
        'max_drawdown': pnl.max_drawdown,
        'calmar': pnl.calmar,
        'sharpe': pnl.sharpe,
        'num_trades': pnl.num_trades,
        'win_rate': pnl.win_rate,
    }


def generate_report(exp_dir):
    """生成实验报告."""
    config_path = f'{exp_dir}/config.yaml'
    if not os.path.exists(config_path):
        print(f"配置文件不存在: {config_path}")
        return

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    with open(f'{exp_dir}/metrics.json', 'r') as f:
        metrics = json.load(f)

    fold_df = pd.read_csv(f'{exp_dir}/fold_metrics.csv')

    with open(f'{exp_dir}/meta.json', 'r') as f:
        meta = json.load(f)

    pnl = run_pnl_backtest(exp_dir)

    # 生成报告
    lines = []
    lines.append(f"# 实验报告: {meta['experiment_name']}")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # 1. 实验概要
    lines.append("## 1. 实验概要")
    lines.append("")
    lines.append("| 项目 | 值 |")
    lines.append("|------|------|")
    lines.append(f"| 实验名称 | {config['experiment']['name']} |")
    lines.append(f"| 描述 | {config['experiment']['description']} |")
    lines.append(f"| 标签 | {config['experiment']['tags']} |")
    lines.append(f"| 模型类型 | {config['model']['type']} |")
    lines.append(f"| 随机种子 | {config.get('seed', 'N/A')} |")
    lines.append("")

    # 2. 数据配置
    lines.append("## 2. 数据配置")
    lines.append("")
    lines.append(f"- **数据源**: {config['data']['source']}")
    lines.append(f"- **交易对**: {config['data']['symbol']}")
    lines.append(f"- **周期**: {config['data']['interval']}")
    lines.append(f"- **时间范围**: {config['data']['start']} ~ {config['data']['end']}")
    lines.append(f"- **数据文件**: `{config['data']['path']}`")
    lines.append("")

    # 3. 特征配置
    lines.append("## 3. 特征配置")
    lines.append("")
    lines.append(f"- **特征集**: {config['features']['sets']}")
    lines.append(f"- **总特征数**: {meta['n_features']}")
    lines.append(f"- **NaN处理**: {config['features']['drop_na_method']}")
    lines.append("")

    # 4. 标签配置
    lines.append("## 4. 标签配置")
    lines.append("")
    lines.append(f"- **策略**: {config['label']['strategy']}")
    lines.append(f"- **窗口 T**: {config['label']['T']} 天")
    lines.append(f"- **阈值 X**: {config['label']['X']} ({config['label']['X']*100}%)")
    lines.append("")

    # 5. 模型配置
    lines.append("## 5. 模型配置")
    lines.append("")
    lines.append(f"- **类型**: {config['model']['type']}")
    lines.append("- **参数**:")
    for k, v in config['model']['params'].items():
        lines.append(f"  - {k}: {v}")
    lines.append("")

    # 6. 评估结果
    lines.append("## 6. 评估结果（汇总）")
    lines.append("")
    lines.append("| 指标               |      值 |")
    lines.append("|:-----------------|-------:|")
    lines.append(f"| cohen_kappa      | {metrics['cohen_kappa']:.4f} |")
    lines.append(f"| accuracy         | {metrics['accuracy']:.4f} |")
    lines.append(f"| f1_binary        | {metrics['f1_binary']:.4f} |")
    lines.append(f"| 正 Kappa 比例    | {metrics['positive_kappa_ratio']:.1%} |")
    lines.append("")

    # 7. PnL 回测结果
    if pnl:
        lines.append("## 7. PnL 回测结果")
        lines.append("")
        lines.append("| 指标               |      值 |")
        lines.append("|:-----------------|-------:|")
        lines.append(f"| 年化收益 (CAGR)   | {pnl['cagr']:.2%} |")
        lines.append(f"| 最大回撤           | {pnl['max_drawdown']:.2%} |")
        lines.append(f"| 卡玛比率           | {pnl['calmar']:.2f} |")
        lines.append(f"| 夏普比率           | {pnl['sharpe']:.2f} |")
        lines.append(f"| 交易次数           | {pnl['num_trades']} |")
        lines.append(f"| 胜率               | {pnl['win_rate']:.1%} |")
        lines.append("")
        section_num = "8"
    else:
        section_num = "7"

    # 8/7. Walk-Forward Fold 详情
    lines.append(f"## {section_num}. Walk-Forward Fold 详情")
    lines.append("")
    lines.append(f"- **方法**: {config['evaluation']['method']}")
    lines.append(f"- **初始训练集**: {config['evaluation']['init_train']}")
    lines.append(f"- **OOS窗口**: {config['evaluation']['oos_window']}")
    lines.append(f"- **步进**: {config['evaluation']['step']}")
    lines.append(f"- **总 Fold 数**: {len(fold_df)}")
    lines.append("")
    lines.append("|   fold_id |   train_end |   kappa |   accuracy |   f1 |")
    lines.append("|----------:|------------:|--------:|----------:|-----:|")

    for i, row in fold_df.iterrows():
        lines.append(f"|    {i+1} | {int(row['train_end'])} | {row['kappa']:.4f} | {row['accuracy']:.4f} | {row['f1']:.4f} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    lines.append("")

    # 添加回测逻辑说明
    lines.append("## PnL 回测代码")
    lines.append("")
    lines.append("```python")
    lines.append("# PnL 回测核心逻辑")
    lines.append("from src.evaluation.pnl import calculate_pnl_metrics")
    lines.append("")
    lines.append("pred_df = pd.read_csv('predictions.csv')")
    lines.append("prices_df = pd.read_csv('data/raw/btc_binance_BTCUSDT_1d.csv')")
    lines.append("prices_df['date'] = pd.to_datetime(prices_df['date'])")
    lines.append("prices_df = prices_df.sort_values('date').reset_index(drop=True)")
    lines.append("")
    lines.append("y_true = pred_df['y_true'].values")
    lines.append("y_pred = pred_df['y_pred'].values")
    lines.append("prices = prices_df['close']")
    lines.append("")
    lines.append("min_len = min(len(y_true), len(prices))")
    lines.append("y_true = y_true[:min_len]")
    lines.append("y_pred = y_pred[:min_len]")
    lines.append("prices = prices.iloc[:min_len]")
    lines.append("")
    lines.append("metrics = calculate_pnl_metrics(")
    lines.append("    y_true=y_true,")
    lines.append("    y_pred=y_pred,")
    lines.append("    prices=prices,")
    lines.append("    position_size=1.0,")
    lines.append("    transaction_cost=0.001,")
    lines.append("    risk_free_rate=0.0,")
    lines.append("    periods_per_year=52.0,")
    lines.append(")")
    lines.append("```")

    report = "\n".join(lines)

    report_path = f'{exp_dir}/report.md'
    with open(report_path, 'w') as f:
        f.write(report)

    print(f"报告已生成: {report_path}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', type=str, required=True, help='实验目录')
    args = parser.parse_args()

    generate_report(args.dir)
