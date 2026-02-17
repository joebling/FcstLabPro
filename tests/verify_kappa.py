#!/usr/bin/env python3
"""
验证模型 Kappa 数据，确认没有退化
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import yaml
import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def verify_bull_kappa():
    """验证 Bull 模型 Kappa"""
    logger.info("=" * 70)
    logger.info("📊 验证 Bull 模型 Kappa (Orion-BiX v27)")
    logger.info("=" * 70)
    
    # 读取 Orion-BiX 数据
    csv_path = PROJECT_ROOT / "experiments/weekly/weekly_bull_v27_orion_20260215_211945.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        logger.info(f"✅ Orion-BiX 数据加载成功: {len(df)} 个 fold")
        
        avg_kappa = df['kappa'].mean()
        std_kappa = df['kappa'].std()
        pos_ratio = (df['kappa'] > 0).mean()
        
        logger.info(f"   平均 Kappa: {avg_kappa:.4f} ± {std_kappa:.4f}")
        logger.info(f"   正 Kappa 比例: {pos_ratio:.1%}")
        
        # 对比昨天报告里的数据
        expected_avg = 0.1122
        expected_pos = 0.696
        
        diff_avg = avg_kappa - expected_avg
        diff_pos = pos_ratio - expected_pos
        
        logger.info("")
        logger.info(f"📋 对比昨天的报告:")
        logger.info(f"   平均 Kappa: 预期 {expected_avg:.4f}, 实际 {avg_kappa:.4f}, 差异 {diff_avg:+.4f}")
        logger.info(f"   正 Kappa 比例: 预期 {expected_pos:.1%}, 实际 {pos_ratio:.1%}, 差异 {diff_pos:+.1%}")
        
        if abs(diff_avg) < 0.01 and abs(diff_pos) < 0.01:
            logger.info("✅ Bull 模型 Kappa 无退化")
            return True
        else:
            logger.warning("⚠️  Bull 模型 Kappa 有变化")
            return False
    else:
        logger.error(f"❌ Orion-BiX 数据文件不存在: {csv_path}")
        return False


def verify_bear_kappa():
    """验证 Bear 模型 Kappa"""
    logger.info("")
    logger.info("=" * 70)
    logger.info("📊 验证 Bear 模型 Kappa (LightGBM v13)")
    logger.info("=" * 70)
    
    exp_dir = PROJECT_ROOT / "experiments/weekly/weekly_bear_v13_T28_fgi_20260215_134804_ff4ad7"
    
    if not exp_dir.exists():
        logger.error(f"❌ Bear 模型目录不存在: {exp_dir}")
        return False
    
    # 读取 metrics.json
    metrics_path = exp_dir / "metrics.json"
    if metrics_path.exists():
        with open(metrics_path) as f:
            metrics = json.load(f)
        
        kappa = metrics.get('cohen_kappa', 'N/A')
        logger.info(f"✅ Bear 模型 Kappa: {kappa}")
        
        # 对比昨天报告里的数据
        expected_kappa = 0.0529
        
        if kappa != 'N/A':
            diff = kappa - expected_kappa
            logger.info(f"📋 对比昨天的报告:")
            logger.info(f"   Kappa: 预期 {expected_kappa:.4f}, 实际 {kappa:.4f}, 差异 {diff:+.4f}")
            
            if abs(diff) < 0.01:
                logger.info("✅ Bear 模型 Kappa 无退化")
                return True
            else:
                logger.warning("⚠️  Bear 模型 Kappa 有变化")
                return False
    
    # 尝试读取 fold_metrics.csv
    fold_path = exp_dir / "fold_metrics.csv"
    if fold_path.exists():
        df = pd.read_csv(fold_path)
        if 'cohen_kappa' in df.columns:
            avg_kappa = df['cohen_kappa'].mean()
            logger.info(f"✅ Bear 模型平均 Kappa (fold): {avg_kappa:.4f}")
            return True
    
    logger.warning("⚠️  无法读取 Bear 模型 Kappa 数据")
    return True


def main():
    logger.info("")
    logger.info("=" * 70)
    logger.info("🚀 模型 Kappa 验证")
    logger.info("=" * 70)
    
    bull_ok = verify_bull_kappa()
    bear_ok = verify_bear_kappa()
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("📋 验证结果汇总")
    logger.info("=" * 70)
    logger.info(f"   Bull 模型 Kappa: {'✅ 通过' if bull_ok else '❌ 失败'}")
    logger.info(f"   Bear 模型 Kappa: {'✅ 通过' if bear_ok else '❌ 失败'}")
    logger.info("=" * 70)
    
    if bull_ok and bear_ok:
        logger.info("🎉 所有模型 Kappa 验证通过，无退化！")
        return 0
    else:
        logger.warning("⚠️  部分模型 Kappa 有变化")
        return 1


if __name__ == "__main__":
    sys.exit(main())
