# ⚡ Derivatives Analysis

**Date**: 2026-02-13
**Focus**: Investigating the predictive power of Futures Market data (Funding Rates, Open Interest, CVD).

---

## 1. Hypothesis
Derivatives markets often lead spot markets. We hypothesized that:
1.  **Positive Funding Rate** -> Overheated (Bearish signal?)
2.  **Rising Open Interest (OI)** -> Impending volatility.
3.  **CVD Divergence** -> Smart money accumulating/distributing.

---

## 2. Experiments & Findings

### 2.1 Funding Rate
-   **Observation**: Extreme funding rates (very high positive or negative) are mean-reverting.
-   **Signal**: `funding_rate_rolling_mean_30` showed weak correlation with future direction (Corr: 0.02).
-   **Result**: Not a strong primary predictor for *price direction*, but good for regime detection.

### 2.2 Open Interest (OI)
-   **Observation**: High OI usually precedes a "flush" (rapid price move).
-   **Signal**: `oi_change_pct` was useful for predicting *volatility*, but not *direction*.
-   **Result**: Helpful for risk management, less so for profit targeting.

### 2.3 Cumulative Volume Delta (CVD)
-   **Hypothesis**: Spot CVD > Futures CVD implies genuine demand.
-   **Feature**: `cvd_divergence` (Spot CVD - Perp CVD).
-   **Result**: This was the **most promising derivatives feature**.
    -   When Spot buying > Perp buying, price tended to rise over T+7 days.
    -   It ranked in the Top 40 features in the v2 baseline.

---

## 3. Implementation Challenges

-   **Data Quality**: Historical derivatives data (especially prior to 2020) is sparse and often noisy across exchanges.
-   **Stationarity**: Interpreting raw OI is difficult as the market cap grows. We had to normalize OI by Market Cap (`oi_ratio`), which improved performance.

## 4. Conclusion

Derivatives data adds value, but specifically the **Flow/CVD** components, not the headline "Funding Rate". Future work should focus on **Exchange Flows** (Stablecoin inflows) rather than just Funding/OI.
