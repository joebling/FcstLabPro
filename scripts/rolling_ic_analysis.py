#!/usr/bin/env python3
"""Rolling IC 曲线分析 (Layer 2).

验证 IC 稳定性，检测 regime shift:
1. Rolling IC 时间序列
2. IC 分布统计
3. Regime 标记

符合 Institutional 标准:
- 使用 non-overlapping returns
- 基于月度 IC 计算 t-stat
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import yaml

from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns
import src.labels.reversal
from src.labels.registry import get_label_strategy
from scipy.stats import spearmanr


def calculate_ic_t_stat(ic_series):
    """基于 IC 时间序列计算 t-stat."""
    ic_series = np.array(ic_series)
    ic_series = ic_series[~np.isnan(ic_series)]
    if len(ic_series) < 2:
        return 0, 0
    ic_mean = np.mean(ic_series)
    ic_std = np.std(ic_series, ddof=1)
    if ic_std == 0:
        return ic_mean, 0
    t_stat = ic_mean / (ic_std / np.sqrt(len(ic_series)))
    return ic_mean, t_stat


def rolling_ic_analysis(df, proba, close_prices, timestamps, step=21, window=52):
    """
    Rolling IC 分析.

    Args:
        df: 特征数据
        proba: 预测概率
        close_prices: 收盘价
        timestamps: 时间戳
        step: non-overlapping 采样步长
        window: Rolling 窗口大小 (周)
    """
    # Non-overlapping returns
    signals = []
    returns = []
    dates = []

    for i in range(0, len(proba) - step, step):
        signals.append(proba[i])
        ret = (close_prices[i + step] - close_prices[i]) / close_prices[i]
        returns.append(ret)
        dates.append(timestamps[i])

    signals = np.array(signals)
    returns = np.array(returns)
    dates = pd.DatetimeIndex(dates)

    print("=" * 60)
    print("Rolling IC 分析 (Layer 2)")
    print("=" * 60)
    print(f"\n数据概况:")
    print(f"  Non-overlapping 样本数: {len(signals)}")
    print(f"  时间范围: {dates[0]} ~ {dates[-1]}")

    # 整体 IC
    spearman_ic, p_val = spearmanr(returns, signals)
    print(f"\n整体 Spearman IC: {spearman_ic:.4f} (p={p_val:.4f})")

    # 按月计算 IC
    df_monthly = pd.DataFrame({
        'signal': signals,
        'return': returns,
        'date': dates
    })
    df_monthly['month'] = df_monthly['date'].dt.to_period('M')

    monthly_ic = []
    for month in df_monthly['month'].unique():
        m = df_monthly[df_monthly['month'] == month]
        if len(m) >= 2:
            ic, _ = spearmanr(m['return'], m['signal'])
            monthly_ic.append({
                'month': str(month),
                'ic': ic,
                'n_samples': len(m)
            })

    df_ic = pd.DataFrame(monthly_ic)
    print(f"\n月度 IC 统计:")
    print(f"  月份数: {len(df_ic)}")
    print(f"  IC 均值: {df_ic['ic'].mean():.4f}")
    print(f"  IC 标准差: {df_ic['ic'].std():.4f}")
    print(f"  IC 最小: {df_ic['ic'].min():.4f}")
    print(f"  IC 最大: {df_ic['ic'].max():.4f}")

    # Rolling IC (滚动 52 周 = 约 12 个月)
    # 由于数据只有约 2 年，我们用较小的窗口
    roll_window = min(12, len(df_ic) - 1)  # 至少 2 个月
    df_ic['rolling_ic'] = df_ic['ic'].rolling(window=roll_window, min_periods=2).mean()

    # IC t-stat
    ic_mean, t_stat = calculate_ic_t_stat(df_ic['ic'].dropna().values)
    print(f"\nIC t-stat:")
    print(f"  IC 均值: {ic_mean:.4f}")
    print(f"  t-stat: {t_stat:.4f}")

    # Regime 检测 (基于时间)
    mid_point = len(df_ic) // 2
    first_half_ic = df_ic['ic'].iloc[:mid_point].mean()
    second_half_ic = df_ic['ic'].iloc[mid_point:].mean()

    print(f"\nRegime 分解:")
    print(f"  前半段 IC: {first_half_ic:.4f}")
    print(f"  后半段 IC: {second_half_ic:.4f}")
    print(f"  差异: {second_half_ic - first_half_ic:.4f}")

    # 打印每月 IC
    print(f"\n月度 IC 详情:")
    print("-" * 40)
    for _, row in df_ic.iterrows():
        sign = "+" if row['ic'] > 0 else ""
        print(f"  {row['month']}: {sign}{row['ic']:.4f} (n={row['n_samples']})")

    # IC 稳定性判断
    print(f"\n稳定性判断:")
    if abs(t_stat) > 2:
        print("  ✅ IC 统计显著 (t-stat > 2)")
    else:
        print("  ⚠️ IC 不显著 (t-stat < 2)")

    if df_ic['ic'].std() < 0.2:
        print("  ✅ IC 稳定 (std < 0.2)")
    else:
        print("  ⚠️ IC 波动较大 (std > 0.2)")

    if first_half_ic * second_half_ic > 0:
        print("  ✅ 两半段符号一致")
    else:
        print("  ⚠️ 两半段符号相反 - 可能存在 regime shift")

    # 保存结果
    output_dir = Path('experiments/weekly/rolling_ic_analysis')
    output_dir.mkdir(parents=True, exist_ok=True)

    df_ic.to_csv(output_dir / 'monthly_ic.csv', index=False)
    print(f"\n结果已保存到: {output_dir}")

    # 绘制图表
    fig, axes = plt.subplots(2, 1, figsize=(12, 8))

    # 图1: Rolling IC 曲线
    ax1 = axes[0]
    ax1.bar(range(len(df_ic)), df_ic['ic'], color='steelblue', alpha=0.7)
    ax1.axhline(y=0, color='red', linestyle='--', linewidth=1)
    ax1.axhline(y=df_ic['ic'].mean(), color='green', linestyle='--', linewidth=1, label=f"Mean: {df_ic['ic'].mean():.3f}")
    ax1.set_xlabel('Month')
    ax1.set_ylabel('Spearman IC')
    ax1.set_title('Monthly IC (Non-overlapping Returns)')
    ax1.legend()
    ax1.set_xticks(range(0, len(df_ic), max(1, len(df_ic) // 6)))
    ax1.set_xticklabels([df_ic['month'].iloc[i] for i in range(0, len(df_ic), max(1, len(df_ic) // 6))], rotation=45)

    # 图2: IC 分布
    ax2 = axes[1]
    ax2.hist(df_ic['ic'], bins=10, color='steelblue', alpha=0.7, edgecolor='black')
    ax2.axvline(x=0, color='red', linestyle='--', linewidth=1, label='Zero')
    ax2.axvline(x=df_ic['ic'].mean(), color='green', linestyle='--', linewidth=1, label=f"Mean: {df_ic['ic'].mean():.3f}")
    ax2.set_xlabel('Spearman IC')
    ax2.set_ylabel('Frequency')
    ax2.set_title('IC Distribution')
    ax2.legend()

    plt.tight_layout()
    plt.savefig(output_dir / 'rolling_ic.png', dpi=150)
    print(f"图表已保存到: {output_dir / 'rolling_ic.png'}")

    return df_ic


def main():
    """主函数."""
    # 加载配置
    config_path = 'experiments/weekly/weekly_bull_v27_orion_v2/config.yaml'
    config = yaml.safe_load(open(config_path))

    print("=" * 60)
    print("Rolling IC 曲线分析")
    print("=" * 60)

    # 加载数据
    df = load_csv(config['data']['path'])
    print(f"原始数据: {len(df)} 行")

    # 构建特征
    df = build_features(df, config['features']['sets'])
    feature_cols = get_feature_columns(df)

    # 标签
    label_func = get_label_strategy(config['label']['strategy'])
    labels = label_func(df, T=config['label']['T'], X=config['label']['X'])
    if 'map' in config['label']:
        labels = labels.map({int(k): int(v) for k, v in config['label']['map'].items()})
    df['label'] = labels
    df = df.dropna(subset=['label'])

    # 加载模型
    import joblib
    model_path = 'experiments/weekly/weekly_bull_v27_orion_v2/model.joblib'
    scaler_path = 'experiments/weekly/weekly_bull_v27_orion_v2/scaler.joblib'

    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path)

    # 预测
    init_train = config['evaluation'].get('init_train', 1500)
    X_test = df[feature_cols].values[init_train:]
    timestamps = df.index[init_train:].values
    close_prices = df['close'].values[init_train:]

    X_test_scaled = scaler.transform(X_test)
    proba = model.predict_proba(X_test_scaled)[:, 1]

    print(f"测试集: {len(proba)} 样本")

    # Rolling IC 分析
    df_ic = rolling_ic_analysis(df.iloc[init_train:], proba, close_prices, timestamps)

    # 生成实验报告
    report = f"""# Rolling IC 分析报告 (Layer 2)

## 数据概况
- Non-overlapping 样本数: {len(proba)}
- 时间范围: {pd.Timestamp(timestamps[0])} ~ {pd.Timestamp(timestamps[-1])}

## 整体 IC
- Spearman IC: {spearmanr(df['close'].iloc[init_train:].values[::21][:len(proba)//21*21], proba[::21][:len(proba)//21*21])[0]:.4f}

## 月度 IC 统计
- 月份数: {len(df_ic)}
- IC 均值: {df_ic['ic'].mean():.4f}
- IC 标准差: {df_ic['ic'].std():.4f}
- IC 最小: {df_ic['ic'].min():.4f}
- IC 最大: {df_ic['ic'].max():.4f}

## 稳定性判断
- IC t-stat: {calculate_ic_t_stat(df_ic['ic'].dropna().values)[1]:.4f}

## 结论
"""

    ic_mean, t_stat = calculate_ic_t_stat(df_ic['ic'].dropna().values)
    if abs(t_stat) > 2:
        report += "- ✅ IC 统计显著\n"
    else:
        report += "- ⚠️ IC 不显著\n"

    if df_ic['ic'].std() < 0.2:
        report += "- ✅ IC 稳定\n"
    else:
        report += "- ⚠️ IC 波动较大\n"

    # 保存报告
    output_dir = Path('experiments/weekly/rolling_ic_analysis')
    with open(output_dir / 'report.md', 'w') as f:
        f.write(report)

    print(f"\n报告已保存到: {output_dir / 'report.md'}")


if __name__ == '__main__':
    main()
