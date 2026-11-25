# Methodology

## Experimental Design

This section documents the complete experimental methodology for the SDR-Based Cognitive Radio System, including channel models, modulation schemes, controller strategies, performance metrics, and statistical evaluation.

---

## 1. Project Assumptions

- **Hardware:** RTL-SDR (Realtek RTL2838/R820T) and ADALM-Pluto (AD9363A)
- **GNU Radio:** Version 3.10.x
- **libiio:** Version 0.26
- **Python:** 3.10+
- **Data:** Simulated channel experiments and offline ML analysis
- **Hardware:** Receive-only (no RF transmission)

---

## 2. Channel Models

### 2.1 Three-Channel Model

The system models three independent communication channels, each with its own signal quality characteristics:

```
Channel states: Low (bad) | Medium | High (good)
SNR ranges:  0-5 dB | 5-15 dB | 15-30 dB
```

Each channel is modeled with:
- AR(1) fading process with configurable volatility
- Burst interference with configurable probability
- AWGN with target SNR dependent on modulation

### 2.2 Multipath Channel

The multipath channel model implements a two-path channel:

```
y[n] = x[n] + a * exp(j*phi) * x[n-d] + w[n]
```

Where:
- `x[n]`: Direct-path signal
- `a`: Echo amplitude (0.1, 0.3, 0.5, 0.7)
- `phi`: Echo phase (random per trial)
- `d`: Echo delay (1, 2, 4, 8, 16 samples)
- `w[n]`: AWGN

**Validation:** 1,800 trials (4 amplitudes × 5 delays × 3 modulations × 3 SNRs × 10 repetitions)

### 2.3 SNR Estimation

SNR is estimated using reference signal correlation:
1. Generate known preamble/reference
2. Correlate received signal with reference
3. Estimate noise power from residual
4. Compute SNR = signal_power / noise_power

---

## 3. Modulation Schemes

### 3.1 BPSK (Binary Phase Shift Keying)

- 1 symbol = 1 bit
- Constellation: {-1, +1}
- Symbol mapping: 0 → -1, 1 → +1
- BER at SNR 10 dB: ~1e-5
- Throughput efficiency: 1 bit/step

### 3.2 QPSK (Quadrature Phase Shift Keying)

- 1 symbol = 2 bits
- Constellation: {±1±j}/√2
- Gray-coded symbol mapping
- BER at SNR 10 dB: ~1e-5
- Throughput efficiency: 2 bits/step

### 3.3 16-QAM

- 1 symbol = 4 bits
- Constellation: {±1±j}×{1,3}·1/√10
- Gray-coded 2D mapping
- BER at SNR 10 dB: ~1e-4
- Throughput efficiency: 4 bits/step

### 3.4 Modulation Selection Logic

The adaptive modulation strategy selects the highest-order modulation that meets:
- Target PDR: 0.99 (default)
- Current SNR estimate

---

## 4. Controller Strategies

### 4.1 Fixed Strategy

Maintains the same modulation and channel throughout the entire experiment. No adaptation occurs.

### 4.2 Adaptive Modulation

Adaptively selects the best modulation for the current channel SNR, subject to PDR constraints.

### 4.3 Channel Switching

Switches between available channels to find the best signal quality, without changing modulation.

### 4.4 Hybrid Strategy

Combines adaptive modulation and channel switching. Modulates on the current channel quality, switches to a better channel if available.

### 4.5 Reliability-Constrained Strategy

Adaptive modulation with a stricter PDR threshold, limiting modulation changes to maintain reliability.

### 4.6 Cost-Aware Hybrid (Calibrated)

A calibrated version of the hybrid strategy using:
- Logistic regression models trained on empirical GNU Radio data
- Cost function: switching_cost + (1 - expected_pdr) × penalty_weight
- Dwell-time enforcement to prevent rapid switching
- Channel penalty and modulation penalty weights tuned experimentally

### 4.7 Comparison

| Strategy | Switch Count (Low) | Switch Count (High) | Throughput (Low) | Throughput (High) | PDR (High) |
|----------|-------------------|---------------------|------------------|-------------------|------------|
| Fixed | 0 | 0 | 2.000 | 2.000 | 1.000 |
| Adaptive Modulation | 0 | 0 | 3.760 | 2.296 | 1.000 |
| Channel Switching | 0 | 0 | 2.000 | 2.000 | 1.000 |
| Hybrid | 3.00 | 72.60 | 3.711 | 2.796 | 1.000 |
| Reliability-Constrained | 3.00 | 478.13 | 2.122 | 1.481 | 0.988 |
| Cost-Aware Hybrid | 0.00 | -57.13 | 3.999 | 2.986 | 1.000 |
| **Calibrated Hybrid** | **0.00** | **-72.60** | **3.999** | **2.986** | **1.000** |

*(Cost-aware hybrid and calibrated hybrid have identical results due to calibration being frozen at the time of the multi-seed experiment.)*

---

## 5. Performance Metrics

### 5.1 Packet Delivery Ratio (PDR)

```
PDR = N_successful_packets / N_attempted_packets
```

PDR is bounded to [0, 1]. PDR = 1 means all packets were successfully received.

### 5.2 Throughput

```
Throughput = Σ (modulation_bits_per_symbol × successful_packets) / total_steps
```

Normalized to bits per step (max 4 for 16-QAM).

### 5.3 Service Availability

```
Availability = N_available_steps / N_total_steps
```

Fraction of steps where the channel was available for transmission.

### 5.4 Switching Count

Number of channel switches during the experiment.

### 5.5 Switching Overhead

```
Switching_Overhead = N_switches × switching_cost
```

Where switching_cost is a fixed penalty (default: 0.001) per switch.

### 5.6 Cost Function

```
Cost = switching_cost × N_switches + (1 - PDR) × penalty_weight
```

The cost-aware hybrid controller minimizes this cost function.

---

## 6. Seed-Grouped Train/Test Split

For machine learning analysis:
- **Train set:** 18 seeds (2026-2043)
- **Test set:** 12 seeds (2044-2055)

This ensures no data leakage between training and testing sets.

---

## 7. Statistical Methodology

### 7.1 Paired-Seed t-Tests

For each strategy pair and environment:
- Compute paired differences across 30 seeds
- Calculate mean difference and 95% confidence interval
- Positive differences favor the first strategy

### 7.2 Significance Threshold

Differences with 95% CI excluding zero are considered statistically significant.

---

## 8. Reproducibility

All experiments use:
- Fixed random seeds (30 seeds)
- Pre-generated reference waveforms
- Deterministic simulation logic
- Seed-grouped train/test split for ML

---

## 9. Limitations

- ML analysis is offline only, not integrated into the controller
- No GPU acceleration used (all local execution)
- Physical RF experiments are receive-only
- Hardware experiments limited to single frequencies
- Cost-aware hybrid uses frozen calibration
