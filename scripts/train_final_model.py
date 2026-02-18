"""训练并保存 Orion-BiX 最终模型 - 用于部署."""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import os
import joblib
import yaml
import pandas as pd
from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns
from orion_bix import OrionBixClassifier
from src.labels.reversal import generate_reversal_labels
from sklearn.preprocessing import StandardScaler
import json
from datetime import datetime

# 配置 - 使用 Final v2 配置
CONFIG_PATH = "configs/experiments/weekly/exp_weekly_bull_v27_orion.yaml"
OUTPUT_DIR = "experiments/weekly/weekly_bull_v27_orion_v2"

# 加载配置
with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

print(f"训练 Orion-BiX 模型: {OUTPUT_DIR}")
print(f"配置: T={config['label']['T']}, X={config['label']['X']}")

# 加载数据
data = load_csv(config['data']['path'])
print(f"数据加载完成: {len(data)} 行")

# 构建特征
feature_sets = config['features']['sets']
df = build_features(data, feature_sets, drop_na_method=config['features'].get('drop_na_method', 'ffill_then_drop'))
print(f"特征构建完成: {len(df.columns)} 列")

# 特征列
feature_cols = get_feature_columns(df)
print(f"使用特征: {len(feature_cols)} 个")

# 标签
label_col = f"reversal_T{config['label']['T']}_X{config['label']['X']}"
df[label_col] = generate_reversal_labels(
    df,
    T=config['label']['T'],
    X=config['label']['X'],
)

# 删除NaN行
df = df.dropna(subset=feature_cols + [label_col])
print(f"清洗后数据: {len(df)} 行")

X = df[feature_cols].values
y = df[label_col].values.astype(int)

# 标准化
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# 训练模型 - 使用配置中的 n_estimators
n_estimators = config['model']['params'].get('n_estimators', 16)
print(f"训练 Orion-BiX 模型 (n_estimators={n_estimators})...")
model = OrionBixClassifier(
    n_estimators=n_estimators,
    random_state=config['model']['params'].get('random_state', 42),
)
model.fit(X_scaled, y)

# 保存
os.makedirs(OUTPUT_DIR, exist_ok=True)

joblib.dump(model, f"{OUTPUT_DIR}/model.joblib")
joblib.dump(scaler, f"{OUTPUT_DIR}/scaler.joblib")
joblib.dump(feature_cols, f"{OUTPUT_DIR}/feature_cols.joblib")

# 保存配置
config['experiment']['name'] = 'weekly_bull_v27_orion_final_deploy'
config['experiment']['description'] = 'Bull v27: Orion-BiX 部署版本 - T=21 + FGI + Regime'
with open(f"{OUTPUT_DIR}/config.yaml", 'w') as f:
    yaml.dump(config, f, default_flow_style=False)

# 保存 meta.json
meta = {
    "experiment_id": "weekly_bull_v27_orion_final_deploy",
    "name": "weekly_bull_v27_orion_final_deploy",
    "description": "Bull v27: Orion-BiX 部署版本",
    "tags": ["weekly", "bull", "binary", "v27", "orion", "deploy"],
    "category": "weekly",
    "created_at": datetime.now().isoformat(),
    "seed": 42,
    "status": "completed",
    "model_params": {
        "n_estimators": n_estimators,
        "random_state": 42
    },
    "label_config": {
        "T": config['label']['T'],
        "X": config['label']['X'],
        "strategy": config['label']['strategy']
    }
}
with open(f"{OUTPUT_DIR}/meta.json", 'w') as f:
    json.dump(meta, f, indent=2)

print(f"\n模型已保存到: {OUTPUT_DIR}/")
print(f"  - model.joblib")
print(f"  - scaler.joblib")
print(f"  - feature_cols.joblib")
print(f"  - config.yaml")
print(f"  - meta.json")
print(f"正类比例: {y.mean():.2%}")
