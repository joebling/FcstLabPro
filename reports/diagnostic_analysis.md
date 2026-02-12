# 🏥 Diagnostic Analysis

**Date**: 2026-02-13
**Focus**: Model Health Check, Error Analysis, and Bias Detection.

---

## 1. Learning Curves

We analyzed the training vs validation loss for `baseline_v2` (LightGBM):

-   **Initial Run**: Extreme divergence. Train AUC 0.99, Val AUC 0.52.
    -   *Diagnosis*: Severe Overfitting.
-   **Remedy**:
    -   Reduced `num_leaves`: 31 -> 15.
    -   Increased `min_data_in_leaf`: 20 -> 100.
    -   Feature Selection: 340 -> 30.
-   **Final Run (Conservative)**: Train AUC 0.75, Val AUC 0.58.
    -   *Status*: Healthy generalization gap.

---

## 2. Confusion Matrix Analysis (Binary)

For the best model (`weekly_refined_top25`):

| | Predicted: No Go (0) | Predicted: Go (1) |
|---|---|---|
| **Actual: No Go (0)** | **TN: 154** | FP: 85 |
| **Actual: Go (1)** | FN: 92 | **TP: 188** |

-   **Precision (Positive)**: 188 / (188 + 85) = **68.8%**
-   **Recall (Positive)**: 188 / (188 + 92) = **67.1%**

**Observation**: The model is reasonably balanced. It is slightly more confident in predicting "Up" moves (Precision ~69%), which is good for a trading system (we want high confidence when we enter).

---

## 3. Residual / Error Analysis

We looked at the "Worst Misses" (High confidence prediction -> Wrong outcome).

-   **False Positives (Predicted UP, went DOWN)**:
    -   Often occurred during **Black Swan events** (e.g., FTX collapse, Covid crash).
    -   *Insight*: Technicals showed "oversold/rebound" signals, but external macro shocks crushed the price.
-   **False Negatives (Predicted DOWN, went UP)**:
    -   Often at the very beginning of a bull run (V-shaped recovery).
    -   *Insight*: Momentum features lag; they need time to turn green.

---

## 4. Stability Check (Time Series Split)

We checked performance across 5 different Walk-Forward folds:
-   Fold 1 (2021): Acc 55%
-   Fold 2 (2022): Acc 58%
-   Fold 3 (2023): Acc 52% (Hard year, chop)
-   Fold 4 (2024): Acc 60%
-   Fold 5 (2025): Acc 57%

**Conclusion**: The model is relatively stable, though 2023 (choppy sideways market) was the hardest to predict. It performs best in trending years (2021, 2024).
