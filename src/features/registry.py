"""特征集注册表 — 通过名称映射到特征生成函数."""

import logging
from typing import Callable

import pandas as pd

logger = logging.getLogger(__name__)

# 全局注册表: name -> feature_function(df) -> df_with_features
_FEATURE_REGISTRY: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {}


def register_feature_set(name: str):
    """装饰器: 将特征生成函数注册到全局注册表.

    Usage
    -----
    @register_feature_set("technical")
    def build_technical_features(df: pd.DataFrame) -> pd.DataFrame:
        ...
    """
    def decorator(func: Callable[[pd.DataFrame], pd.DataFrame]):
        _FEATURE_REGISTRY[name] = func
        logger.debug(f"特征集已注册: {name}")
        return func
    return decorator


def get_feature_set(name: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """获取已注册的特征生成函数."""
    if name not in _FEATURE_REGISTRY:
        available = list(_FEATURE_REGISTRY.keys())
        raise KeyError(f"特征集 '{name}' 未注册, 可用: {available}")
    return _FEATURE_REGISTRY[name]


def list_feature_sets() -> list[str]:
    """列出所有已注册的特征集名称."""
    return list(_FEATURE_REGISTRY.keys())
