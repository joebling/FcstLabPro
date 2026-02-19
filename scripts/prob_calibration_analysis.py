#!/usr/bin/env python3
"""概率校准分析脚本.

分析:
- 概率分布直方图
- Reliability Diagram
- Brier Score
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import joblib
import yaml
import argparse

from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns
import src.labels.reversal
from src.labels.registry import get_label_strategy


def load_config(config_path):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def brier_score(y_true, y_proba):
    """计算 Brier Score."""
    return np.mean((y_proba - y_true) ** 2)


def run_calibration_analysis(bull_dir):
    """运行概率校准分析."""

    # 1. 加载配置和数据
    config_path = os.path.join(bull_dir, 'config.yaml')
    config = load_config(config_path)

    print("Loading data...")
    data_path = config['data']['path']
    df = load_csv(data_path)

    # 构建特征
    print("Building features...")
    feature_sets = config['features']['sets']
    df = build_features(df, feature_sets)

    # 获取特征列
    feature_cols = get_feature_columns(df)

    # 生成标签
    label_func = get_label_strategy(config['label']['strategy'])
    labels = label_func(df, T=config['label']['T'], X=config['label']['X'])

    if 'map' in config['label']:
        mapping = {int(k): int(v) for k, v in config['label']['map'].items()}
        labels = labels.map(mapping)

    df['label'] = labels
    df = df.dropna(subset=['label'])
    df['label'] = df['label'].astype(int)

    # 2. 加载模型
    print("Loading model...")
    model_path = os.path.join(bull_dir, 'model.joblib')
    model = joblib.load(model_path)

    scaler_path = os.path.join(bull_dir, 'scaler.joblib')
    scaler = joblib.load(scaler_path)

    # 3. 预测
    init_train = config['evaluation'].get('init_train', 1500)
    X_test = df[feature_cols].values[init_train:]
    y_test = df['label'].values[init_train:]
    timestamps_test = df.index[init_train:]

    print(f"Predicting {len(X_test)} samples...")
    X_test_scaled = scaler.transform(X_test)
    proba = model.predict_proba(X_test_scaled)[:, 1]

    # 4. 分析
    print("\n" + "="*60)
    print("概率分布分析")
    print("="*60)

    # 概率分布统计
    print(f"\n概率统计:")
    print(f"  最小值: {proba.min():.4f}")
    print(f"  最大值: {proba.max():.4f}")
    print(f"  均值: {proba.mean():.4f}")
    print(f"  中位数: {np.median(proba):.4f}")
    print(f"  标准差: {proba.std():.4f}")

    # 分组统计
    bins = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    prob_bins = pd.cut(proba, bins=bins)

    print(f"\n概率分布:")
    for i in range(len(bins) - 1):
        count = (prob_bins == i).sum()
        pct = count / len(proba) * 100
        bar = "█" * int(pct / 2)
        print(f"  [{bins[i]:.1f}-{bins[i+1]:.1f}): {count:4d} ({pct:5.1f}%) {bar}")

    # 低概率集中度
    low_prob = (proba < 0.1).sum()
    low_prob_pct = low_prob / len(proba) * 100
    print(f"\n⚠️ 低概率集中度 (< 0.1): {low_prob}/{len(proba)} ({low_prob_pct:.1f}%)")

    if low_prob_pct > 80:
        print("   确认: 概率塌缩严重!")

    # 5. Reliability Diagram
    print("\n" + "="*60)
    print("Reliability Diagram (预测分组 vs 实际命中率)")
    print("="*60)

    # 将预测概率分成10组
    n_bins = 10
    bin_edges = np.linspace(0, 1, n_bins + 1)
    bin_results = []

    for i in range(n_bins):
        mask = (proba >= bin_edges[i]) & (proba < bin_edges[i + 1])
        if mask.sum() > 0:
            # 实际命中率 (标签为1的比例)
            actual = y_test[mask].mean()
            predicted = proba[mask].mean()
            bin_results.append({
                'bin': i,
                'predicted': predicted,
                'actual': actual,
                'count': mask.sum()
            })
            print(f"  预测 {bin_edges[i]:.1f}-{bin_edges[i+1]:.1f}: 实际命中率 {actual:.2%} ({mask.sum()} 样本)")

    # 6. Brier Score
    print("\n" + "="*60)
    print("Brier Score")
    print("="*60)

    # 转换标签为 0/1
    y_binary = (y_test == 1).astype(int)
    bs = brier_score(y_binary, proba)
    print(f"\n  Brier Score: {bs:.4f}")

    if bs < 0.20:
        print("  ✅ Brier Score 良好 (< 0.20)")
    elif bs < 0.25:
        print("  ⚠️ Brier Score 一般 (0.20-0.25)")
    else:
        print("  ❌ Brier Score 较差 (> 0.25)")

    # 7. 总结
    print("\n" + "="*60)
    print("总结")
    print("="*60)

    print(f"\n✅ 成功标准检查:")
    print(f"  低概率集中度 < 80%: {low_prob_pct:.1f}% {'✅' if low_prob_pct < 80 else '❌'}")
    print(f"  Brier Score < 0.20: {bs:.4f} {'✅' if bs < 0.20 else '❌'}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='概率校准分析')
    parser.add_argument('--bull-dir', type=str,
                       default='experiments/weekly/weekly_bull_v27_orion_v2',
                       help='Bull 模型目录')
    args = parser.parse_args()

    run_calibration_analysis(args.bull_dir)
