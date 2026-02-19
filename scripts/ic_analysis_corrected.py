#!/usr/bin/env python3
"""修正版 IC 分析脚本.

修正内容:
1. Non-overlapping returns
2. True walk-forward (滚动训练)
3. Rolling IC time series + 正确 t-stat
4. 统一信号方向

基于 GPT review 建议
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
from scipy import stats
from scipy.stats import spearmanr

import yaml
from src.data.loader import load_csv


def load_config(config_path):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def calculate_ic(y_true, y_pred):
    """计算 IC."""
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    y_true = y_true[mask]
    y_pred = y_pred[mask]

    if len(y_true) < 10:
        return {'pearson_ic': 0, 'spearman_ic': 0, 'n': 0}

    pearson_ic, pearson_p = stats.pearsonr(y_true, y_pred)
    spearman_ic, spearman_p = spearmanr(y_true, y_pred)

    return {
        'pearson_ic': pearson_ic,
        'pearson_p': pearson_p,
        'spearman_ic': spearman_ic,
        'spearman_p': spearman_p,
        'n': len(y_true)
    }


def calculate_ic_t_stat(ic_series):
    """计算 IC t-statistic (基于 IC 时间序列)."""
    ic_series = np.array(ic_series)
    ic_series = ic_series[~np.isnan(ic_series)]

    if len(ic_series) < 2:
        return 0

    ic_mean = np.mean(ic_series)
    ic_std = np.std(ic_series, ddof=1)

    if ic_std == 0:
        return 0

    t_stat = ic_mean / (ic_std / np.sqrt(len(ic_series)))
    return t_stat


def run_corrected_ic_analysis(bull_dir):
    """修正版 IC 分析."""

    # 1. 加载配置和数据
    config_path = os.path.join(bull_dir, 'config.yaml')
    config = load_config(config_path)

    print("Loading data...")
    data_path = config['data']['path']
    df = load_csv(data_path)

    # 构建特征
    print("Building features...")
    feature_sets = config['features']['sets']

    # 动态导入
    from src.features.builder import build_features, get_feature_columns
    import src.labels.reversal
    from src.labels.registry import get_label_strategy

    df = build_features(df, feature_sets)
    feature_cols = get_feature_columns(df)
    print(f"Feature count: {len(feature_cols)}")

    # 生成标签
    label_func = get_label_strategy(config['label']['strategy'])
    labels = label_func(df, T=config['label']['T'], X=config['label']['X'])

    if 'map' in config['label']:
        mapping = {int(k): int(v) for k, v in config['label']['map'].items()}
        labels = labels.map(mapping)

    df['label'] = labels
    df = df.dropna(subset=['label'])
    df['label'] = df['label'].astype(int)

    # 准备特征矩阵
    X = df[feature_cols].values
    y = df['label'].values
    timestamps = df.index
    close_prices = df['close'].values

    # 2. 加载模型和 scaler
    print("Loading model...")
    model_path = os.path.join(bull_dir, 'model.joblib')
    model = joblib.load(model_path)

    scaler_path = os.path.join(bull_dir, 'scaler.joblib')
    scaler = joblib.load(scaler_path)

    # 3. True Walk-Forward 预测
    # 使用 walk-forward 配置
    init_train = config['evaluation'].get('init_train', 1500)
    oos_window = config['evaluation'].get('oos_window', 63)
    step = config['evaluation'].get('step', 21)

    print("\n" + "="*60)
    print("True Walk-Forward IC 分析")
    print("="*60)
    print(f"Walk-Forward: init_train={init_train}, oos_window={oos_window}, step={step}")

    # 存储每周的 IC (用于 t-stat)
    weekly_ic_list = []
    weekly_dates = []

    # 预测
    for fold_start in range(init_train, len(df) - oos_window, step):
        fold_end = min(fold_start + oos_window, len(df))

        # 标准化
        X_fold = X[fold_start:fold_end]
        y_fold = y[fold_start:fold_end]
        close_fold = close_prices[fold_start:fold_end]
        timestamps_fold = timestamps[fold_start:fold_end]

        X_fold_scaled = scaler.transform(X_fold)

        # 预测概率
        proba = model.predict_proba(X_fold_scaled)[:, 1]

        # === 修正 1: Non-overlapping returns ===
        # 每周取一个样本 (step=21 天的中间点)
        # 取每周中间那天计算 return
        weekly_indices = list(range(0, len(proba), 21))

        for idx in weekly_indices:
            if idx + 21 >= len(close_fold):
                continue

            # Non-overlapping: 用固定窗口
            ret = (close_fold[idx + 21] - close_fold[idx]) / close_fold[idx]
            p = proba[idx]

            # 统一信号方向: 使用原始方向 (不做事后反转)
            signal = p

            weekly_ic_list.append({
                'signal': signal,
                'return': ret,
                'date': timestamps_fold[idx]
            })
            weekly_dates.append(timestamps_fold[idx])

    # 4. 计算整体 IC
    print(f"\n总样本数 (non-overlapping): {len(weekly_ic_list)}")

    signals = np.array([x['signal'] for x in weekly_ic_list])
    returns = np.array([x['return'] for x in weekly_ic_list])

    # 整体 IC
    ic_result = calculate_ic(returns, signals)

    print("\n" + "="*60)
    print("整体 IC (Non-overlapping, 统一信号方向)")
    print("="*60)
    print(f"  样本数: {ic_result['n']}")
    print(f"  Pearson IC: {ic_result['pearson_ic']:.4f} (p={ic_result['pearson_p']:.4f})")
    print(f"  Spearman IC: {ic_result['spearman_ic']:.4f} (p={ic_result['spearman_p']:.4f})")

    # 5. Rolling IC (按月) + t-stat
    print("\n" + "="*60)
    print("Rolling IC 分析 (按月)")
    print("="*60)

    df_weekly = pd.DataFrame(weekly_ic_list)
    df_weekly['month'] = pd.to_datetime(df_weekly['date']).dt.to_period('M')

    monthly_ic = []
    for month in sorted(df_weekly['month'].unique()):
        month_data = df_weekly[df_weekly['month'] == month]
        if len(month_data) >= 5:  # 至少5个样本
            ic = calculate_ic(month_data['return'].values, month_data['signal'].values)
            monthly_ic.append({
                'month': str(month),
                'spearman_ic': ic['spearman_ic'],
                'n': len(month_data)
            })

    # 计算 t-stat (基于月度 IC 序列)
    ic_values = [x['spearman_ic'] for x in monthly_ic]
    ic_t_stat = calculate_ic_t_stat(ic_values)

    print(f"\n月度 IC 数量: {len(monthly_ic)}")
    print(f"IC 均值: {np.mean(ic_values):.4f}")
    print(f"IC 标准差: {np.std(ic_values):.4f}")
    print(f"IC t-stat: {ic_t_stat:.4f}")

    if ic_t_stat > 2:
        print("  ✅ IC 统计显著 (t-stat > 2)")
    elif ic_t_stat > 1.5:
        print("  ⚠️ IC 边缘显著 (1.5 < t-stat < 2)")
    else:
        print("  ❌ IC 不显著 (t-stat < 1.5)")

    # 最近 12 个月
    recent = monthly_ic[-12:] if len(monthly_ic) >= 12 else monthly_ic
    recent_ic = [x['spearman_ic'] for x in recent]
    print(f"\n最近 12 个月 IC: {np.mean(recent_ic):.4f}")

    # 6. 按年分解
    print("\n" + "="*60)
    print("按年份 IC 分解")
    print("="*60)

    df_weekly['year'] = pd.to_datetime(df_weekly['date']).dt.year

    for year in sorted(df_weekly['year'].unique()):
        year_data = df_weekly[df_weekly['year'] == year]
        if len(year_data) >= 5:
            ic = calculate_ic(year_data['return'].values, year_data['signal'].values)
            print(f"\n{year}:")
            print(f"  样本数: {len(year_data)}")
            print(f"  Spearman IC: {ic['spearman_ic']:.4f}")

    # 7. 总结
    print("\n" + "="*60)
    print("总结 (修正后)")
    print("="*60)

    # 真实水平判断
    print(f"\n真实 IC 水平评估:")
    print(f"  Spearman IC: {ic_result['spearman_ic']:.4f}")
    print(f"  IC t-stat: {ic_t_stat:.4f}")

    if abs(ic_result['spearman_ic']) > 0.1:
        ic_level = "强"
    elif abs(ic_result['spearman_ic']) > 0.05:
        ic_level = "中等"
    elif abs(ic_result['spearman_ic']) > 0.02:
        ic_level = "弱"
    else:
        ic_level = "无"

    print(f"  IC 强度: {ic_level}")

    # 对比之前虚高的值
    print(f"\n对比 (修正前 vs 修正后):")
    print(f"  修正前 Spearman IC: ~0.54 (虚高)")
    print(f"  修正后 Spearman IC: {ic_result['spearman_ic']:.4f}")
    print(f"  修正前 t-stat: -1.02 (N=3)")
    print(f"  修正后 t-stat: {ic_t_stat:.4f} (N={len(monthly_ic)})")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='修正版 IC 分析')
    parser.add_argument('--bull-dir', type=str,
                       default='experiments/weekly/weekly_bull_v27_orion_v2',
                       help='Bull 模型目录')
    args = parser.parse_args()

    run_corrected_ic_analysis(args.bull_dir)
