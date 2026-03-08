"""简单的 LSTM 时间序列分类器 - 用于深度学习实验."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.base import BaseEstimator, ClassifierMixin

from src.models.registry import register_model
from src.models.base import BaseModel

logger = logging.getLogger(__name__)


class SimpleLSTMClassifier(nn.Module):
    """简单的 LSTM 分类器."""

    def __init__(self, input_dim, hidden_dim=64, num_layers=2, dropout=0.3):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout,
        )
        self.fc = nn.Linear(hidden_dim, 1)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        # x: (batch, seq_len, input_dim)
        lstm_out, (h_n, c_n) = self.lstm(x)
        # 取最后一个时间步的输出
        out = lstm_out[:, -1, :]
        out = self.dropout(out)
        out = self.fc(out)
        return torch.sigmoid(out)


@register_model("lstm_classifier")
class LSTMClassifier(BaseModel):
    """LSTM 时间序列分类器封装."""

    def __init__(self, params: dict[str, Any] | None = None):
        # 从 params 中提取参数
        p = params or {}
        self.hidden_dim = p.get("hidden_dim", 64)
        self.num_layers = p.get("num_layers", 2)
        self.epochs = p.get("epochs", 50)
        self.batch_size = p.get("batch_size", 32)
        self.learning_rate = p.get("learning_rate", 0.001)
        self.sequence_length = p.get("sequence_length", 21)
        self.dropout = p.get("dropout", 0.3)
        self.random_state = p.get("random_state", 42)

        self.model = None
        self.classes_ = None
        self._fitted = False
        self.is_fitted = False

    def _create_sequences(self, X):
        """将数据转换为序列格式."""
        sequences = []
        for i in range(len(X) - self.sequence_length + 1):
            sequences.append(X[i : i + self.sequence_length])
        return np.array(sequences)

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sample_weight: np.ndarray | None = None,
    ) -> "LSTMClassifier":
        """训练 LSTM 模型.

        Note: sample_weight is not supported for LSTM, included for API compatibility.
        """
        # 设置随机种子
        torch.manual_seed(self.random_state)
        np.random.seed(self.random_state)

        self.classes_ = np.unique(y)

        # 创建序列数据
        X_seq = self._create_sequences(X)
        y_seq = y[self.sequence_length - 1 :]  # 对齐标签

        # 转为 tensor
        X_tensor = torch.FloatTensor(X_seq)
        y_tensor = torch.FloatTensor(y_seq).unsqueeze(1)

        # 创建 DataLoader
        dataset = TensorDataset(X_tensor, y_tensor)
        dataloader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)

        # 初始化模型
        input_dim = X.shape[1]
        self.model = SimpleLSTMClassifier(
            input_dim=input_dim,
            hidden_dim=self.hidden_dim,
            num_layers=self.num_layers,
            dropout=self.dropout,
        )

        # 训练
        optimizer = torch.optim.Adam(self.model.parameters(), lr=self.learning_rate)
        criterion = nn.BCELoss()

        self.model.train()
        for epoch in range(self.epochs):
            total_loss = 0
            for batch_X, batch_y in dataloader:
                optimizer.zero_grad()
                outputs = self.model(batch_X)
                loss = criterion(outputs, batch_y)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()

            if (epoch + 1) % 10 == 0:
                logger.info(f"  Epoch {epoch+1}/{self.epochs}, Loss: {total_loss/len(dataloader):.4f}")

        self._fitted = True
        self.is_fitted = True
        logger.info(f"LSTM 训练完成, n_samples={len(X_seq)}")
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测类别."""
        if not self.is_fitted:
            raise RuntimeError("模型尚未训练")

        self.model.eval()
        X_seq = self._create_sequences(X)

        if len(X_seq) == 0:
            return np.array([])

        X_tensor = torch.FloatTensor(X_seq)
        with torch.no_grad():
            outputs = self.model(X_tensor)
            predictions = (outputs > 0.5).float().squeeze().numpy()

        return predictions.astype(int)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """预测概率."""
        if not self._fitted:
            raise RuntimeError("模型尚未训练")

        self.model.eval()
        X_seq = self._create_sequences(X)

        if len(X_seq) == 0:
            return np.array([[0.5, 0.5]])

        X_tensor = torch.FloatTensor(X_seq)
        with torch.no_grad():
            outputs = self.model(X_tensor).squeeze().numpy()

        proba = np.column_stack([1 - outputs, outputs])
        return proba

    def feature_importance(self) -> np.ndarray:
        """LSTM 不直接支持特征重要性，返回 None."""
        return None
