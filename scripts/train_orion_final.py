"""训练并保存 Orion-BiX 最终模型."""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import joblib
import yaml
import pandas as pd
from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns

# Orion-BiX
from orion_bix import OrionBixClassifier

# 配置
EXP_NAME = "weekly_bull_v29_orion_n4"
CONFIG_PATH = "configs/experiments/weekly/exp_weekly_bull_v27_orion.yaml"
OUTPUT_DIR = f"experiments/weekly/{EXP_NAME}"

# 加载配置
with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

print(f"训练 Orion-BiX 模型: {EXP_NAME}")

# 加载数据
data = load_csv(config['data']['path'])
print(f"数据加载完成: {len(data)} 行")

# 构建特征
feature_sets = config['features']['sets']
df = build_features(data, feature_sets, drop_na_method=config['features'].get('drop_na_method', 'ffill_then_drop'))
print(f"特征构建完成: {len(df.columns)} 列")

# 特征列（在添加标签之前获取，避免包含标签列）
feature_cols = get_feature_columns(df)
print(f"使用特征: {len(feature_cols)} 个")

# 标签
from src.labels.reversal import generate_reversal_labels
label_col = f"reversal_T{config['label']['T']}_X{config['label']['X']}"
df[label_col] = generate_reversal_labels(
    df,
    T=config['label']['T'],
    X=config['label']['X'],
)

X = df[feature_cols].values
y = df[label_col].values.astype(int)

# 标准化
from sklearn.preprocessing import StandardScaler
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# 训练模型
print("训练 Orion-BiX 模型...")
model = OrionBixClassifier(
    n_estimators=4,
    random_state=42,
)
model.fit(X_scaled, y)

# 保存
import os
os.makedirs(OUTPUT_DIR, exist_ok=True)

joblib.dump(model, f"{OUTPUT_DIR}/model.joblib")
joblib.dump(scaler, f"{OUTPUT_DIR}/scaler.joblib")
joblib.dump(feature_cols, f"{OUTPUT_DIR}/feature_cols.joblib")

# 保存配置
with open(f"{OUTPUT_DIR}/config.yaml", 'w') as f:
    yaml.dump(config, f)

print(f"模型已保存: {OUTPUT_DIR}/model.joblib")
print(f"正类比例: {y.mean():.2%}")
