#!/usr/bin/env python3
"""
E03: No MA Filter Test
=======================
Purpose: Quantify model vs Triple MA filter contribution.

Test: Compare Sharpe with and without Triple MA filter
- If without MA: Sharpe ~ with MA → model provides most alpha
- If without MA: Sharpe << with MA → alpha mainly from MA filter

Expected:
- With MA: Sharpe ~ 1.24 (v4 result)
- Without MA: Should be in 0.3-0.8 range if model has real alpha

Author: FcstLabPro
Date: 2026-02-20
"""

import sys
from pathlib import Path

# Add project root to path
for p in [Path.cwd(), Path(__file__).resolve().parent]:
    PROJECT_ROOT = p
    if (PROJECT_ROOT / "src").exists():
        sys.path.insert(0, str(PROJECT_ROOT))
        break
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import yaml
import json
from scipy.stats import spearmanr
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
import warnings
warnings.filterwarnings('ignore')

from src.data.loader import load_csv
from src.features.builder import build_features, get_feature_columns
import src.labels.reversal
from src.labels.registry import get_label_strategy


# ============================================================================
# Configuration
# ============================================================================

print("=" * 60)
print("E03: No MA Filter Test")
print("=" * 60)

DATA_PATH = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"
CONFIG_PATH = PROJECT_ROOT / "configs" / "experiments" / "weekly" / "exp_weekly_bull_v27_orion_v4_extended_oos.yaml"
OUTPUT_DIR = Path(__file__).parent


# ============================================================================
# Data Loading
# ============================================================================

with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)

print(f"\nConfig: {config['experiment']['name']}")
print(f"Label: T={config['label']['T']}, X={config['label']['X']}")

# Load data
print("\nLoading data...")
df = load_csv(str(DATA_PATH))
print(f"Raw data: {len(df)} rows")

# Build features
print("Building features...")
df = build_features(
    df,
    feature_sets=config['features']['sets'],
    drop_na_method=config['features'].get('drop_na_method', 'ffill_then_drop'),
)

# Generate labels
label_func = get_label_strategy(config['label']['strategy'])
labels = label_func(df, T=config['label']['T'], X=config['label']['X'])

# Apply label mapping
if 'map' in config['label']:
    mapping = {int(k): int(v) for k, v in config['label']['map'].items()}
    labels = labels.map(mapping)

df['label'] = labels
df = df.dropna(subset=['label'])
df['label'] = df['label'].astype(int)

# Get features
feature_cols = get_feature_columns(df)
X = df[feature_cols].values
y = df['label'].values
dates = df.index.tolist()
close_prices = df['close'].values

print(f"Data: {len(X)} samples, {len(feature_cols)} features")
print(f"Label distribution: {np.bincount(y)}")


# ============================================================================
# Walk-Forward Prediction
# ============================================================================

def run_walk_forward(X, y, init_train=800, oos_window=63, step=21):
    """Run walk-forward prediction."""
    n_samples = len(X)
    predictions = []
    true_labels = []
    valid_indices = []

    t = init_train
    while t + oos_window <= n_samples:
        X_train = X[:t]
        y_train = y[:t]

        X_test = X[t:t+oos_window]
        y_test = y[t:t+oos_window]

        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Train model
        model = RandomForestClassifier(
            n_estimators=100,
            max_depth=6,
            random_state=42,
            n_jobs=-1
        )
        model.fit(X_train_scaled, y_train)

        # Predict
        if len(model.classes_) == 2:
            preds = model.predict_proba(X_test_scaled)[:, 1]
        else:
            preds = np.zeros(len(X_test))

        predictions.extend(preds)
        true_labels.extend(y_test)
        valid_indices.extend(range(t, t+oos_window))

        t += step

    return np.array(predictions), np.array(true_labels), np.array(valid_indices)


# ============================================================================
# Run Prediction
# ============================================================================

print("\n" + "=" * 60)
print("Running walk-forward prediction...")
print("=" * 60)

predictions, true_labels, valid_idx = run_walk_forward(X, y)

print(f"Predictions: {len(predictions)}")


# ============================================================================
# Backtest Functions
# ============================================================================

def backtest_no_ma(signals, prices, valid_idx, step=21):
    """
    Backtest without MA filter.
    """
    # Align prices with predictions
    aligned_prices = []
    for idx in valid_idx:
        aligned_prices.append(prices[idx])
    aligned_prices = np.array(aligned_prices)

    # Convert signals to positions (threshold = 0.5)
    positions = (signals > 0.5).astype(int)

    # Calculate returns
    strategy_returns = []
    for i in range(len(positions) - 1):
        ret = (aligned_prices[i+1] - aligned_prices[i]) / aligned_prices[i]
        strategy_returns.append(positions[i] * ret)

    strategy_returns = np.array(strategy_returns)

    if len(strategy_returns) == 0 or np.std(strategy_returns) == 0:
        return {
            'sharpe': 0.0,
            'max_drawdown': 0.0,
            'total_return': 0.0,
            'win_rate': 0.0,
            'n_trades': 0,
        }

    # Sharpe
    sharpe = np.mean(strategy_returns) / np.std(strategy_returns) * np.sqrt(252 / step)

    # Max drawdown
    cumulative = np.cumprod(1 + strategy_returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = np.min(drawdown)

    return {
        'sharpe': sharpe,
        'max_drawdown': abs(max_drawdown),
        'total_return': cumulative[-1] - 1 if len(cumulative) > 0 else 0,
        'win_rate': np.mean(strategy_returns > 0),
        'n_trades': np.sum(np.diff(positions) != 0),
    }


def backtest_with_ma(signals, prices, valid_idx, step=21, ma_type='triple'):
    """
    Backtest with MA filter.
    """
    # Align prices with predictions
    aligned_prices = []
    for idx in valid_idx:
        aligned_prices.append(prices[idx])
    aligned_prices = np.array(aligned_prices)

    # Calculate MAs
    ma50 = pd.Series(aligned_prices).rolling(50).mean().values
    ma150 = pd.Series(aligned_prices).rolling(150).mean().values
    ma200 = pd.Series(aligned_prices).rolling(200).mean().values

    # Convert signals to positions
    positions = (signals > 0.5).astype(int)

    # Apply MA filter
    for i in range(len(positions)):
        if ma_type == 'triple':
            if not (aligned_prices[i] > ma50[i] and aligned_prices[i] > ma150[i] and aligned_prices[i] > ma200[i]):
                positions[i] = 0
        elif ma_type == 'ma200':
            if aligned_prices[i] < ma200[i]:
                positions[i] = 0

    # Calculate returns
    strategy_returns = []
    for i in range(len(positions) - 1):
        ret = (aligned_prices[i+1] - aligned_prices[i]) / aligned_prices[i]
        strategy_returns.append(positions[i] * ret)

    strategy_returns = np.array(strategy_returns)

    if len(strategy_returns) == 0 or np.std(strategy_returns) == 0:
        return {
            'sharpe': 0.0,
            'max_drawdown': 0.0,
            'total_return': 0.0,
            'win_rate': 0.0,
            'n_trades': 0,
        }

    # Sharpe
    sharpe = np.mean(strategy_returns) / np.std(strategy_returns) * np.sqrt(252 / step)

    # Max drawdown
    cumulative = np.cumprod(1 + strategy_returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = np.min(drawdown)

    return {
        'sharpe': sharpe,
        'max_drawdown': abs(max_drawdown),
        'total_return': cumulative[-1] - 1 if len(cumulative) > 0 else 0,
        'win_rate': np.mean(strategy_returns > 0),
        'n_trades': np.sum(np.diff(positions) != 0),
    }


# ============================================================================
# Run Backtests
# ============================================================================

step = config['evaluation']['step']

print("\n" + "=" * 60)
print("Running backtests...")
print("=" * 60)

# Without MA
results_no_ma = backtest_no_ma(predictions, close_prices, valid_idx, step)
print(f"\nWithout MA Filter:")
print(f"  Sharpe: {results_no_ma['sharpe']:.4f}")
print(f"  Max Drawdown: {results_no_ma['max_drawdown']:.4f}")
print(f"  Total Return: {results_no_ma['total_return']:.4f}")
print(f"  Win Rate: {results_no_ma['win_rate']:.4f}")
print(f"  N Trades: {results_no_ma['n_trades']}")

# With Triple MA
results_triple_ma = backtest_with_ma(predictions, close_prices, valid_idx, step, ma_type='triple')
print(f"\nWith Triple MA Filter:")
print(f"  Sharpe: {results_triple_ma['sharpe']:.4f}")
print(f"  Max Drawdown: {results_triple_ma['max_drawdown']:.4f}")
print(f"  Total Return: {results_triple_ma['total_return']:.4f}")
print(f"  Win Rate: {results_triple_ma['win_rate']:.4f}")
print(f"  N Trades: {results_triple_ma['n_trades']}")

# With MA200
results_ma200 = backtest_with_ma(predictions, close_prices, valid_idx, step, ma_type='ma200')
print(f"\nWith MA200 Filter:")
print(f"  Sharpe: {results_ma200['sharpe']:.4f}")
print(f"  Max Drawdown: {results_ma200['max_drawdown']:.4f}")
print(f"  Total Return: {results_ma200['total_return']:.4f}")
print(f"  Win Rate: {results_ma200['win_rate']:.4f}")
print(f"  N Trades: {results_ma200['n_trades']}")


# ============================================================================
# Results
# ============================================================================

print("\n" + "=" * 60)
print("RESULTS SUMMARY")
print("=" * 60)

print(f"\n| Filter | Sharpe | MaxDD | Return | WinRate |")
print(f"|--------|--------|-------|--------|---------|")
print(f"| No MA  | {results_no_ma['sharpe']:.4f} | {results_no_ma['max_drawdown']:.4f} | {results_no_ma['total_return']:.4f} | {results_no_ma['win_rate']:.4f} |")
print(f"| Triple | {results_triple_ma['sharpe']:.4f} | {results_triple_ma['max_drawdown']:.4f} | {results_triple_ma['total_return']:.4f} | {results_triple_ma['win_rate']:.4f} |")
print(f"| MA200  | {results_ma200['sharpe']:.4f} | {results_ma200['max_drawdown']:.4f} | {results_ma200['total_return']:.4f} | {results_ma200['win_rate']:.4f} |")


# ============================================================================
# Conclusion
# ============================================================================

print("\n" + "=" * 60)
print("CONCLUSION")
print("=" * 60)

sharpe_ratio_no_ma = results_no_ma['sharpe']
sharpe_ratio_with_ma = results_triple_ma['sharpe']

if sharpe_ratio_no_ma < 0.3:
    conclusion = "WEAK - Alpha mainly from MA filter, not model"
    detail = f"Sharpe without MA ({sharpe_ratio_no_ma:.4f}) < 0.3, model has little independent alpha"
elif sharpe_ratio_no_ma < 0.8:
    conclusion = "MARGINAL - Some model alpha, but MA contributes significantly"
    detail = f"Sharpe without MA ({sharpe_ratio_no_ma:.4f}) in 0.3-0.8 range"
else:
    conclusion = "STRONG - Model has real independent alpha"
    detail = f"Sharpe without MA ({sharpe_ratio_no_ma:.4f}) > 0.8, model provides substantial alpha"

print(f"\n{conclusion}")
print(f"  {detail}")
print(f"\nMA Contribution:")
print(f"  Sharpe improvement from MA: {sharpe_ratio_with_ma - sharpe_ratio_no_ma:.4f}")
print(f"  Percentage from model: {sharpe_ratio_no_ma / sharpe_ratio_with_ma * 100:.1f}%")


# ============================================================================
# Save Results
# ============================================================================

output_data = {
    'experiment': 'E03 No MA Filter Test',
    'results_no_ma': results_no_ma,
    'results_triple_ma': results_triple_ma,
    'results_ma200': results_ma200,
    'conclusion': conclusion,
    'detail': detail,
    'model_contribution_pct': sharpe_ratio_no_ma / sharpe_ratio_with_ma * 100 if sharpe_ratio_with_ma > 0 else 0,
}

with open(OUTPUT_DIR / 'results.json', 'w') as f:
    json.dump(output_data, f, indent=2, default=str)

print(f"\nResults saved to {OUTPUT_DIR}/")
