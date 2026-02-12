"""模型基类."""

from abc import ABC, abstractmethod
from typing import Any

import numpy as np
import pandas as pd


class BaseModel(ABC):
    """所有模型的抽象基类."""

    def __init__(self, params: dict[str, Any] | None = None):
        self.params = params or {}
        self.model = None
        self.is_fitted = False

    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray) -> "BaseModel":
        """训练模型."""
        ...

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测."""
        ...

    @abstractmethod
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """预测概率."""
        ...

    @abstractmethod
    def feature_importance(self) -> np.ndarray:
        """获取特征重要性."""
        ...

    def get_params(self) -> dict:
        """获取模型参数."""
        return self.params.copy()
