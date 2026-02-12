# 🚀 FcstLabPro: Final Comprehensive Report

**Date**: 2026-02-13
**Project**: Bitcoin Price Prediction Experiment Platform (Refactored & Extended)
**Repo**: [FcstLabPro](https://github.com/joebling/FcstLabPro)

---

## 1. Project Overview & Achievements

### 🎯 Goal
To rebuild and extend the Bitcoin price prediction platform ("FcstLabPro") by benchmarking against best practices from legacy projects. The objective was to create a structured, traceable, scalable, and easy-to-compare machine learning experiment platform.

### 🏗 Architecture & Infrastructure
We have successfully implemented a robust infrastructure:
- **Multi-level Experiment Structure**: Organized experiments into `baseline`, `feature_study`, `param_tuning`, etc., allowing for clear separation of concerns.
- **Enhanced Feature Registry**: A central `FeatureBuilder` capable of generating **340+ features** across 7 distinct categories (Technical, Volume, Market Structure, On-chain, Sentiment, Flow, Lag/Rolling).
- **Advanced Experiment Tracker**: A `Tracker` class that supports recursive discovery, category filtering, and enhanced metadata logging (Git commit, duration, detailed metrics).
- **CLI Management**: A `manage_experiments.py` script for listing, cleaning, and deleting experiments with powerful filters.
- **Reproducibility**: Strict dependency management via `.venv` and Git integration for tracking codebase state per experiment.

---

## 2. Feature System Expansion

We expanded the feature space significantly to capture more market dynamics:

| Feature Set | Count | Description |
|:---|---:|:---|
| **Technical** | 35 | Standard indicators (RSI, MACD, BB, SMA crosses, etc.) |
| **Volume** | 15 | OBV, Volume SMA, Volume Volatility, Price-Volume Correlation |
| **Market Structure** | 12 | Distance from Highs/Lows, Regime detection (Bull/Bear) |
| **On-chain** | 20 | SOPR (STH/LTH), MVRV, Exchange Flows (Simulated/Real) |
| **Sentiment** | 5 | Fear & Greed Index (proxies), Social Volume |
| **Flow** | 10 | CVD (Cumulative Volume Delta), Buying Pressure |
| **Lag & Rolling** | 240+ | Rolling stats (mean, std, min, max) for key indicators over multiple windows |

**Total Features**: Increased from **77** (Legacy) to **340+** (FcstLabPro v2).

---

## 3. Key Experiment Findings

We conducted a comparative analysis between the legacy-style baseline and the new expanded feature set.

### Experiments Compared
1.  **`baseline_T14_X8` (v1)**:
    -   **Features**: 77 (Technical + Volume only).
    -   **Model**: LightGBM (500 estimators).
    -   **Strategy**: Reversal Label (14d window, 8% threshold).
2.  **`baseline_v2_quick` (v2)**:
    -   **Features**: 340+ (All 7 feature sets).
    -   **Model**: LightGBM (200 estimators - "Quick" run).
    -   **Strategy**: Reversal Label (14d window, 8% threshold).

### Performance Metrics

| Metric | Baseline v1 (77 feats) | Baseline v2 (340 feats) | Change |
|:---|:---:|:---:|:---:|
| **Accuracy** | **37.45%** | 35.09% | 📉 -2.4% |
| **F1 Macro** | **0.3546** | 0.3193 | 📉 -0.035 |
| **Cohen Kappa** | **0.0466** | -0.0130 | 📉 -0.059 |

### 💡 Insight & Analysis
- **Quality > Quantity?** The v1 baseline with fewer features performed better than the "quick" v2 run. This suggests that simply adding hundreds of features without careful selection or sufficient regularization/tuning can introduce noise.
- **Model Tuning**: The v2 run used fewer estimators (200 vs 500) for speed. It is likely that the model underfitted the complex 340-feature space.
- **Feature Importance Shift**:
    -   **v1 Top Features**: `sma_cross_50_200`, `low_50d_dist`, `vol_volatility_20`.
    -   **v2 Top Features**: `sth_sopr_std30` (On-chain), `rsi_14_std30`, `buy_pressure_std30` (Flow).
    -   **New Signals**: The model *did* pick up on new feature sets (On-chain and Flow) as important, finding distinct signals that were not present in v1.

---

## 4. Recommendations & Future Work

Based on the current state, the following roadmap is recommended:

### short-term (Optimization)
1.  **Feature Selection**: Run a recursive feature elimination (RFE) or permutation importance experiment to prune the 340 features down to the most effective ~50-100.
2.  **Full Training**: Run `baseline_v2` with full hyperparameters (`n_estimators=1000+`, lower learning rate) to see if the complex feature set shines with more compute.
3.  **Hyperparameter Tuning**: Use the `param_tuning` category to optimize LightGBM parameters for the new feature sets.

### Long-term (Expansion)
1.  **Ensemble Methods**: Implement Stacking or Voting classifiers combining XGBoost, CatBoost, and Random Forests (classes already exist in code).
2.  **Real Data Integration**: Connect the `download_onchain.py` scripts to live APIs (Glassnode/CryptoQuant) for production inference.
3.  **Deep Learning**: Explore LSTM/Transformer models using the sequence data prepared by the `LagRolling` feature generator.

---

## 5. Deliverables

- **Codebase**: Full Python source in `src/`.
- **Configs**: YAML configurations for all experiment stages in `configs/`.
- **Reports**: Detailed markdown reports in `reports/`.
- **Registry**: JSON registry of all experiments in `experiments/registry.json`.

**Status**: ✅ Platform Ready for Advanced Research.
