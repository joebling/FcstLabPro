"""模型注册表."""

import logging
from typing import Type

from src.models.base import BaseModel

logger = logging.getLogger(__name__)

_MODEL_REGISTRY: dict[str, Type[BaseModel]] = {}


def register_model(name: str):
    """装饰器: 注册模型类."""
    def decorator(cls: Type[BaseModel]):
        _MODEL_REGISTRY[name] = cls
        logger.debug(f"模型已注册: {name}")
        return cls
    return decorator


def get_model_class(name: str) -> Type[BaseModel]:
    """获取已注册的模型类."""
    if name not in _MODEL_REGISTRY:
        available = list(_MODEL_REGISTRY.keys())
        raise KeyError(f"模型 '{name}' 未注册, 可用: {available}")
    return _MODEL_REGISTRY[name]


def create_model(name: str, params: dict | None = None) -> BaseModel:
    """创建模型实例."""
    cls = get_model_class(name)
    return cls(params=params)


def list_models() -> list[str]:
    """列出所有已注册的模型."""
    return list(_MODEL_REGISTRY.keys())
