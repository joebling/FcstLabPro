#!/usr/bin/env python3
"""v0302 Label 实验 - 训练脚本.

使用新的 label 策略训练模型，生成可部署的模型文件。

支持三种 label 策略:
- simple_return: 简单正负收益
- excess_return: 超额收益
- dip_recovery: Dip+Recovery

输出目录结构 (符合项目规范):
    weekly_bull_v0302_{label}_{timestamp}_{short_hash}/
    ├── config.yaml           # 完整配置
    ├── meta.json             # 元信息
    ├── metrics.json          # 汇总指标
    ├── fold_metrics.csv      # 每个 fold 的指标
    ├── feature_importance.csv # 特征重要性
    ├── model.joblib          # 模型
    ├── scaler.joblib         # 标准化器
    ├── feature_cols.joblib   # 特征列
    └── report.md             # 实验报告

Author: FcstLabPro
Date: 2026-02-20
"""

import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import json
import yaml
import numpy as np
import pandas as pd
import joblib
import hashlib
from datetime import datetime
from time import time
from sklearn.metrics import cohen_kappa_score, accuracy_score, f1_score, precision_score, recall_score
from sklearn.preprocessing import StandardScaler

from orion_bix import OrionBixClassifier
from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns
from src.labels.registry import get_label_strategy


def get_git_info():
    """获取 git 信息."""
    try:
        commit = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], 
                                         stderr=subprocess.DEVNULL).decode().strip()
        branch = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                                         stderr=subprocess.DEVNULL).decode().strip()
        status = subprocess.check_output(['git', 'status', '--porcelain'],
                                         stderr=subprocess.DEVNULL).decode().strip()
        dirty = len(status) > 0
        return {'commit': commit, 'branch': branch, 'dirty': dirty}
    except:
        return {'commit': 'unknown', 'branch': 'unknown', 'dirty': False}


def generate_experiment_id(name: str) -> str:
    """生成实验 ID (简化版)."""
    return name


def run_walk_forward_training(X, y, config, purge_gap=0):
    """执行 Walk-Forward 训练和评估."""
    eval_cfg = config['evaluation']
    init_train = eval_cfg['init_train']
    oos_window = eval_cfg['oos_window']
    step = eval_cfg['step']
    model_params = config['model']['params']

    fold_results = []
    all_y_true = []
    all_y_pred = []
    all_y_proba = []
    last_model = None
    last_scaler = None
    feature_importance_list = []

    n_folds = (len(X) - init_train) // step

    for i in range(n_folds):
        train_end = init_train + i * step - purge_gap
        test_start = init_train + i * step
        test_end = min(test_start + oos_window, len(X))

        if train_end <= 0 or test_end <= test_start:
            break

        fold_scaler = StandardScaler()
        X_train = fold_scaler.fit_transform(X[:train_end])
        y_train = y[:train_end]
        X_test = fold_scaler.transform(X[test_start:test_end])
        y_test = y[test_start:test_end]

        if len(np.unique(y_train)) < 2:
            print(f"  Fold {i+1}: 跳过（只有单一类别）")
            continue

        model = OrionBixClassifier(
            n_estimators=model_params.get('n_estimators', 16),
            random_state=model_params.get('random_state', 42),
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        
        if hasattr(model, 'predict_proba'):
            y_proba = model.predict_proba(X_test)
            if y_proba.shape[1] == 2:
                y_proba = y_proba[:, 1]
            else:
                y_proba = np.zeros(len(X_test))
        else:
            y_proba = np.zeros(len(X_test))

        kappa = cohen_kappa_score(y_test, y_pred) if len(np.unique(y_test)) > 1 else 0.0
        acc = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, average='binary', zero_division=0)
        prec = precision_score(y_test, y_pred, average='binary', zero_division=0)
        rec = recall_score(y_test, y_pred, average='binary', zero_division=0)

        fold_results.append({
            'fold': i + 1,
            'train_end': train_end,
            'test_start': test_start,
            'test_size': len(y_test),
            'kappa': kappa,
            'accuracy': acc,
            'f1_binary': f1,
            'precision_binary': prec,
            'recall_binary': rec,
        })

        all_y_true.extend(y_test)
        all_y_pred.extend(y_pred)
        all_y_proba.extend(y_proba)

        print(f"  Fold {i+1}: Kappa={kappa:.4f}, Acc={acc:.4f}, F1={f1:.4f}")

        last_model = model
        last_scaler = fold_scaler

        if hasattr(model, 'feature_importances_'):
            feature_importance_list.append(model.feature_importances_)

    avg_feature_importance = None
    if feature_importance_list:
        avg_feature_importance = np.mean(feature_importance_list, axis=0)

    return last_model, last_scaler, fold_results, all_y_true, all_y_pred, avg_feature_importance


def generate_report(exp_dir: Path, config: dict, metrics: dict, feature_cols: list):
    """生成实验报告."""
    report = f"""# {config['experiment']['name']}

> 实验日期: {datetime.now().strftime('%Y-%m-%d')}
> Label 策略: {config['label']['strategy']}

---

## 一、实验配置

| 参数 | 值 |
|------|-----|
| Label 策略 | {config['label']['strategy']} |
| 预测窗口 T | {config['label']['T']} |
| 初始训练集 | {config['evaluation']['init_train']} |
| OOS 窗口 | {config['evaluation']['oos_window']} |
| Step | {config['evaluation']['step']} |
| Purge Gap | {config['evaluation'].get('purge_gap', 0)} |
| 特征数 | {len(feature_cols)} |
| 模型 | {config['model']['type']} |

---

## 二、评估指标

| 指标 | 值 |
|------|-----|
| Cohen's Kappa (平均) | {metrics['cohen_kappa']:.4f} |
| Cohen's Kappa (整体) | {metrics['cohen_kappa_overall']:.4f} |
| Accuracy | {metrics['accuracy']:.4f} |
| F1 Binary | {metrics['f1_binary']:.4f} |
| 正 Kappa 比例 | {metrics['positive_kappa_ratio']:.1%} |
| Fold 数 | {metrics['n_folds']} |

---

## 三、特征集

{', '.join(config['features']['sets'])}

---

*报告生成: {datetime.now().isoformat()}*
"""
    with open(exp_dir / 'report.md', 'w') as f:
        f.write(report)


def main():
    parser = argparse.ArgumentParser(description='v0302 Label 实验训练')
    parser.add_argument('--label', type=str, default='simple_return',
                        choices=['simple_return', 'excess_return', 'dip_recovery'],
                        help='Label 策略')
    parser.add_argument('--type', type=str, default='bull',
                        choices=['bull', 'bear'],
                        help='模型类型: bull 或 bear')
    parser.add_argument('--T', type=int, default=21, help='预测窗口 (bull=21, bear=28)')
    parser.add_argument('--output', type=str, default=None, help='输出目录')
    parser.add_argument('--init-train', type=int, default=800, help='初始训练集大小')
    parser.add_argument('--oos-window', type=int, default=63, help='OOS 窗口')
    parser.add_argument('--step', type=int, default=42, help='步长 (增大可减少训练时间)')
    parser.add_argument('--purge-gap', type=int, default=21, help='训练测试间隔（防泄漏）')
    args = parser.parse_args()

    start_time = time()
    
    model_type = args.type
    experiment_name = f"weekly_{model_type}_v0302_{args.label}"
    experiment_id = generate_experiment_id(experiment_name)
    
    output_dir = args.output or f"experiments/weekly/{experiment_id}"

    print("=" * 60)
    print(f"v0302 Label 实验 - {model_type} - {args.label}")
    print(f"实验 ID: {experiment_id}")
    print("=" * 60)

    if model_type == 'bull':
        model_config = {
            'type': 'orion_bix',
            'params': {'n_estimators': 16, 'random_state': 42}
        }
        feature_sets = ['technical', 'volume', 'flow', 'market_structure', 'external_fgi', 'regime']
    else:
        model_config = {
            'type': 'lightgbm',
            'params': {
                'n_estimators': 100, 'max_depth': 6, 'learning_rate': 0.05,
                'num_leaves': 31, 'subsample': 0.8, 'colsample_bytree': 0.8,
                'min_child_samples': 20, 'reg_alpha': 0.1, 'reg_lambda': 0.1,
                'random_state': 42, 'verbose': -1, 'auto_scale_pos_weight': True
            }
        }
        feature_sets = ['technical', 'volume', 'flow', 'market_structure', 'external_fgi']

    config = {
        'experiment': {
            'name': experiment_name,
            'description': f'v0302 Label 实验: {model_type} - {args.label}',
            'tags': ['weekly', model_type, 'v0302', args.label],
            'category': 'weekly',
        },
        'data': {
            'path': 'data/raw/btc_binance_BTCUSDT_1d.csv',
            'source': 'binance',
            'symbol': 'BTCUSDT',
            'interval': '1d',
        },
        'features': {
            'sets': feature_sets,
            'scaling': 'standard' if model_type == 'bull' else None,
            'drop_na_method': 'ffill_then_drop',
        },
        'label': {
            'strategy': args.label,
            'T': args.T,
        },
        'model': model_config,
        'evaluation': {
            'method': 'walk_forward',
            'init_train': args.init_train,
            'oos_window': args.oos_window,
            'step': args.step,
            'purge_gap': args.purge_gap,
            'metrics': ['accuracy', 'f1_binary', 'precision_binary', 'recall_binary', 'cohen_kappa'],
        },
        'seed': 42,
    }

    print(f"Label 策略: {args.label}")
    print(f"预测窗口 T: {args.T}")
    print(f"输出目录: {output_dir}")

    print("\n加载数据...")
    data_path = PROJECT_ROOT / config['data']['path']
    df = load_csv(str(data_path))
    print(f"原始数据: {len(df)} 条")

    print("构建特征...")
    df = build_features(
        df,
        feature_sets=config['features']['sets'],
        drop_na_method=config['features']['drop_na_method'],
    )

    print(f"生成标签: {args.label}...")
    label_func = get_label_strategy(args.label)
    
    label_kwargs = {'T': args.T}
    if args.label == 'dip_recovery':
        label_kwargs['dip_threshold'] = 0.05
        label_kwargs['recovery_threshold'] = 0.03
    elif args.label == 'excess_return':
        label_kwargs['rolling_window'] = 63

    labels = label_func(df, **label_kwargs)

    df['label'] = labels
    df = df.dropna(subset=['label'])
    df['label'] = df['label'].astype(int)

    feature_cols = get_feature_columns(df)
    X = df[feature_cols].values
    y = df['label'].values

    print(f"有效样本: {len(X)}, 特征数: {len(feature_cols)}")
    print(f"类别分布: {dict(zip(*np.unique(y, return_counts=True)))}")

    print(f"\nWalk-Forward 训练 (purge_gap={args.purge_gap})...")
    model, scaler, fold_results, all_y_true, all_y_pred, feature_importance = run_walk_forward_training(
        X, y, config, purge_gap=args.purge_gap
    )

    if model is None:
        print("❌ 训练失败，没有有效的 fold")
        return

    duration = time() - start_time
    exp_dir = PROJECT_ROOT / output_dir
    exp_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n保存模型到 {exp_dir}...")
    joblib.dump(model, exp_dir / 'model.joblib')
    joblib.dump(scaler, exp_dir / 'scaler.joblib')
    joblib.dump(feature_cols, exp_dir / 'feature_cols.joblib')

    with open(exp_dir / 'config.yaml', 'w') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    fold_df = pd.DataFrame(fold_results)
    fold_df.to_csv(exp_dir / 'fold_metrics.csv', index=False)

    if feature_importance is not None:
        fi_df = pd.DataFrame({
            'feature': feature_cols,
            'importance': feature_importance,
        }).sort_values('importance', ascending=False)
        fi_df.to_csv(exp_dir / 'feature_importance.csv', index=False)

    overall_kappa = cohen_kappa_score(all_y_true, all_y_pred)
    metrics = {
        'cohen_kappa': float(np.mean([r['kappa'] for r in fold_results])),
        'cohen_kappa_overall': float(overall_kappa),
        'accuracy': float(np.mean([r['accuracy'] for r in fold_results])),
        'f1_binary': float(np.mean([r['f1_binary'] for r in fold_results])),
        'precision_binary': float(np.mean([r['precision_binary'] for r in fold_results])),
        'recall_binary': float(np.mean([r['recall_binary'] for r in fold_results])),
        'positive_kappa_ratio': float(np.mean([r['kappa'] > 0 for r in fold_results])),
        'n_folds': len(fold_results),
    }
    with open(exp_dir / 'metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2)

    git_info = get_git_info()
    meta = {
        'experiment_id': experiment_id,
        'name': experiment_name,
        'description': config['experiment']['description'],
        'tags': config['experiment']['tags'],
        'category': config['experiment']['category'],
        'created_at': datetime.now().isoformat(),
        'git': git_info,
        'seed': config['seed'],
        'status': 'completed',
        'duration_seconds': round(duration, 2),
        'label_strategy': args.label,
        'T': args.T,
        'n_features': len(feature_cols),
        'n_folds': len(fold_results),
        'aggregate_metrics': metrics,
    }
    with open(exp_dir / 'meta.json', 'w') as f:
        json.dump(meta, f, indent=2)

    generate_report(exp_dir, config, metrics, feature_cols)

    print("\n" + "=" * 60)
    print("训练完成!")
    print("=" * 60)
    print(f"  实验ID: {experiment_id}")
    print(f"  Fold 数: {len(fold_results)}")
    print(f"  平均 Kappa: {metrics['cohen_kappa']:.4f}")
    print(f"  整体 Kappa: {overall_kappa:.4f}")
    print(f"  正 Kappa 比例: {metrics['positive_kappa_ratio']:.1%}")
    print(f"  耗时: {duration:.1f}s")
    print(f"\n文件已保存到: {exp_dir}")
    print("\n生成的文件:")
    for f in ['config.yaml', 'meta.json', 'metrics.json', 'fold_metrics.csv', 
              'feature_importance.csv', 'model.joblib', 'scaler.joblib', 
              'feature_cols.joblib', 'report.md']:
        print(f"  - {f}")


if __name__ == '__main__':
    main()
