# 📊 Phase 2 Summary: Daily Optimization Loop

**Date**: 2026-02-13
**Scope**: Daily Prediction Models (24h timeframe data)
**Goal**: Improve upon the Baseline v1 performance through iterative optimization.

---

## 1. Overview of Experiments

In Phase 2, we moved from the initial infrastructure validation to aggressively optimizing the model for Daily data. We tested hypothesis across Label definitions, Feature Selection, and Model Tuning.

| Stage | Experiment ID | Accuracy | Kappa | Change vs Prev | Key Action |
|:---|:---|:---|:---|:---|:---|
| **1. Baseline** | `baseline_T14_X8` | 0.375 | 0.047 | - | Initial Multi-class (3-class) setup. |
| **2. Label Opt** | `binary_T14_X8` | **0.527** | 0.042 | Acc +40% | Switched to **Binary Classification** (0/1). |
| **3. Feat Select**| `top30_binary` | 0.541 | 0.064 | Kappa +52% | Reduced features from 340+ to **Top 30**. |
| **4. Tuning** | `conservative` | **0.551** | **0.090** | Kappa +41% | Tuned parameters to reduce overfitting. |
| **5. Enhanced** | `onchain_enhanced`| 0.546 | 0.081 | - | Added On-chain/Derivative features. |
| **6. Model** | `xgboost/catboost`| 0.531 | 0.051 | - | Tested alternative algorithms. |

---

## 2. Key Insights

### 2.1 The "Binary" Switch
Transitioning from a 3-class problem (Buy/Sell/Hold) to a Binary problem (Signal/No-Signal) provided the largest jump in raw Accuracy (37.5% -> 52.7%).
-   The 3-class model struggled significantly to distinguish "Hold" from the other classes.
-   Binary classification simplified the decision boundary.

### 2.2 Less is More (Feature Selection)
The `top30_binary` experiment significantly outperformed the full feature set (Kappa 0.064 vs 0.042).
-   **Finding**: The 340+ feature set contains significant noise for Daily predictions.
-   **Action**: Using only the most predictive features (mostly volatility and technicals) improved signal stability.

### 2.3 Overfitting is the Enemy
The `conservative` experiment, which purposely used a lower learning rate and constrained tree depth, achieved the **best Daily performance (Kappa 0.090)**.
-   This confirms that financial time-series data is extremely noisy, and flexible models (like default LightGBM) tend to memorize noise rather than learn patterns.

### 2.4 Advanced Features & Models
-   **On-chain Data**: Did not yield immediate improvements for Daily trading (`onchain_enhanced` performed slightly worse than `conservative`). On-chain metrics likely move too slowly for daily precision.
-   **XGBoost/CatBoost**: LightGBM outperformed both in this specific setup, likely due to its better handling of the specific feature distribution or the limited sample size.

---

## 3. Conclusion for Phase 2

While we squeezed significant performance out of the Daily models (Kappa 0.047 -> 0.090), the ceiling remained low. This difficulty in predicting Daily price action led to the strategic pivot in **Phase 3** (Weekly Predictions), which ultimately unlocked much higher performance.
