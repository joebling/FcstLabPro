#!/usr/bin/env python3
"""Orion-BiX Walk-Forward 训练与评估脚本.

生成:
- fold_metrics.csv: 每个 fold 的评估指标
- predictions.csv: 所有 OOS 样本的预测结果
- metrics.json: 汇总指标
- meta.json: 实验元信息
- model.joblib: 最终模型
- scaler.joblib: 标准化器
- feature_cols.joblib: 特征列名
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import json
import yaml
import numpy as np
import pandas as pd
import joblib
from datetime import datetime
from sklearn.metrics import cohen_kappa_score, accuracy_score, f1_score
from sklearn.preprocessing import StandardScaler

from orion_bix import OrionBixClassifier
from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns

# 导入标签模块以注册策略
import src.labels.reversal
from src.labels.registry import get_label_strategy


def load_config(config_path):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Orion-BiX Walk-Forward 训练')
    parser.add_argument('--config', type=str, default='configs/experiments/weekly/exp_weekly_bull_v27_orion_0218.yaml',
                        help='配置文件路径')
    parser.add_argument('--output', type=str, default='experiments/weekly/weekly_bull_v27_orion_0218',
                        help='输出目录')
    args = parser.parse_args()

    print("="*80)
    print("Orion-BiX Walk-Forward 训练")
    print("="*80)

    # 1. 加载配置
    config = load_config(args.config)
    exp_dir = args.output
    os.makedirs(exp_dir, exist_ok=True)

    print(f"实验: {config['experiment']['name']}")
    print(f"输出: {exp_dir}")

    # 2. 加载数据
    data_path = config['data']['path']
    print(f"加载数据: {data_path}")
    df = load_csv(data_path)
    print(f"数据: {len(df)} 条")

    # 3. 特征工程
    print("构建特征...")
    df = build_features(
        df,
        feature_sets=config['features']['sets'],
        drop_na_method=config['features'].get('drop_na_method', 'ffill_then_drop'),
    )

    # 4. 标签生成
    label_func = get_label_strategy(config['label']['strategy'])
    labels = label_func(df, T=config['label']['T'], X=config['label']['X'])

    # 应用标签映射
    if 'map' in config['label']:
        mapping = {int(k): int(v) for k, v in config['label']['map'].items()}
        labels = labels.map(mapping)

    df['label'] = labels
    df = df.dropna(subset=['label'])
    df['label'] = df['label'].astype(int)

    # 5. 获取特征
    feature_cols = get_feature_columns(df)
    X = df[feature_cols].values
    y = df['label'].values

    print(f"数据: {len(X)} 样本, {len(feature_cols)} 特征")
    print(f"类别: {np.bincount(y)}")

    # 6. 标准化 (只在最终模型使用，walk-forward 中每步重新 fit)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)  # 仅用于最终模型

    # 7. Walk-Forward 评估
    init_train = config['evaluation']['init_train']
    oos_window = config['evaluation']['oos_window']
    step = config['evaluation']['step']

    print(f"Walk-Forward: init_train={init_train}, oos={oos_window}, step={step}")

    fold_results = []
    all_y_true = []
    all_y_pred = []

    n_folds = (len(X) - init_train) // step
    for i in range(n_folds):
        train_end = init_train + i * step
        test_start = train_end
        test_end = min(train_end + oos_window, len(X))

        if test_end <= test_start:
            break

        # 每步重新 fit scaler (避免数据泄露)
        fold_scaler = StandardScaler()
        X_train = fold_scaler.fit_transform(X[:train_end])
        y_train = y[:train_end]
        X_test = fold_scaler.transform(X[test_start:test_end])
        y_test = y[test_start:test_end]

        # 训练
        model = OrionBixClassifier(
            n_estimators=config['model']['params']['n_estimators'],
            random_state=config['model']['params']['random_state'],
        )
        model.fit(X_train, y_train)

        # 预测
        y_pred = model.predict(X_test)

        # 评估
        kappa = cohen_kappa_score(y_test, y_pred)
        acc = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, average='binary', zero_division=0)

        fold_results.append({
            'train_end': train_end,
            'kappa': kappa,
            'accuracy': acc,
            'f1': f1,
        })

        all_y_true.extend(y_test)
        all_y_pred.extend(y_pred)

        print(f"  Fold {i+1}: Kappa={kappa:.4f}, Acc={acc:.4f}, F1={f1:.4f}")

    # 8. 保存结果
    # fold_metrics.csv
    fold_df = pd.DataFrame(fold_results)
    fold_df.to_csv(f'{exp_dir}/fold_metrics.csv', index=False)

    # predictions.csv
    pred_df = pd.DataFrame({'y_true': all_y_true, 'y_pred': all_y_pred})
    pred_df.to_csv(f'{exp_dir}/predictions.csv', index=False)

    # metrics.json
    overall_kappa = cohen_kappa_score(pred_df['y_true'], pred_df['y_pred'])
    metrics = {
        'cohen_kappa': float(np.mean([r['kappa'] for r in fold_results])),
        'cohen_kappa_overall': float(overall_kappa),
        'accuracy': float(np.mean([r['accuracy'] for r in fold_results])),
        'f1_binary': float(np.mean([r['f1'] for r in fold_results])),
        'positive_kappa_ratio': float(np.mean([r['kappa'] > 0 for r in fold_results])),
    }
    with open(f'{exp_dir}/metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2)

    # meta.json
    meta = {
        'experiment_name': config['experiment']['name'],
        'description': config['experiment']['description'],
        'created_at': datetime.now().isoformat(),
        'model_type': config['model']['type'],
        'n_features': len(feature_cols),
        'n_folds': len(fold_results),
        'init_train': init_train,
        'oos_window': oos_window,
        'step': step,
    }
    with open(f'{exp_dir}/meta.json', 'w') as f:
        json.dump(meta, f, indent=2)

    # 保存模型和预处理对象
    joblib.dump(feature_cols, f'{exp_dir}/feature_cols.joblib')
    joblib.dump(scaler, f'{exp_dir}/scaler.joblib')
    # 保存最后一个 fold 的模型作为最终模型
    joblib.dump(model, f'{exp_dir}/model.joblib')

    # 保存配置
    with open(f'{exp_dir}/config.yaml', 'w') as f:
        yaml.dump(config, f)

    # 9. 打印汇总
    print(f"\n{'='*80}")
    print("训练完成!")
    print(f"{'='*80}")
    print(f"  Fold 数: {len(fold_results)}")
    print(f"  平均 Kappa: {metrics['cohen_kappa']:.4f}")
    print(f"  整体 Kappa: {metrics['cohen_kappa_overall']:.4f}")
    print(f"  正 Kappa 比例: {metrics['positive_kappa_ratio']:.1%}")
    print(f"\n文件已保存到: {exp_dir}")


if __name__ == '__main__':
    main()
