#!/usr/bin/env python3
"""数据对齐检查.

检查是否存在未来函数/数据泄露:
1. 特征是否使用未来数据?
2. 标签是否正确对齐?
3. 预测时点是否正确?
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import yaml

from src.data.loader import load_csv
from src.features.builder import build_features
import src.labels.reversal
from src.labels.registry import get_label_strategy


def check_data_alignment():
    """检查数据对齐."""

    # 加载配置
    config = yaml.safe_load(open('experiments/weekly/weekly_bull_v27_orion_v2/config.yaml'))

    print("="*60)
    print("数据对齐检查")
    print("="*60)

    # 加载数据
    df = load_csv(config['data']['path'])
    print(f"\n原始数据: {len(df)} 行")
    print(f"时间范围: {df.index[0]} ~ {df.index[-1]}")

    # 构建特征
    df = build_features(df, config['features']['sets'])

    # 检查特征
    print(f"\n特征数量: {len(df.columns)}")

    # 检查 MA 特征 (最容易出现未来数据)
    ma_cols = [c for c in df.columns if 'MA' in c or 'ma' in c]
    print(f"MA 相关特征: {len(ma_cols)}")

    # 检查是否有 "未来" 特征
    future_indicators = ['future', 'lead', 'shift']
    has_future = any(any(f in c.lower() for f in future_indicators) for c in df.columns)
    print(f"\n是否有未来特征: {has_future}")

    # 标签检查
    label_func = get_label_strategy(config['label']['strategy'])
    labels = label_func(df, T=config['label']['T'], X=config['label']['X'])

    print(f"\n标签检查:")
    print(f"  标签类型: {config['label']['strategy']}")
    print(f"  预测窗口 T: {config['label']['T']} 天")
    print(f"  标签值分布: {labels.value_counts().to_dict()}")

    # 检查是否有 NaN 在标签中 (可能因为数据不足)
    nan_ratio = labels.isna().sum() / len(labels)
    print(f"  标签 NaN 比例: {nan_ratio:.2%}")

    print("\n" + "="*60)
    print("关键验证")
    print("="*60)

    # 验证: 特征使用历史数据
    print("\n1. 特征是否使用未来数据?")
    print("   检查方法: 特征只能使用 t 时刻及之前的数据")
    print("   结果: 需要人工检查特征构建代码")
    print("   建议: 检查 src/features/ 中是否有 look-ahead")

    # 验证: 标签对齐
    print("\n2. 标签是否正确对齐?")
    print(f"   T={config['label']['T']} 天的反转标签")
    print(f"   预期: 标签对应未来 T 天的价格变动")

    # 验证: 预测时间点
    print("\n3. 预测时间点是否正确?")
    print("   预期: t 时刻使用 t 之前的数据预测 t+T 天的收益")
    print("   当前实现: 需要检查 run_walk_forward 中的数据切片")

    print("\n" + "="*60)
    print("结论")
    print("="*60)

    print("\n⚠️ 建议检查:")
    print("  1. src/features/builder.py 中特征是否有 look-ahead")
    print("  2. 训练时 train/test split 是否正确")
    print("  3. 预测时是否只使用历史数据")

    print("\n✅ 已验证:")
    print(f"  - 数据时间范围: {df.index[0]} ~ {df.index[-1]}")
    print(f"  - 标签类型: {config['label']['strategy']}")


if __name__ == '__main__':
    check_data_alignment()
