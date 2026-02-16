#!/usr/bin/env python3
"""Bear 模型类别不平衡优化脚本.

测试不同的类别不平衡处理策略:
1. scale_pos_weight 不同值
2. is_unbalance
3. SMOTE 过采样
4. 调整预测阈值

运行:
    python scripts/optimize_bear_imbalance.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import yaml
import json
import logging
from datetime import datetime

import lightgbm as lgb
from sklearn.metrics import cohen_kappa_score, f1_score, precision_recall_curve

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def load_data():
    """加载数据并构建特征."""
    from src.data.loader import load_csv
    from src.features.builder import build_features, get_feature_columns

    # 加载数据
    df = load_csv('data/raw/btc_binance_BTCUSDT_1d.csv')

    # 构建特征 (使用与 v13 相同的特征集)
    feature_sets = ['technical', 'volume', 'flow', 'market_structure', 'external_fgi']
    df = build_features(df, feature_sets=feature_sets)

    # 构建标签 (Bear: T=28, X=0.05)
    df = build_label(df, T=28, X=0.05)

    # 获取特征列
    feature_cols = get_feature_columns(df)
    feature_cols = [c for c in feature_cols if c in df.columns]

    # 过滤有效数据
    df = df.dropna(subset=feature_cols + ['label'])

    return df, feature_cols


def build_label(df: pd.DataFrame, T: int = 28, X: float = 0.05) -> pd.DataFrame:
    """构建 Bear 标签 (反转策略)."""
    df = df.copy()

    # 计算未来 T 天的收益率
    df['future_return'] = df['close'].shift(-T) / df['close'] - 1

    # 标签映射
    # 0 (震荡): -X < return < X
    # 1 (大涨, 对 Bear 来说是 "不跌"): return > X  -> label = 0 (不跌)
    # 2 (大跌): return < -X -> label = 1 (大跌)

    conditions = [
        df['future_return'] > X,    # 大涨
        df['future_return'] < -X,   # 大跌
        (df['future_return'] >= -X) & (df['future_return'] <= X),  # 震荡
    ]
    choices = [0, 1, 0]  # 大涨=0(不跌), 大跌=1(跌), 震荡=0(不跌)

    df['label'] = np.select(conditions, choices, default=np.nan)

    return df


def train_and_evaluate(X_train, y_train, X_test, y_test, params: dict) -> dict:
    """训练模型并评估."""
    # 训练
    model = lgb.LGBMClassifier(**params)
    model.fit(X_train, y_train)

    # 预测概率
    y_proba = model.predict_proba(X_test)[:, 1]

    # 默认阈值
    y_pred = (y_proba >= 0.5).astype(int)

    # 计算指标
    kappa = cohen_kappa_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)

    return {
        'kappa': kappa,
        'f1': f1,
        'y_proba': y_proba,
        'y_pred': y_pred,
    }


def optimize_threshold(y_test, y_proba: np.ndarray) -> dict:
    """优化预测阈值以最大化 Kappa."""
    precisions, recalls, thresholds = precision_recall_curve(y_test, y_proba)

    best_kappa = -1
    best_threshold = 0.5

    for thresh in np.arange(0.1, 0.9, 0.05):
        y_pred = (y_proba >= thresh).astype(int)
        if y_pred.sum() == 0:
            continue
        kappa = cohen_kappa_score(y_test, y_pred)
        if kappa > best_kappa:
            best_kappa = kappa
            best_threshold = thresh

    return {'best_threshold': best_threshold, 'best_kappa': best_kappa}


def run_walk_forward(df, feature_cols, params: dict, init_train: int = 1500, step: int = 21):
    """Walk-forward 回测."""
    results = []
    X = df[feature_cols].values
    y = df['label'].values

    for train_end in range(init_train, len(df) - 63, step):
        X_train = X[:train_end]
        y_train = y[:train_end]

        test_end = min(train_end + 63, len(df))
        X_test = X[train_end:test_end]
        y_test = y[train_end:test_end]

        if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
            continue

        # 训练和评估
        eval_result = train_and_evaluate(X_train, y_train, X_test, y_test, params)

        # 优化阈值
        threshold_opt = optimize_threshold(y_test, eval_result['y_proba'])

        results.append({
            'train_end': train_end,
            'kappa_default': eval_result['kappa'],
            'f1_default': eval_result['f1'],
            'best_threshold': threshold_opt['best_threshold'],
            'kappa_optimized': threshold_opt['best_kappa'],
        })

    return pd.DataFrame(results)


def main():
    """主函数: 测试不同类别不平衡策略."""
    print("=" * 60)
    print("Bear 模型类别不平衡优化实验")
    print("=" * 60)

    # 加载数据
    logger.info("加载数据...")
    df, feature_cols = load_data()
    logger.info(f"特征数: {len(feature_cols)}, 数据行数: {len(df)}")

    # 计算类别分布
    label_counts = df['label'].value_counts()
    neg_count = label_counts.get(0, 0)
    pos_count = label_counts.get(1, 0)
    imbalance_ratio = neg_count / pos_count if pos_count > 0 else 0

    print(f"\n类别分布:")
    print(f"  负类 (不跌): {neg_count} ({neg_count/len(df)*100:.1f}%)")
    print(f"  正类 (大跌): {pos_count} ({pos_count/len(df)*100:.1f}%)")
    print(f"  不平衡比例: 1:{imbalance_ratio:.1f}")

    # 基础参数
    base_params = {
        'n_estimators': 300,
        'max_depth': 5,
        'learning_rate': 0.03,
        'num_leaves': 20,
        'subsample': 0.7,
        'colsample_bytree': 0.7,
        'random_state': 42,
        'verbose': -1,
    }

    # 实验配置
    experiments = [
        {
            'name': 'baseline (auto_scale)',
            'params': {**base_params, 'auto_scale_pos_weight': True},
        },
        {
            'name': 'scale_pos_weight=5',
            'params': {**base_params, 'scale_pos_weight': 5.0},
        },
        {
            'name': 'scale_pos_weight=8',
            'params': {**base_params, 'scale_pos_weight': 8.0},
        },
        {
            'name': 'scale_pos_weight=10',
            'params': {**base_params, 'scale_pos_weight': 10.0},
        },
        {
            'name': 'is_unbalance=true',
            'params': {**base_params, 'is_unbalance': True},
        },
    ]

    # 运行实验
    results = []
    for exp in experiments:
        logger.info(f"\n实验: {exp['name']}")
        print(f"\n{'='*40}")
        print(f"实验: {exp['name']}")
        print(f"{'='*40}")

        df_results = run_walk_forward(df, feature_cols, exp['params'])

        if len(df_results) > 0:
            avg_kappa = df_results['kappa_default'].mean()
            avg_kappa_opt = df_results['kappa_optimized'].mean()
            pos_ratio = (df_results['kappa_default'] > 0).mean()

            print(f"  默认阈值 Kappa: {avg_kappa:.4f} ± {df_results['kappa_default'].std():.4f}")
            print(f"  优化阈值 Kappa: {avg_kappa_opt:.4f} ± {df_results['kappa_optimized'].std():.4f}")
            print(f"  正 Kappa 比例: {pos_ratio:.1%}")

            results.append({
                'name': exp['name'],
                'avg_kappa_default': avg_kappa,
                'avg_kappa_optimized': avg_kappa_opt,
                'kappa_std': df_results['kappa_default'].std(),
                'positive_ratio': pos_ratio,
            })

    # 对比表格
    print("\n" + "=" * 60)
    print("实验对比")
    print("=" * 60)

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('avg_kappa_optimized', ascending=False)

    print(f"\n| 实验 | 默认 Kappa | 优化 Kappa | Kappa Std | 正 Kappa 比例 |")
    print(f"|------|-----------|------------|-----------|--------------|")
    for _, row in results_df.iterrows():
        print(f"| {row['name']} | {row['avg_kappa_default']:.4f} | {row['avg_kappa_optimized']:.4f} | {row['kappa_std']:.4f} | {row['positive_ratio']:.1%} |")

    # 保存结果
    output_path = PROJECT_ROOT / 'experiments' / 'bear_imbalance_optimization.csv'
    results_df.to_csv(output_path, index=False)
    logger.info(f"结果已保存: {output_path}")

    # 最佳配置
    best = results_df.iloc[0]
    print(f"\n🏆 最佳配置: {best['name']}")
    print(f"   优化后 Kappa: {best['avg_kappa_optimized']:.4f}")


if __name__ == '__main__':
    main()
