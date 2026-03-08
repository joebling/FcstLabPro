import importlib
import logging

logger = logging.getLogger(__name__)

# 必须加载的核心模型
from . import lgbm  # noqa: F401

# 可选模型：依赖重型库（torch 等），缺失时跳过
_optional_models = [
    "orion_bix_classifier",
    "tft_classifier",
    "patchtst_classifier",
    "tabpfn_classifier",
]

for _name in _optional_models:
    try:
        importlib.import_module(f".{_name}", __name__)
    except Exception as e:
        logger.debug(f"跳过可选模型 {_name}: {e}")
