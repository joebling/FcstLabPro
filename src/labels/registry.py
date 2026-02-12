"""标签策略注册表."""

import logging
from typing import Callable

import pandas as pd

logger = logging.getLogger(__name__)

_LABEL_REGISTRY: dict[str, Callable] = {}


def register_label_strategy(name: str):
    """装饰器: 注册标签生成策略."""
    def decorator(func):
        _LABEL_REGISTRY[name] = func
        logger.debug(f"标签策略已注册: {name}")
        return func
    return decorator


def get_label_strategy(name: str) -> Callable:
    """获取已注册的标签生成函数."""
    if name not in _LABEL_REGISTRY:
        available = list(_LABEL_REGISTRY.keys())
        raise KeyError(f"标签策略 '{name}' 未注册, 可用: {available}")
    return _LABEL_REGISTRY[name]


def list_label_strategies() -> list[str]:
    """列出所有已注册的标签策略."""
    return list(_LABEL_REGISTRY.keys())
