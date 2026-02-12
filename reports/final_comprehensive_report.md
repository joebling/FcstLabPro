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

We conducted extensive experiments ranging from infrastructure verification to deep daily optimization and weekly strategy exploration.

### 3.1 Phase 1: Infrastructure & Baseline Comparison
We first validated the new v2 infrastructure by comparing the legacy-style baseline against the new expanded feature set.

#### Experiments Compared
1.  **`baseline_T14_X8` (v1)**:
    -   **Features**: 77 (Technical + Volume only).
    -   **Model**: LightGBM (500 estimators).
    -   **Strategy**: Reversal Label (14d window, 8% threshold).
2.  **`baseline_v2_quick` (v2)**:
    -   **Features**: 340+ (All 7 feature sets).
    -   **Model**: LightGBM (200 estimators - "Quick" run).
    -   **Strategy**: Reversal Label (14d window, 8% threshold).

#### Performance Metrics (v1 vs v2)

| Metric | Baseline v1 (77 feats) | Baseline v2 (340 feats) | Change |
|:---|:---:|:---:|:---:|
| **Accuracy** | **37.45%** | 35.09% | 📉 -2.4% |
| **F1 Macro** | **0.3546** | 0.3193 | 📉 -0.035 |
| **Cohen Kappa** | **0.0466** | -0.0130 | 📉 -0.059 |

**Insight**: The initial v2 run ("quick") underperformed due to noise from unselected features and reduced model estimators, prompting the need for the optimizations seen in Phase 2.

---

### 3.2 Phase 2: Daily Optimization Loop (Daily)

We iteratively optimized the daily prediction models, moving from multi-class to binary classification, selecting features, and tuning parameters.

| Stage | Experiment | Accuracy | Kappa | Improvement/Notes |
|:---|:---|:---|:---|:---|
| **Initial baseline** | `baseline_T14_X8` (3-class) | 0.375 | 0.047 | Legacy benchmark |
| **Label Optimization** | `binary_T14_X8` | 0.527 | 0.042 | **Accuracy +40%** (Switch to Binary) |
| **Feature Selection** | `top30_binary` | 0.541 | 0.064 | **Kappa +52%** (Reduced noise) |
| **Param Tuning** | `conservative` | **0.551** | **0.090** | **Kappa +41%** (Best Daily Model) |
| **On-chain Data** | `onchain_enhanced` | 0.546 | 0.081 | No immediate gain vs. technicals |
| **Model Comparison** | XGBoost/CatBoost/RF | 0.531-0.540 | 0.051-0.069 | LightGBM remains SOTA |
| **Ensemble** | Voting/Stacking | 0.541-0.547 | 0.071-0.082 | Complexity did not yield significant ROI |

**Key Takeaway**: Complex features (On-chain/Ensemble) struggled to beat a well-tuned, feature-selected LightGBM on Daily data.

---

### 3.3 Phase 3: Weekly Prediction Breakthrough (Weekly) 🌟

shifting focus to a Weekly horizon proved to be a major breakthrough, yielding the highest stability and signal quality.

| Experiment | Label | Features | Accuracy | Kappa | F1 Macro |
|:---|:---|:---|:---|:---|:---|
| `weekly_T4_X5` | T4, X5% | All | 0.571 | 0.127 | 0.564 |
| `weekly_T4_X8` | T4, X8% | All | 0.548 | 0.083 | 0.537 |
| `weekly_T3_X5` | T3, X5% | All | 0.565 | 0.116 | 0.558 |
| `weekly_T2_X3` | T2, X3% | All | 0.548 | 0.082 | 0.535 |
| `weekly_conservative` | T4, X5% + Opt | All | 0.569 | 0.124 | 0.562 |
| `weekly_enhanced` | T4, X5% + Ext | All + Onchain | 0.554 | 0.096 | 0.545 |
| `weekly_refined_top25` | **T4, X5% + Top25** | **25** | **0.576** | **0.138** | **0.570** |
| `weekly_top15` | T4, X5% + Top15 | 15 | 0.564 | 0.113 | 0.556 |

**Breakthrough**: The `weekly_refined_top25` experiment achieved the project's highest scores (**Accuracy 57.6%, Kappa 0.138**), validating that weekly trends are cleaner and more predictable than daily noise.

---

### 3.4 Supplementary Analysis Reports

Detailed breakdowns of specific study areas can be found in the `reports/` directory:

-   📄 **`phase2_summary.md`**: Comprehensive summary of the Daily optimization phase.
-   📄 **`label_study_summary.md`**: Analysis of different labeling parameters (T14 vs T7, X5 vs X8).
-   📄 **`feature_study_summary.md`**: Deep dive into feature importance and selection (Top 30 vs Full).
-   📄 **`derivatives_analysis.md`**: Specific analysis of utilizing derivatives data (Funding Rates, CVD).
-   📄 **`diagnostic_analysis.md`**: Model diagnostic checks and error analysis.
-   📄 **`compare_baseline_...md`**: The initial v1 vs v2 detailed comparison.

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
