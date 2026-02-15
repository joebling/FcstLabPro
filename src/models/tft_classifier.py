"""TFT (Temporal Fusion Transformer) 时间序列分类器."""

import logging
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from src.models.registry import register_model
from src.models.base import BaseModel

logger = logging.getLogger(__name__)


class GatedResidualNetwork(nn.Module):
    """门控残差网络 (Gated Residual Network)."""

    def __init__(self, input_dim, hidden_dim, output_dim, dropout=0.1):
        super().__init__()
        self.input_projection = nn.Linear(input_dim, hidden_dim)
        self.hidden_layer = nn.Linear(hidden_dim, hidden_dim)
        self.output_projection = nn.Linear(hidden_dim, output_dim)
        self.gate = nn.Linear(hidden_dim, output_dim)
        self.dropout = nn.Dropout(dropout)
        self.layer_norm = nn.LayerNorm(output_dim)

    def forward(self, x):
        # x: (batch, input_dim)
        hidden = torch.relu(self.input_projection(x))
        hidden = self.dropout(hidden)
        hidden = torch.relu(self.hidden_layer(hidden))
        gate = torch.sigmoid(self.gate(hidden))
        output = self.output_projection(hidden)
        output = gate * output

        # 残差连接
        if output.shape[-1] != x.shape[-1]:
            x = nn.functional.linear(x, torch.eye(x.shape[-1], output.shape[-1]).to(x.device))
        output = self.layer_norm(output + x)
        return output


class TimeDistributed(nn.Module):
    """时间分布式层 - 对序列中每个时间步应用相同的层."""

    def __init__(self, module):
        super().__init__()
        self.module = module

    def forward(self, x):
        # x: (batch, seq_len, features)
        batch_size, seq_len = x.shape[0], x.shape[1]
        x_reshaped = x.reshape(-1, x.shape[-1])  # (batch*seq_len, features)
        out = self.module(x_reshaped)
        out = out.reshape(batch_size, seq_len, -1)
        return out


class TFTClassifier(nn.Module):
    """简化版 TFT 分类器."""

    def __init__(
        self,
        input_dim,
        static_dim=0,
        hidden_dim=64,
        num_layers=2,
        nhead=4,
        dropout=0.1,
    ):
        super().__init__()
        self.static_dim = static_dim
        self.hidden_dim = hidden_dim

        # 静态特征处理 (如果有)
        if static_dim > 0:
            self.static_grn = GatedResidualNetwork(static_dim, hidden_dim, hidden_dim, dropout)
        else:
            self.static_grn = None

        # 时序特征处理
        self.input_projection = nn.Linear(input_dim, hidden_dim)

        # 变长注意力 (Variable Selection Network)
        self.vsn_grn = GatedResidualNetwork(input_dim, hidden_dim, input_dim, dropout)

        # Transformer 编码器
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=nhead,
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        # 静态上下文向量 (用于初始化 LSTM 状态)
        self.static_context = nn.Linear(hidden_dim, hidden_dim)

        # 输出层
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1),
            nn.Sigmoid(),
        )

    def forward(self, x, static_features=None):
        """
        x: (batch, seq_len, input_dim)
        static_features: (batch, static_dim) 可选
        """
        batch_size, seq_len, _ = x.shape

        # 静态特征处理
        if self.static_grn is not None and static_features is not None:
            static_embedding = self.static_grn(static_features)
            static_context = self.static_context(static_embedding)
            # 将静态上下文加到每个时间步
            static_context = static_context.unsqueeze(1).expand(-1, seq_len, -1)
        else:
            static_context = 0

        # 变长选择
        vsn_weights = torch.softmax(self.vsn_grn(x), dim=-1)
        x = x * vsn_weights

        # 输入投影
        x = self.input_projection(x)
        x = x + static_context

        # Transformer 编码
        transformer_out = self.transformer_encoder(x)

        # 取最后一个时间步
        out = transformer_out[:, -1, :]

        # 输出
        out = self.fc(out)
        return out


@register_model("tft_classifier")
class TFTClassifierWrapper(BaseModel):
    """TFT 时间序列分类器封装."""

    def __init__(self, params: dict[str, Any] | None = None):
        p = params or {}
        self.hidden_dim = p.get("hidden_dim", 64)
        self.num_layers = p.get("num_layers", 2)
        self.epochs = p.get("epochs", 50)
        self.batch_size = p.get("batch_size", 32)
        self.learning_rate = p.get("learning_rate", 0.001)
        self.sequence_length = p.get("sequence_length", 21)
        self.dropout = p.get("dropout", 0.1)
        self.nhead = p.get("nhead", 4)
        self.random_state = p.get("random_state", 42)

        self.model = None
        self.classes_ = None
        self.is_fitted = False
        self.static_dim = 0  # 暂不实现静态特征分离

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
    ) -> "TFTClassifierWrapper":
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
        self.model = TFTClassifier(
            input_dim=input_dim,
            static_dim=self.static_dim,
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

        self.is_fitted = True
        logger.info(f"TFT 训练完成, n_samples={len(X_seq)}")
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
