"""生产 serving 层 — 模型加载、特征契约、信号引擎.

这个包是「生产推理唯一入口」，把原本散落在各脚本里的硬编码模型路径、
variant 解析、特征列校验收敛到一处。

模块:
  - active_config: 读 models/production/active.yaml (生产模型唯一真相源)
"""

from src.serving.active_config import (
    ActiveModel,
    load_active_models,
    resolve_model,
)
from src.serving.feature_contract import (
    build_feature_frame,
    validate_feature_cols,
)

__all__ = [
    "ActiveModel",
    "load_active_models",
    "resolve_model",
    "build_feature_frame",
    "validate_feature_cols",
]
