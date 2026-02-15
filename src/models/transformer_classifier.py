"""简单的 Transformer 时间序列分类器 - 用于深度学习实验."""

import logging
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from src.models.registry import register_model
from src.models.base import BaseModel

logger = logging.getLogger(__name__)


class PositionalEncoding(nn.Module):
    """位置编码."""

    def __init__(self, d_model, max_len=5000):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-np.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)
        self.register_buffer("pe", pe)

    def forward(self, x):
        return x + self.pe[:, : x.size(1), :]


class SimpleTransformerClassifier(nn.Module):
    """简单的 Transformer 分类器."""

    def __init__(self, input_dim, hidden_dim=64, num_layers=2, dropout=0.3, nhead=4):
        super().__init__()
        self.input_projection = nn.Linear(input_dim, hidden_dim)
        self.pos_encoder = PositionalEncoding(hidden_dim)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=nhead,
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.fc = nn.Linear(hidden_dim, 1)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        # x: (batch, seq_len, input_dim)
        x = self.input_projection(x)
        x = self.pos_encoder(x)
        transformer_out = self.transformer_encoder(x)
        # 取最后一个时间步的输出
        out = transformer_out[:, -1, :]
        out = self.dropout(out)
        out = self.fc(out)
        return torch.sigmoid(out)


@register_model("transformer_classifier")
class TransformerClassifier(BaseModel):
    """Transformer 时间序列分类器封装."""

    def __init__(self, params: dict[str, Any] | None = None):
        p = params or {}
        self.hidden_dim = p.get("hidden_dim", 64)
        self.num_layers = p.get("num_layers", 2)
        self.epochs = p.get("epochs", 50)
        self.batch_size = p.get("batch_size", 32)
        self.learning_rate = p.get("learning_rate", 0.001)
        self.sequence_length = p.get("sequence_length", 21)
        self.dropout = p.get("dropout", 0.3)
        self.nhead = p.get("nhead", 4)
        self.random_state = p.get("random_state", 42)

        self.model = None
        self.classes_ = None
        self._fitted = False
        self.is_fitted = False

    def _create_sequences(self, X):
        sequences = []
        for i in range(len(X) - self.sequence_length + 1):
            sequences.append(X[i : i + self.sequence_length])
        return np.array(sequences)

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sample_weight: np.ndarray | None = None,
    ) -> "TransformerClassifier":
        torch.manual_seed(self.random_state)
        np.random.seed(self.random_state)

        self.classes_ = np.unique(y)

        X_seq = self._create_sequences(X)
        y_seq = y[self.sequence_length - 1 :]

        X_tensor = torch.FloatTensor(X_seq)
        y_tensor = torch.FloatTensor(y_seq).unsqueeze(1)

        dataset = TensorDataset(X_tensor, y_tensor)
        dataloader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)

        input_dim = X.shape[1]
        self.model = SimpleTransformerClassifier(
            input_dim=input_dim,
            hidden_dim=self.hidden_dim,
            num_layers=self.num_layers,
            dropout=self.dropout,
            nhead=self.nhead,
        )

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
        logger.info(f"Transformer 训练完成, n_samples={len(X_seq)}")
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
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
        if not self.is_fitted:
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
        return None
