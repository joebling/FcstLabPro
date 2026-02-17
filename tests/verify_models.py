#!/usr/bin/env python3
"""
验证本地模型是否正常工作
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import joblib
import logging
import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def verify_bull_model():
    """验证 Bull 模型"""
    logger.info("=" * 60)
    logger.info("📊 验证 Bull 模型 (Orion-BiX v27)")
    logger.info("=" * 60)

    model_dir = PROJECT_ROOT / "experiments/weekly/weekly_bull_v27_orion_final"
    
    if not model_dir.exists():
        logger.error(f"❌ Bull 模型目录不存在: {model_dir}")
        return False

    # 检查文件
    files = list(model_dir.glob("*"))
    logger.info(f"📂 目录内容: {[f.name for f in files]}")
    
    required_files = ["config.yaml"]
    for f in required_files:
        if not (model_dir / f).exists():
            logger.error(f"❌ 缺少必要文件: {f}")
            return False

    logger.info("✅ 配置文件存在")

    # 尝试加载模型
    try:
        if (model_dir / "model.joblib").exists():
            logger.info("📦 尝试加载模型...")
            model = joblib.load(model_dir / "model.joblib")
            logger.info(f"✅ 模型加载成功: {type(model)}")
        else:
            logger.info("⚠️  没有 model.joblib，跳过预测测试")
        
        if (model_dir / "feature_cols.joblib").exists():
            feature_cols = joblib.load(model_dir / "feature_cols.joblib")
            logger.info(f"✅ 特征列加载成功: {len(feature_cols)} 个特征")
        
        if (model_dir / "scaler.joblib").exists():
            scaler = joblib.load(model_dir / "scaler.joblib")
            logger.info(f"✅ Scaler 加载成功: {type(scaler)}")
        
        logger.info("✅ Bull 模型验证通过")
        return True
        
    except Exception as e:
        logger.error(f"❌ Bull 模型验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_bear_model():
    """验证 Bear 模型"""
    logger.info("")
    logger.info("=" * 60)
    logger.info("📊 验证 Bear 模型 (LightGBM v13)")
    logger.info("=" * 60)

    model_dir = PROJECT_ROOT / "experiments/weekly/weekly_bear_v13_T28_fgi_20260215_134804_ff4ad7"
    
    if not model_dir.exists():
        logger.error(f"❌ Bear 模型目录不存在: {model_dir}")
        return False

    # 检查文件
    files = list(model_dir.glob("*"))
    logger.info(f"📂 目录内容: {[f.name for f in files]}")
    
    required_files = ["config.yaml"]
    for f in required_files:
        if not (model_dir / f).exists():
            logger.error(f"❌ 缺少必要文件: {f}")
            return False

    logger.info("✅ 配置文件存在")

    # 尝试加载模型
    try:
        if (model_dir / "model.joblib").exists():
            logger.info("📦 尝试加载模型...")
            model = joblib.load(model_dir / "model.joblib")
            logger.info(f"✅ 模型加载成功: {type(model)}")
        else:
            logger.info("⚠️  没有 model.joblib，跳过预测测试")
        
        if (model_dir / "feature_cols.joblib").exists():
            feature_cols = joblib.load(model_dir / "feature_cols.joblib")
            logger.info(f"✅ 特征列加载成功: {len(feature_cols)} 个特征")
        
        if (model_dir / "scaler.joblib").exists():
            scaler = joblib.load(model_dir / "scaler.joblib")
            logger.info(f"✅ Scaler 加载成功: {type(scaler)}")
        
        logger.info("✅ Bear 模型验证通过")
        return True
        
    except Exception as e:
        logger.error(f"❌ Bear 模型验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    logger.info("")
    logger.info("=" * 60)
    logger.info("🚀 FcstLabPro 模型验证")
    logger.info("=" * 60)
    
    bull_ok = verify_bull_model()
    bear_ok = verify_bear_model()
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("📋 验证结果汇总")
    logger.info("=" * 60)
    logger.info(f"  Bull 模型: {'✅ 通过' if bull_ok else '❌ 失败'}")
    logger.info(f"  Bear 模型: {'✅ 通过' if bear_ok else '❌ 失败'}")
    logger.info("=" * 60)
    
    if bull_ok and bear_ok:
        logger.info("🎉 所有模型验证通过！")
        return 0
    else:
        logger.error("❌ 部分模型验证失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
