# 🧬 Feature Study Summary

**Date**: 2026-02-13
**Focus**: Feature Importance Analysis & Selection Strategy

---

## 1. Feature Importance Ranking (Top 20)

Aggregated from the best performing models (`conservative` and `weekly_refined`).

| Rank | Feature Name | Category | Description | Importance (Gain) |
|:---|:---|:---|:---|:---|
| 1 | `sth_sopr_std30` | On-chain | Short-Term Holder SOPR Volatility (30d) | High |
| 2 | `rsi_14_std30` | Technical | RSI Volatility / Uncertainty | High |
| 3 | `sma_cross_50_200` | Technical | Golden/Death Cross status | High |
| 4 | `buy_pressure_std30` | Flow | Volatility of Buy/Sell volume imbalance | Med-High |
| 5 | `lth_sopr_ma30` | On-chain | Long-Term Holder Profitability Trend | Med-High |
| 6 | `dist_from_low_180d` | Mkt Struct | How far price is above 6-month lows | Medium |
| 7 | `vol_volatility_20` | Volume | Stability of trading volume | Medium |
| ... | ... | ... | ... | ... |

*(Full list available in experiment artifacts)*

---

## 2. Category Performance Analysis

### 🏆 Top Performers
1.  **Volatility Metrics (`_std`)**: Features measuring the *standard deviation* of other indicators (e.g., `rsi_std`, `sth_sopr_std`) consistently ranked highest.
    *   *Insight*: The model finds "change in stability" more predictive than the raw value itself.
2.  **Market Structure**: Distance from long-term highs/lows (`dist_from_low`) provides critical context on where we are in the cycle.
3.  **On-chain (SOPR)**: Profitability ratios for Short-Term Holders (STH-SOPR) are excellent at detecting local tops/bottoms.

### 📉 Underperformers
1.  **Raw Price/Volume**: Raw `close`, `volume` values are not stationary and confuse tree models.
2.  **Lag features (Raw)**: Simple lags (`close_lag_1`) added noise. Rolling stats (`close_rolling_std`) were much better.
3.  **Sentiment (Social)**: Social volume data was too noisy/sparse in this dataset to be effective.

---

## 3. Selection Strategy Impact

Comparing "All Features" (340) vs "Top 30":

-   **All Features**:
    -   Training Score: 99.9% (Overfit)
    -   Test Score: 52% (Random)
-   **Top 30**:
    -   Training Score: 65% (Healthy)
    -   Test Score: 55% (Predictive)

**Conclusion**: Massive feature reduction is **mandatory**. The logic "throw everything at the model" failed. We successfully used Recursive Feature Elimination (RFE) to isolate the signal.
