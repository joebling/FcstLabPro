"""
v0302 Alpha Validation - Common Utilities
==========================================
Shared functions for all validation experiments.

Author: FcstLabPro
Date: 2026-02-20
"""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import joblib
import yaml
from scipy.stats import spearmanr
from typing import Tuple, Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

# Base configuration - v4 Extended OOS
BASE_CONFIG_PATH = PROJECT_ROOT / "configs" / "experiments" / "weekly" / "exp_weekly_bull_v27_orion_v4_extended_oos.yaml"
BASE_MODEL_DIR = PROJECT_ROOT / "experiments" / "weekly" / "weekly_bull_v27_orion_v4_extended_oos"
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "btc_binance_BTCUSDT_1d.csv"


# ============================================================================
# Data Loading Functions
# ============================================================================

def load_base_config() -> dict:
    """Load base v4 configuration."""
    with open(BASE_CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f)


def load_base_data(config_path: str = None) -> Tuple[pd.DataFrame, np.ndarray, np.ndarray, List[str]]:
    """
    Load base data and features for v4 model.

    Returns:
        df: DataFrame with features and close prices
        X: Feature array
        y: Label array
        dates: List of dates
    """
    config = load_base_config() if config_path is None else yaml.safe_load(open(config_path))

    # Load data
    from src.data.loader import load_csv
    df = load_csv(str(DATA_PATH))

    # Build features
    from src.features.builder import build_features, get_feature_columns
    df = build_features(
        df,
        feature_sets=config['features']['sets'],
        drop_na_method=config['features'].get('drop_na_method', 'ffill_then_drop'),
    )

    # Generate labels
    from src.labels.registry import get_label_strategy
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

    return df, X, y, dates, close_prices, feature_cols


def generate_reversal_labels(df: pd.DataFrame, T: int = 21, X: float = 0.05) -> pd.Series:
    """
    Generate reversal labels.

    Label logic:
    - If future T-day return < -X (drop > X%), label = 2 (buy signal)
    - If future T-day return > X (rise > X%), label = 0 (sell signal)
    - Otherwise label = 1 (hold)

    For binary classification: map {0, 1} -> 0, {2} -> 1
    """
    future_return = df['close'].shift(-T) / df['close'] - 1

    labels = pd.Series(index=df.index, dtype=int)

    # label 0: significant rise (> X%)
    labels[future_return > X] = 0
    # label 1: middle ground
    labels[(future_return <= X) & (future_return >= -X)] = 1
    # label 2: significant drop (< -X%)
    labels[future_return < -X] = 2

    return labels


# ============================================================================
# Walk-Forward Prediction
# ============================================================================

def walk_forward_predict(
    X: pd.DataFrame,
    y: pd.Series,
    config: dict,
    init_train: int = None,
    oos_window: int = None,
    step: int = None
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """
    Run walk-forward prediction.

    Args:
        X: Feature DataFrame
        y: Labels
        config: Configuration dict
        init_train: Initial training size (overrides config)
        oos_window: OOS window size (overrides config)
        step: Step size (overrides config)

    Returns:
        predictions: Array of predictions
        true_labels: Array of true labels
        dates: List of prediction dates
    """
    from orion.benchmark import OrionBenchmark

    init_train = init_train or config['evaluation']['init_train']
    oos_window = oos_window or config['evaluation']['oos_window']
    step = step or config['evaluation']['step']

    # Prepare data
    data = X.copy()
    data['label'] = y

    # Use Orion benchmark for walk-forward
    benchmark = OrionBenchmark(
        patterns=[data],
        metrics=['f1_binary'],
    )

    # Run benchmark
    results = benchmark.run(
        ['orion.chi.0.03'],
        train_size=init_train,
        test_size=oos_window,
        stride=step,
    )

    # Extract predictions
    predictions = []
    true_labels = []
    dates = []

    for pattern_result in results:
        for train_result in pattern_result:
            preds = train_result['y_pred']
            true_vals = train_result['y_true']

            predictions.extend(preds)
            true_labels.extend(true_vals)

            if 'timestamp' in train_result:
                dates.extend(train_result['timestamp'])

    return np.array(predictions), np.array(true_labels), dates


def walk_forward_predict_simple(
    X: np.ndarray,
    y: np.ndarray,
    config: dict,
    init_train: int = None,
    oos_window: int = None,
    step: int = None
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Simplified walk-forward prediction using sklearn models.

    Args:
        X: Feature array (n_samples, n_features)
        y: Label array
        config: Configuration dict
        init_train: Initial training size
        oos_window: OOS window size
        step: Step size

    Returns:
        predictions: Array of predictions
        returns: Array of future returns
    """
    from sklearn.ensemble import RandomForestClassifier

    init_train = init_train or config['evaluation']['init_train']
    oos_window = oos_window or config['evaluation']['oos_window']
    step = step or config['evaluation']['step']

    n_samples = len(X)
    predictions = []
    returns = []

    # Generate future returns
    T = config['label']['T']
    close_prices = np.zeros(n_samples + T)

    for i in range(n_samples):
        if i + T < n_samples:
            future_return = (close_prices[i+T] - close_prices[i]) / close_prices[i] if close_prices[i] != 0 else 0
        else:
            future_return = 0

    t = init_train
    while t + oos_window <= n_samples:
        X_train = X[:t]
        y_train = y[:t]

        X_test = X[t:t+oos_window]
        y_test = y[t:t+oos_window]

        # Train model
        model = RandomForestClassifier(
            n_estimators=16,
            max_depth=5,
            random_state=42,
            n_jobs=-1
        )
        model.fit(X_train, y_train)

        # Predict
        preds = model.predict_proba(X_test)[:, 1] if len(model.classes_) > 1 else model.predict_proba(X_test)[:, 0]

        predictions.extend(preds)

        # Calculate returns for each prediction
        for i in range(len(preds)):
            idx = t + i
            if idx + T < n_samples:
                future_ret = (close_prices[idx+T] - close_prices[idx]) / close_prices[idx] if close_prices[idx] != 0 else 0
            else:
                future_ret = 0
            returns.append(future_ret)

        t += step

    return np.array(predictions), np.array(returns)


# ============================================================================
# IC Calculation Functions
# ============================================================================

def non_overlapping_ic(
    predictions: np.ndarray,
    returns: np.ndarray,
    step: int = 21
) -> Tuple[float, float]:
    """
    Calculate IC using non-overlapping samples.

    Args:
        predictions: Model predictions
        returns: Future returns
        step: Step size for non-overlapping

    Returns:
        ic: Spearman IC
        p_val: p-value
    """
    # Take non-overlapping samples
    n = len(predictions)
    n_non_overlap = n // step

    if n_non_overlap < 2:
        return 0.0, 1.0

    non_overlap_preds = predictions[:n_non_overlap * step:step]
    non_overlap_returns = returns[:n_non_overlap * step:step]

    ic, p_val = spearmanr(non_overlap_preds, non_overlap_returns)

    return ic, p_val


def monthly_ic_series(
    predictions: np.ndarray,
    returns: np.ndarray,
    dates: List[str],
    step: int = 21
) -> np.ndarray:
    """
    Calculate monthly IC series.

    Args:
        predictions: Predictions
        returns: Returns
        dates: Dates for each prediction
        step: Step size

    Returns:
        ic_series: Array of monthly ICs
    """
    if dates is None or len(dates) == 0:
        # Create dummy dates
        dates = pd.date_range(start='2022-01-01', periods=len(predictions), freq='21D')

    df = pd.DataFrame({
        'pred': predictions,
        'return': returns,
        'date': pd.to_datetime(dates) if isinstance(dates[0], str) else dates
    })

    df['month'] = df['date'].dt.to_period('M')

    ic_series = []
    for month in df['month'].unique():
        month_data = df[df['month'] == month]
        if len(month_data) >= 3:
            ic, _ = spearmanr(month_data['pred'], month_data['return'])
            ic_series.append(ic)

    return np.array(ic_series)


def newey_west_tstat(ic_series: np.ndarray, max_lag: int = 3) -> float:
    """
    Calculate Newey-West adjusted t-statistic.

    Args:
        ic_series: Array of IC values
        max_lag: Maximum lag for Newey-West correction

    Returns:
        t_stat: Newey-West adjusted t-statistic
    """
    from statsmodels.regression.linear_model import OLS

    if len(ic_series) < 5:
        return 0.0

    # OLS with HAC standard errors
    X = np.ones(len(ic_series))
    model = OLS(ic_series, X)
    result = model.fit(cov_type='HAC', cov_kwds={'maxlags': max_lag})

    return result.tvalues[0]


def bootstrap_ci(
    predictions: np.ndarray,
    returns: np.ndarray,
    n_boot: int = 1000,
    block_size: int = 4
) -> Tuple[float, float, float]:
    """
    Calculate bootstrap confidence intervals for IC.

    Args:
        predictions: Predictions
        returns: Returns
        n_boot: Number of bootstrap iterations
        block_size: Block size for block bootstrap

    Returns:
        ic_mean: Mean IC
        ci_lower: 2.5 percentile
        ci_upper: 97.5 percentile
    """
    pairs = list(zip(predictions, returns))

    # IID Bootstrap
    iid_ics = []
    for _ in range(n_boot):
        idx = np.random.choice(len(pairs), size=len(pairs), replace=True)
        boot_preds = [pairs[i][0] for i in idx]
        boot_rets = [pairs[i][1] for i in idx]

        if len(set(boot_preds)) > 1 and len(set(boot_rets)) > 1:
            ic, _ = spearmanr(boot_preds, boot_rets)
            iid_ics.append(ic)

    iid_ics = np.array(iid_ics)

    # Block Bootstrap
    n_blocks = len(pairs) // block_size
    block_ics = []
    for _ in range(n_boot):
        block_idx = np.random.choice(n_blocks, size=n_blocks, replace=True)
        boot_idx = []
        for b in block_idx:
            boot_idx.extend(range(b * block_size, min((b + 1) * block_size, len(pairs))))

        boot_preds = [pairs[i][0] for i in boot_idx if i < len(pairs)]
        boot_rets = [pairs[i][1] for i in boot_idx if i < len(pairs)]

        if len(set(boot_preds)) > 1 and len(set(boot_rets)) > 1:
            ic, _ = spearmanr(boot_preds, boot_rets)
            block_ics.append(ic)

    block_ics = np.array(block_ics)

    return (
        np.mean(iid_ics),
        np.percentile(iid_ics, 2.5),
        np.percentile(iid_ics, 97.5),
        np.percentile(block_ics, 2.5),
        np.percentile(block_ics, 97.5),
    )


# ============================================================================
# Backtest Functions
# ============================================================================

def backtest_strategy(
    signals: np.ndarray,
    prices: np.ndarray,
    step: int = 21,
    ma_filter: str = None
) -> Dict:
    """
    Backtest a trading strategy.

    Args:
        signals: Trading signals (0-1 probability)
        prices: Price series
        step: Signal step size
        ma_filter: MA filter ('triple', 'ma200', None)

    Returns:
        metrics: Dictionary with backtest metrics
    """
    # Convert signals to positions
    positions = (signals > 0.5).astype(int)

    # Apply MA filter if specified
    if ma_filter is not None:
        ma50 = pd.Series(prices).rolling(50).mean().values
        ma150 = pd.Series(prices).rolling(150).mean().values
        ma200 = pd.Series(prices).rolling(200).mean().values

        for i in range(len(positions)):
            if ma_filter == 'triple':
                if not (prices[i] > ma50[i] and prices[i] > ma150[i] and prices[i] > ma200[i]):
                    positions[i] = 0
            elif ma_filter == 'ma200':
                if prices[i] < ma200[i]:
                    positions[i] = 0

    # Calculate returns
    strategy_returns = []
    for i in range(len(positions) - 1):
        ret = (prices[i+1] - prices[i]) / prices[i]
        strategy_returns.append(positions[i] * ret)

    strategy_returns = np.array(strategy_returns)

    # Calculate metrics
    if len(strategy_returns) == 0 or np.std(strategy_returns) == 0:
        return {
            'sharpe': 0.0,
            'max_drawdown': 0.0,
            'total_return': 0.0,
            'win_rate': 0.0,
        }

    sharpe = np.mean(strategy_returns) / np.std(strategy_returns) * np.sqrt(252)

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
# Report Generation
# ============================================================================

def save_results(
    experiment_name: str,
    results: dict,
    output_dir: Path = None
) -> None:
    """Save experiment results to files."""
    if output_dir is None:
        output_dir = Path(__file__).parent / experiment_name

    output_dir.mkdir(parents=True, exist_ok=True)

    # Save as JSON
    import json
    with open(output_dir / 'results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)

    # Save as CSV if there's tabular data
    if 'table' in results and results['table']:
        df = pd.DataFrame(results['table'])
        df.to_csv(output_dir / 'results.csv', index=False)

    print(f"Results saved to {output_dir}")


def generate_report(
    experiment_name: str,
    experiment_description: str,
    results: dict,
    conclusion: str,
    output_dir: Path = None
) -> str:
    """Generate markdown report for an experiment."""
    if output_dir is None:
        output_dir = Path(__file__).parent / experiment_name

    output_dir.mkdir(parents=True, exist_ok=True)

    report = f"""# {experiment_name}

## Description
{experiment_description}

## Results

| Metric | Value |
|---------|-------|
"""

    for key, value in results.items():
        if isinstance(value, float):
            report += f"| {key} | {value:.4f} |\n"
        else:
            report += f"| {key} | {value} |\n"

    report += f"""
## Conclusion

{conclusion}

---
*Generated: 2026-02-20*
"""

    with open(output_dir / 'report.md', 'w') as f:
        f.write(report)

    print(f"Report saved to {output_dir / 'report.md'}")

    return report
