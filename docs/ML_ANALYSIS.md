# Offline ML Analysis of Cognitive Radio Experiments

**Date:** November 22, 2026  
**Dataset:** `results/calibrated_multi_seed_results.csv` (630 runs, 30 seeds, 3 environments, 7 strategies)

---

## 1. Dataset Audit Summary

| Property | Value |
|----------|-------|
| Rows | 630 |
| Columns | 8 |
| Missing values | 0 |
| Duplicates | 0 |
| Environments | Low (210), Medium (210), High (210) |
| Strategies | 7 × 90 runs each |
| Seeds | 30 (2026–2055) |
| Target: throughput | mean=2.595, std=0.799, range=[1.415, 4.000] |
| Target: PDR | mean=0.982, std=0.044, range=[0.794, 1.000] |

### Features Available Before Experiment (Used as Predictors)
- **environment** (categorical): Low / Medium / High interference
- **strategy** (categorical): fixed, adaptive_modulation, channel_switching, hybrid, reliability_constrained, cost_aware_hybrid, calibrated_hybrid

### Targets (Measured After Experiment)
- **throughput_bits_per_step** — normalized throughput
- **packet_delivery_ratio** — PDR

### Excluded from Features (Post-Experiment Metrics)
- `service_availability`, `switches`, `attempted_packets` — these are outcomes, not predictors

### Data Leakage Prevention
- **Seed-grouped split**: `GroupShuffleSplit` with `groups=seed` ensures no seed appears in both train and test
- 24 seeds train / 6 seeds test (80/20 split)
- Categorical encoding: OneHotEncoder with `drop="first"`

---

## 2. Model Configurations

### Linear Regression (Baseline ML)
```python
Pipeline([
    ("preprocessor", ColumnTransformer([
        ("cat", OneHotEncoder(drop="first", sparse_output=False), ["environment", "strategy"])
    ])),
    ("scaler", StandardScaler(with_mean=False)),
    ("model", LinearRegression())
])
```

### Random Forest Regressor (Nonlinear Model)
```python
Pipeline([
    ("preprocessor", ColumnTransformer([
        ("cat", OneHotEncoder(drop="first", sparse_output=False), ["environment", "strategy"])
    ])),
    ("model", RandomForestRegressor(
        n_estimators=500,
        max_depth=10,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1
    ))
])
```

### Baseline Predictor
- Mean of training target (no features)

---

## 3. Evaluation Results

### Overall Test Set Performance (6 held-out seeds)

| Target | Model | MAE | RMSE | R² |
|--------|-------|-----|------|-----|
| **Throughput** | Baseline (mean) | 0.728 | 0.801 | -0.000 |
| | Linear Regression | 0.176 | 0.220 | **0.924** |
| | **Random Forest** | **0.029** | **0.045** | **0.997** |
| **PDR** | Baseline (mean) | 0.025 | 0.045 | -0.000 |
| | Linear Regression | 0.024 | 0.030 | 0.543 |
| | **Random Forest** | **0.002** | **0.006** | **0.985** |

**Key Findings:**
- Random Forest achieves near-perfect prediction for both targets (R² > 0.98)
- Linear Regression is strong for throughput (R² = 0.92) but weak for PDR (R² = 0.54)
- PDR is harder to predict linearly because it saturates at 1.0 for most strategies

---

## 4. Feature Importance (Permutation, Random Forest)

### Throughput Prediction
| Rank | Feature | Importance (MAE Δ) | Std |
|------|---------|-------------------|-----|
| 1 | environment_Low | 0.360 | 0.035 |
| 2 | strategy_reliability_constrained | 0.211 | 0.023 |
| 3 | strategy_channel_switching | 0.193 | 0.023 |
| 4 | strategy_calibrated_hybrid | 0.188 | 0.025 |
| 5 | strategy_fixed | 0.186 | 0.021 |
| 6 | environment_Medium | 0.176 | 0.020 |
| 7 | strategy_hybrid | 0.017 | 0.004 |
| 8 | strategy_cost_aware_hybrid | 0.013 | 0.006 |

**Interpretation:** Low interference environment and strategies with high switching (reliability_constrained, channel_switching, calibrated_hybrid) are most informative for throughput. The reference categories (environment_High, strategy_adaptive_modulation) have zero importance by construction of `drop="first"`.

### PDR Prediction
| Rank | Feature | Importance (MAE Δ) | Std |
|------|---------|-------------------|-----|
| 1 | environment_Low | 0.0167 | 0.0022 |
| 2 | environment_Medium | 0.0155 | 0.0023 |
| 3 | strategy_fixed | 0.0078 | 0.0018 |
| 4 | strategy_hybrid | 0.0054 | 0.0008 |
| 5 | strategy_calibrated_hybrid | 0.0052 | 0.0010 |
| 6 | strategy_reliability_constrained | 0.0050 | 0.0012 |
| 7 | strategy_cost_aware_hybrid | 0.0049 | 0.0010 |
| 8 | strategy_channel_switching | 0.0049 | 0.0007 |

**Interpretation:** Environment dominates PDR prediction. The fixed strategy has lower PDR in high interference, making it distinguishable.

---

## 5. Performance by Interference Environment

### Throughput R² by Environment (Test Seeds)

| Environment | Linear Regression | Random Forest |
|-------------|-------------------|---------------|
| Low | 0.899 | **0.9998** |
| Medium | 0.994 | **0.996** |
| High | 0.715 | **0.981** |

### PDR R² by Environment (Test Seeds)

| Environment | Linear Regression | Random Forest |
|-------------|-------------------|---------------|
| Low | 0.000* | 0.000* |
| Medium | -36.8* | **0.859** |
| High | 0.561 | **0.979** |

*Low PDR variance (all near 1.0) makes R² unstable. Medium Linear Regression shows negative R² due to saturation effects.

**Key Finding:** Random Forest maintains high performance across all environments. Linear Regression degrades significantly in High interference for throughput and fails for PDR in Low/Medium.

---

## 6. Residual Analysis

- **Throughput (RF)**: Residuals centered near zero, no obvious pattern — model captures nonlinear interactions well
- **Throughput (LR)**: Systematic under/over-prediction at extremes — linear model misses strategy×environment interactions
- **PDR (RF)**: Residuals very small, slight heteroscedasticity near PDR=1.0
- **PDR (LR)**: Large residuals for fixed strategy in High interference — cannot model saturation

---

## 7. Files Generated

| File | Description |
|------|-------------|
| `results/ml/dataset_audit.json` | Complete dataset audit |
| `results/ml/model_comparison.csv` | All model metrics |
| `results/ml/performance_by_environment.csv` | Stratified R²/MAE/RMSE |
| `results/ml/feature_importance_throughput_bits_per_step.csv` | Permutation importance |
| `results/ml/feature_importance_packet_delivery_ratio.csv` | Permutation importance |
| `results/ml/linear_regression_results_throughput_bits_per_step.csv` | LR actual vs predicted |
| `results/ml/linear_regression_results_packet_delivery_ratio.csv` | LR actual vs predicted |
| `results/ml/random_forest_results_throughput_bits_per_step.csv` | RF actual vs predicted |
| `results/ml/random_forest_results_packet_delivery_ratio.csv` | RF actual vs predicted |
| `results/ml/plots/throughput_bits_per_step_actual_vs_predicted.png` | 3-panel actual vs predicted |
| `results/ml/plots/throughput_bits_per_step_residuals.png` | LR & RF residuals |
| `results/ml/plots/throughput_bits_per_step_feature_importance.png` | Bar chart |
| `results/ml/plots/packet_delivery_ratio_actual_vs_predicted.png` | 3-panel actual vs predicted |
| `results/ml/plots/packet_delivery_ratio_residuals.png` | LR & RF residuals |
| `results/ml/plots/packet_delivery_ratio_feature_importance.png` | Bar chart |
| `results/ml/plots/r2_by_environment.png` | R² grouped bar chart |

---

## 8. Reproducible Execution

```bash
cd /home/deamon/projects/cognitive-radio
PYTHONPATH=. /usr/bin/python3 src/ml_analysis.py
```

Requires: pandas, scikit-learn, matplotlib, seaborn (installed via system Python)

---

## 9. Limitations

1. **Small test set**: Only 6 seeds (42 samples) held out — confidence intervals would be wide
2. **Saturated targets**: PDR ≈ 1.0 for most strategies in Low/Medium → low variance, unstable R²
3. **Categorical only**: No continuous SNR or channel-state features available in this dataset
4. **No causal claims**: Feature importance ≠ causal effect; Random Forest captures predictive associations
5. **Single split**: Results depend on the 6 seeds chosen; cross-validation over seeds would be more robust
6. **Reference category bias**: OneHotEncoder `drop="first"` makes adaptive_modulation / High environment the reference — importance values are relative to these

---

## 10. Conclusions

1. **Random Forest is highly effective** for predicting both throughput (R²=0.997) and PDR (R²=0.985) from just environment + strategy
2. **Environment is the dominant predictor** — interference level determines the performance ceiling
3. **Strategy matters most for throughput differentiation** — calibrated_hybrid achieves highest throughput by correctly identifying when 16-QAM is viable
4. **Linear Regression is adequate for throughput** (R²=0.92) but **fails for PDR** due to ceiling effects
5. **Offline ML validates experimental design** — the factors we controlled (environment, strategy) explain nearly all variance in outcomes

**This analysis confirms the cognitive radio experiments are well-structured and the performance differences between strategies are predictable from the experimental conditions alone.**

---

*ML/DL remains an offline analysis component. No ML model is integrated into the real-time cognitive controller.*