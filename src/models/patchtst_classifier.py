"""PatchTST (Patch Time Series Transformer) 时间序列分类器."""

import logging
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from src.models.registry import register_model
from src.models.base import BaseModel

logger = logging.getLogger(__name__)


class PatchEmbedding(nn.Module):
    """Patch 嵌入层."""

    def __init__(self, input_dim, patch_size, hidden_dim):
        super().__init__()
        self.patch_size = patch_size
        self.projection = nn.Linear(patch_size * input_dim, hidden_dim)

    def forward(self, x):
        """
        x: (batch, seq_len, input_dim)
        """
        # 将序列分割成 patches
        seq_len = x.shape[1]
        num_patches = seq_len // self.patch_size

        # (batch, num_patches, patch_size, input_dim)
        x = x[:, : num_patches * self.patch_size, :]
        x = x.reshape(x.shape[0], num_patches, self.patch_size, x.shape[2])

        # (batch, num_patches, patch_size * input_dim)
        x = x.reshape(x.shape[0], num_patches, -1)

        # 投影到 hidden_dim
        x = self.projection(x)
        return x


class PatchTSTEncoder(nn.Module):
    """PatchTST 编码器."""

    def __init__(
        self,
        num_patches,
        hidden_dim,
        num_layers,
        nhead,
        dropout=0.1,
        mlp_ratio=4,
    ):
        super().__init__()

        # 可学习的 Patch 位置编码
        self.pos_embedding = nn.Parameter(torch.randn(1, num_patches, hidden_dim) * 0.02)

        # Transformer 编码器
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=nhead,
            dim_feedforward=hidden_dim * mlp_ratio,
            dropout=dropout,
            batch_first=True,
            activation="gelu",
            norm_first=True,  # Pre-LN
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        # 层归一化
        self.norm = nn.LayerNorm(hidden_dim)

    def forward(self, x):
        # 添加位置编码
        x = x + self.pos_embedding

        # Transformer 编码
        x = self.transformer(x)

        # 最终归一化
        x = self.norm(x)
        return x


class PatchTSTClassifier(nn.Module):
    """PatchTST 分类器."""

    def __init__(
        self,
        input_dim,
        patch_size=4,
        hidden_dim=128,
        num_layers=3,
        nhead=4,
        dropout=0.1,
    ):
        super().__init__()
        self.patch_size = patch_size
        self.hidden_dim = hidden_dim

        # Patch 嵌入
        # 假设固定序列长度，这里用 21 (T=21)
        # num_patches = 21 // patch_size = 5
        num_patches = 21 // patch_size if patch_size > 0 else 21

        self.patch_embedding = PatchEmbedding(input_dim, patch_size, hidden_dim)

        # 编码器
        self.encoder = PatchTSTEncoder(
            num_patches=num_patches,
            hidden_dim=hidden_dim,
            num_layers=num_layers,
            nhead=nhead,
            dropout=dropout,
        )

        # 输出层 - 聚合所有 patch 的信息
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1),
            nn.Sigmoid(),
        )

    def forward(self, x):
        """
        x: (batch, seq_len, input_dim)
        """
        # Patch 嵌入
        x = self.patch_embedding(x)

        # 编码
        x = self.encoder(x)

        # 池化所有 patch (mean pooling)
        x = x.mean(dim=1)

        # 输出
        out = self.fc(x)
        return out


@register_model("patchtst_classifier")
class PatchTSTClassifierWrapper(BaseModel):
    """PatchTST 时间序列分类器封装."""

    def __init__(self, params: dict[str, Any] | None = None):
        p = params or {}
        self.hidden_dim = p.get("hidden_dim", 128)
        self.num_layers = p.get("num_layers", 3)
        self.epochs = p.get("epochs", 50)
        self.batch_size = p.get("batch_size", 32)
        self.learning_rate = p.get("learning_rate", 0.001)
        self.sequence_length = p.get("sequence_length", 21)
        self.patch_size = p.get("patch_size", 4)
        self.dropout = p.get("dropout", 0.1)
        self.nhead = p.get("nhead", 4)
        self.random_state = p.get("random_state", 42)

        self.model = None
        self.classes_ = None
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
    ) -> "PatchTSTClassifierWrapper":
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

        # 验证 patch_size 能整除 sequence_length
        if self.sequence_length % self.patch_size != 0:
            logger.warning(
                f"patch_size={self.patch_size} 不能整除 sequence_length={self.sequence_length}，"
                f"自动调整为 {self.sequence_length // 4}"
            )
            self.patch_size = max(1, self.sequence_length // 4)

        self.model = PatchTSTClassifier(
            input_dim=input_dim,
            patch_size=self.patch_size,
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
        logger.info(f"PatchTST 训练完成, n_samples={len(X_seq)}")
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
