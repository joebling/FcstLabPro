"""Orion-BiX 模型实验脚本.

使用 Python 3.10 环境的 Orion-BiX 进行实验.
"""

import sys
import os

import yaml
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import cohen_kappa_score, accuracy_score, f1_score

# Orion-BiX
from orion_bix import OrionBixClassifier


def load_data(config):
    """加载数据."""
    df = pd.read_csv(config['data']['path'])
    df['timestamp'] = pd.to_datetime(df['date'])

    # 过滤日期
    df = df[
        (df['timestamp'] >= config['data']['start']) &
        (df['timestamp'] <= config['data']['end'])
    ].reset_index(drop=True)

    # 尝试加载 FGI 数据
    fgi_path = 'data/external/fear_greed_index.csv'
    if os.path.exists(fgi_path):
        fgi_df = pd.read_csv(fgi_path)
        fgi_df['timestamp'] = pd.to_datetime(fgi_df['date'])
        fgi_df = fgi_df[['timestamp', 'fgi_value']].rename(columns={'fgi_value': 'fgi'})
        df = df.merge(fgi_df, on='timestamp', how='left')
        df['fgi'] = df['fgi'].ffill()
        print(f"加载 FGI 数据成功, 有效行: {df['fgi'].notna().sum()}")

    return df


def add_technical_features(df):
    """添加技术指标特征 - 增强版，包含 GBDT 重要特征."""
    # RSI (14 and 28)
    for window in [14, 28]:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / (loss + 1e-10)
        df[f'rsi_{window}'] = 100 - (100 / (1 + rs))

    # SMA
    for window in [5, 7, 21, 50, 100, 200]:
        df[f'sma_{window}'] = df['close'].rolling(window=window).mean()

    # 相对于 SMA 的位置 (重要特征)
    df['price_vs_sma_50'] = df['close'] / df['sma_50']
    df['price_vs_sma_200'] = df['close'] / df['sma_200']

    # SMA 金叉死叉 (重要特征)
    df['sma_cross_50_200'] = (df['sma_50'] > df['sma_200']).astype(int)

    # 波动率 (重要特征)
    df['volatility_5d'] = df['close'].pct_change().rolling(window=5).std()
    df['volatility_10d'] = df['close'].pct_change().rolling(window=10).std()
    df['volatility_20d'] = df['close'].pct_change().rolling(window=20).std()

    # 趋势强度
    df['trend_strength'] = (df['sma_7'] - df['sma_21']) / (df['sma_21'] + 1e-10)

    # 成交量变化
    df['volume_ma_7'] = df['volume'].rolling(window=7).mean()
    df['volume_ma_20'] = df['volume'].rolling(window=20).mean()
    df['volume_ratio'] = df['volume'] / (df['volume_ma_20'] + 1e-10)

    # 最高/最低距离 (重要特征)
    df['high_14d_dist'] = (df['close'] - df['high'].rolling(14).max()) / (df['close'] + 1e-10)
    df['low_14d_dist'] = (df['close'] - df['low'].rolling(14).min()) / (df['close'] + 1e-10)
    df['low_21d_dist'] = (df['close'] - df['low'].rolling(21).min()) / (df['close'] + 1e-10)
    df['low_50d_dist'] = (df['close'] - df['low'].rolling(50).min()) / (df['close'] + 1e-10)

    # ATR
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr_21'] = tr.rolling(21).mean()

    # MACD
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    return df


def build_features(df, config):
    """构建特征."""
    # 基础技术指标
    df = add_technical_features(df)

    # FGI 特征 (如果存在)
    if 'fgi' in df.columns and df['fgi'].notna().sum() > 0:
        df['fgi_ma_14'] = df['fgi'].rolling(14).mean()
        df['fgi_std_14'] = df['fgi'].rolling(14).std()
        df['fgi_ma_30'] = df['fgi'].rolling(30).mean()

    # Regime 特征
    df['regime_ma200_position'] = (df['close'] - df['sma_200']) / df['sma_200']
    df['regime_trend_strength'] = df['trend_strength']
    df['regime_volatility'] = df['volatility_20d']

    # 填充 NA
    df = df.ffill()
    df = df.dropna()

    return df


def build_labels(df, config):
    """构建标签."""
    T = config['label']['T']
    X = config['label']['X']

    # 计算未来 T 天的最大涨幅
    df['future_max'] = df['close'].shift(-T).rolling(window=T).max()
    df['future_return'] = (df['future_max'] - df['close']) / df['close']

    # 标签: 0=横盘, 1=小幅上涨, 2=大幅上涨
    df['label'] = 0  # 默认横盘
    df.loc[df['future_return'] > X, 'label'] = 2  # 大涨
    df.loc[(df['future_return'] > 0) & (df['future_return'] <= X), 'label'] = 1  # 小涨

    # 应用标签映射
    label_map = config['label']['map']
    df['label'] = df['label'].map(label_map)

    return df


def run_walk_forward(X, y, model_config, init_train=1500, oos_window=63, step=21):
    """Walk-forward 评估."""
    results = []
    n_samples = len(y)

    # Walk-forward
    train_end = init_train
    while train_end + oos_window <= n_samples:
        # 训练集
        X_train = X[:train_end]
        y_train = y[:train_end]

        # 测试集
        X_test = X[train_end:train_end + oos_window]
        y_test = y[train_end:train_end + oos_window]

        if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
            train_end += step
            continue

        # 标准化
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # 训练模型
        model = OrionBixClassifier(
            n_estimators=model_config.get('n_estimators', 16),
            random_state=model_config.get('random_state', 42),
            verbose=False,
        )
        model.fit(X_train_scaled, y_train)

        # 预测
        y_pred = model.predict(X_test_scaled)

        # 评估
        kappa = cohen_kappa_score(y_test, y_pred)
        acc = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, average='binary', zero_division=0)

        results.append({
            'train_end': train_end,
            'kappa': kappa,
            'accuracy': acc,
            'f1': f1,
        })

        train_end += step
        print(f"  Fold {len(results)}: Kappa={kappa:.4f}")

    return results


def main():
    """主函数."""
    # 加载配置
    config_path = sys.argv[1] if len(sys.argv) > 1 else 'configs/experiments/weekly/exp_weekly_bull_v27_orion.yaml'
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    print(f"开始实验: {config['experiment']['name']}")
    print(f"描述: {config['experiment']['description']}")

    # 加载数据
    print("加载数据...")
    df = load_data(config)
    print(f"原始数据: {len(df)} 行")

    # 构建特征
    print("构建特征...")
    df = build_features(df, config)
    print(f"特征数据: {len(df)} 行")

    # 构建标签
    print("构建标签...")
    df = build_labels(df, config)

    # 准备数据
    df = df.dropna(subset=['label'])

    # 特征列
    feature_cols = [c for c in df.columns if c not in ['date', 'timestamp', 'label', 'open', 'high', 'low', 'close', 'volume', 'quote_volume', 'trades', 'future_max', 'future_return']]
    X = df[feature_cols].values
    y = df['label'].values.astype(int)

    print(f"训练数据: {len(X)} 样本, {X.shape[1]} 特征")
    print(f"特征: {feature_cols}")
    print(f"类别分布: {np.bincount(y)}")

    # Walk-forward 评估
    print("运行 Walk-Forward 评估...")
    eval_config = config.get('evaluation', {})
    results = run_walk_forward(
        X, y,
        model_config=config.get('model', {}).get('params', {}),
        init_train=eval_config.get('init_train', 1500),
        oos_window=eval_config.get('oos_window', 63),
        step=eval_config.get('step', 21),
    )

    # 汇总结果
    kappas = [r['kappa'] for r in results]
    accs = [r['accuracy'] for r in results]
    f1s = [r['f1'] for r in results]

    print("\n" + "=" * 50)
    print(f"实验: {config['experiment']['name']}")
    print(f"Fold 数: {len(results)}")
    print(f"平均 Kappa: {np.mean(kappas):.4f} ± {np.std(kappas):.4f}")
    print(f"平均 Accuracy: {np.mean(accs):.4f}")
    print(f"平均 F1: {np.mean(f1s):.4f}")
    print("=" * 50)

    # 保存结果
    results_df = pd.DataFrame(results)
    results_file = f"experiments/weekly/{config['experiment']['name']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    os.makedirs(os.path.dirname(results_file), exist_ok=True)
    results_df.to_csv(results_file, index=False)
    print(f"结果已保存: {results_file}")


if __name__ == '__main__':
    main()
