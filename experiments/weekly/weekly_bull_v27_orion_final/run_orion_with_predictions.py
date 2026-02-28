import sys
import os

sys.path.insert(0, os.path.abspath('.'))

import yaml
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import cohen_kappa_score, accuracy_score, f1_score

from orion_bix import OrionBixClassifier


def load_data(config):
    df = pd.read_csv(config['data']['path'])
    df['timestamp'] = pd.to_datetime(df['date'])

    df = df[
        (df['timestamp'] >= config['data']['start']) &
        (df['timestamp'] <= config['data']['end'])
    ].reset_index(drop=True)

    fgi_path = 'data/external/fear_greed_index.csv'
    if os.path.exists(fgi_path):
        fgi_df = pd.read_csv(fgi_path)
        fgi_df['timestamp'] = pd.to_datetime(fgi_df['date'])
        fgi_df = fgi_df[['timestamp', 'fgi_value']].rename(columns={'fgi_value': 'fgi'})
        df = df.merge(fgi_df, on='timestamp', how='left')
        df['fgi'] = df['fgi'].ffill()

    return df


def add_technical_features(df):
    for window in [14, 28]:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / (loss + 1e-10)
        df[f'rsi_{window}'] = 100 - (100 / (1 + rs))

    for window in [5, 7, 21, 50, 100, 200]:
        df[f'sma_{window}'] = df['close'].rolling(window=window).mean()

    df['price_vs_sma_50'] = df['close'] / df['sma_50']
    df['price_vs_sma_200'] = df['close'] / df['sma_200']
    df['sma_cross_50_200'] = (df['sma_50'] > df['sma_200']).astype(int)

    df['volatility_5d'] = df['close'].pct_change().rolling(window=5).std()
    df['volatility_10d'] = df['close'].pct_change().rolling(window=10).std()
    df['volatility_20d'] = df['close'].pct_change().rolling(window=20).std()

    df['trend_strength'] = (df['sma_7'] - df['sma_21']) / (df['sma_21'] + 1e-10)

    df['volume_ma_7'] = df['volume'].rolling(window=7).mean()
    df['volume_ma_20'] = df['volume'].rolling(window=20).mean()
    df['volume_ratio'] = df['volume'] / (df['volume_ma_20'] + 1e-10)

    df['high_14d_dist'] = (df['close'] - df['high'].rolling(14).max()) / (df['close'] + 1e-10)
    df['low_14d_dist'] = (df['close'] - df['low'].rolling(14).min()) / (df['close'] + 1e-10)
    df['low_21d_dist'] = (df['close'] - df['low'].rolling(21).min()) / (df['close'] + 1e-10)
    df['low_50d_dist'] = (df['close'] - df['low'].rolling(50).min()) / (df['close'] + 1e-10)

    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr_21'] = tr.rolling(21).mean()

    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    return df


def build_features(df, config):
    df = add_technical_features(df)

    if 'fgi' in df.columns and df['fgi'].notna().sum() > 0:
        df['fgi_ma_14'] = df['fgi'].rolling(14).mean()
        df['fgi_std_14'] = df['fgi'].rolling(14).std()
        df['fgi_ma_30'] = df['fgi'].rolling(30).mean()

    df['regime_ma200_position'] = (df['close'] - df['sma_200']) / df['sma_200']
    df['regime_trend_strength'] = df['trend_strength']
    df['regime_volatility'] = df['volatility_20d']

    df = df.ffill()
    df = df.dropna()

    return df


def build_labels(df, config):
    T = config['label']['T']
    X = config['label']['X']

    df['future_max'] = df['close'].shift(-T).rolling(window=T).max()
    df['future_return'] = (df['future_max'] - df['close']) / df['close']

    df['label'] = 0
    df.loc[df['future_return'] > X, 'label'] = 2
    df.loc[(df['future_return'] > 0) & (df['future_return'] <= X), 'label'] = 1

    label_map = config['label']['map']
    df['label'] = df['label'].map(label_map)

    return df


def run_walk_forward(X, y, model_config, init_train=1500, oos_window=63, step=21):
    results = []
    all_y_true = []
    all_y_pred = []
    n_samples = len(y)

    train_end = init_train
    while train_end + oos_window <= n_samples:
        X_train = X[:train_end]
        y_train = y[:train_end]

        X_test = X[train_end:train_end + oos_window]
        y_test = y[train_end:train_end + oos_window]

        if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
            train_end += step
            continue

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        model = OrionBixClassifier(
            n_estimators=model_config.get('n_estimators', 16),
            random_state=model_config.get('random_state', 42),
            verbose=False,
        )
        model.fit(X_train_scaled, y_train)

        y_pred = model.predict(X_test_scaled)

        all_y_true.extend(y_test)
        all_y_pred.extend(y_pred)

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

    return results, np.array(all_y_true), np.array(all_y_pred)


def main():
    config_path = 'experiments/weekly/weekly_bull_v27_orion_final/config.yaml'
    exp_dir = 'experiments/weekly/weekly_bull_v27_orion_final'
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    print(f"开始实验: {config['experiment']['name']}")

    print("加载数据...")
    df = load_data(config)

    print("构建特征...")
    df = build_features(df, config)

    print("构建标签...")
    df = build_labels(df, config)
    df = df.dropna(subset=['label'])

    feature_cols = [c for c in df.columns if c not in ['date', 'timestamp', 'label', 'open', 'high', 'low', 'close', 'volume', 'quote_volume', 'trades', 'future_max', 'future_return']]
    X = df[feature_cols].values
    y = df['label'].values.astype(int)

    print(f"训练数据: {len(X)} 样本, {X.shape[1]} 特征")
    print(f"类别分布: {np.bincount(y)}")

    print("运行 Walk-Forward 评估...")
    eval_config = config.get('evaluation', {})
    results, all_y_true, all_y_pred = run_walk_forward(
        X, y,
        model_config=config.get('model', {}).get('params', {}),
        init_train=eval_config.get('init_train', 1500),
        oos_window=eval_config.get('oos_window', 63),
        step=eval_config.get('step', 21),
    )

    kappas = [r['kappa'] for r in results]
    accs = [r['accuracy'] for r in results]
    f1s = [r['f1'] for r in results]

    print("\n" + "=" * 80)
    print(f"实验: {config['experiment']['name']}")
    print(f"Fold 数: {len(results)}")
    print(f"平均 Kappa: {np.mean(kappas):.4f} ± {np.std(kappas):.4f}")
    print(f"平均 Accuracy: {np.mean(accs):.4f}")
    print(f"平均 F1: {np.mean(f1s):.4f}")
    print("=" * 80)

    results_df = pd.DataFrame(results)
    results_df.to_csv(os.path.join(exp_dir, 'fold_metrics.csv'), index=False)
    print(f"Fold 指标已保存: {os.path.join(exp_dir, 'fold_metrics.csv')}")

    pred_df = pd.DataFrame({
        'y_true': all_y_true,
        'y_pred': all_y_pred,
    })
    pred_df.to_csv(os.path.join(exp_dir, 'predictions.csv'), index=False)
    print(f"预测结果已保存: {os.path.join(exp_dir, 'predictions.csv')}")

    metrics = {
        'cohen_kappa': float(np.mean(kappas)),
        'accuracy': float(np.mean(accs)),
        'f1_binary': float(np.mean(f1s)),
    }
    import json
    with open(os.path.join(exp_dir, 'metrics.json'), 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"汇总指标已保存: {os.path.join(exp_dir, 'metrics.json')}")

if __name__ == '__main__':
    main()
