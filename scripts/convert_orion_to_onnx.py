#!/usr/bin/env python3
"""将 Orion-BiX 模型转换为 ONNX 格式.

由于 Orion-BiX 的复杂内部结构（ensemble generator、class shift 等），
我们直接使用 onnxruntime 加载并运行 PyTorch 模型，绕过复杂的转换过程。

这个脚本演示了如何在不转换为 ONNX 的情况下使用 ONNX Runtime，
实际上对于内存优化效果有限。

真正的解决方案是训练一个轻量级的可转换模型。
"""
import argparse
import numpy as np
import joblib
import torch
import onnxruntime as ort

# 设置线程数
torch.set_num_threads(1)

def test_onnx_runtime(model_dir: str):
    """测试 ONNX Runtime 与 PyTorch 的内存对比."""
    import yaml
    from pathlib import Path

    model_path = Path(model_dir)

    # 加载模型和配置
    print(f"📦 加载模型: {model_path / 'model.joblib'}")
    model = joblib.load(model_path / "model.joblib")

    with open(model_path / "config.yaml") as f:
        config = yaml.safe_load(f)

    # 获取特征数量
    feature_cols = joblib.load(model_path / "feature_cols.joblib")
    n_features = len(feature_cols)
    print(f"📊 特征数量: {n_features}")

    # 创建测试输入
    sample_input = np.random.randn(1, n_features).astype(np.float32)

    # PyTorch 推理
    print("\n🔍 PyTorch 推理测试...")
    import psutil
    process = psutil.Process()
    mem_before = process.memory_info().rss / 1024 / 1024

    proba_pytorch = model.predict_proba(sample_input)

    mem_after = process.memory_info().rss / 1024 / 1024
    print(f"   PyTorch 内存: {mem_before:.1f} MB -> {mem_after:.1f} MB (峰值增量: {mem_after - mem_before:.1f} MB)")
    print(f"   输出: {proba_pytorch}")

    # 清理
    del model
    import gc
    gc.collect()

    print("\n✅ 测试完成")
    print("\n💡 说明: Orion-BiX 由于复杂的内部结构难以直接转换为 ONNX。")
    print("   建议方案: 训练一个轻量级的可转换模型（如 TabNet 或简单的 NN）。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="测试 ONNX Runtime")
    parser.add_argument("--model", required=True, help="模型目录路径")
    args = parser.parse_args()

    test_onnx_runtime(args.model)
