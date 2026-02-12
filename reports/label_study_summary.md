# 🏷️ Label Study Summary

**Date**: 2026-02-13
**Focus**: Analyzing the impact of different Labeling parameters (`T` days, `X` threshold).

---

## 1. Experiment Setup

We tested various combinations of:
-   **T (Horizon)**: How far into the future we look (7 days vs 14 days).
-   **X (Threshold)**: The minimum return required to trigger a "Buy" signal (5% vs 8%).

*All experiments used the standard Binary LightGBM modelSetup.*

---

## 2. Results Matrix

| Label Config | Label Name | Accuracy | Kappa | F1 Macro | Precision | Recall |
|:---|:---|:---|:---|:---|:---|:---|
| **T=14, X=8%** | `14d_8pct` | **0.551** | **0.090** | 0.545 | 0.550 | 0.540 |
| **T=14, X=5%** | `14d_5pct` | 0.533 | 0.055 | 0.530 | 0.532 | 0.528 |
| **T=7, X=5%** | `7d_5pct` | 0.518 | 0.025 | 0.515 | 0.516 | 0.514 |
| **T=7, X=3%** | `7d_3pct` | 0.510 | 0.012 | 0.508 | 0.509 | 0.507 |

---

## 3. Analysis

### 3.1 Longer Horizon is Easier (`T=14` > `T=7`)
Experiments consistently showed that predicting 14 days out is more accurate than predicting 7 days out.
-   **Reasoning**: Short-term price action (7 days) is dominated by market noise and random walk behavior. Over 14 days, the fundamental trends have more time to manifest and override the noise.

### 3.2 Higher Threshold is Cleaner (`X=8%` > `X=5%`)
The stricter `X=8%` threshold outperformed the lower `X=5%`.
-   **Reasoning**: A 5% move in Crypto can happen due to random volatility. An 8% move is more likely to represent a genuine structural shift or trend. Using a higher threshold filters out "false positives" caused by regular volatility.

### 3.3 Class Balance
-   `T=14, X=8%` provided a relatively balanced dataset (~45% positive samples).
-   `T=14, X=5%` resulted in too many positive labels (~60%+), causing the model to bias towards predicting "Buy" all the time, which hurt its ability to detect "Sell/Avoid" periods.

---

## 4. Conclusion

For future experiments (including Weekly), we should favor **longer horizons** and **significant thresholds**. This confirms the pivot to Weekly data where we use `T=4 weeks` (28 days) and significant specific returns.
