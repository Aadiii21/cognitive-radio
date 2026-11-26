# Results and Discussion

## Executive Summary

The cognitive radio system was implemented, validated in simulation and GNU Radio, and its physical layer was tested over the air with an ADALM-Pluto transmitter and an RTL-SDR receiver at 866 MHz. A 630-run multi-seed experiment (30 seeds × 3 environments × 7 strategies) shows the calibrated hybrid strategy has the highest throughput in all interference environments while keeping PDR ≥ 0.99. Over the air, measured BER for BPSK, QPSK and 16-QAM follows AWGN theory within about 1 dB, confirming the controller's modulation thresholds. A CNN modulation classifier trained only on simulated data recognised the modulation in 98.5 % of real OTA windows. The controller's lead holds across switching penalties and under a realistic 1 dB hardware loss. 355 tests pass.

The part reports in `docs/reports/` give the full detail; this document is the summary.

---

## 1. Strategy Comparison

All values are means over 30 seeds, computed from `results/calibrated_multi_seed_results.csv` (630 runs, regenerated 25 Nov 2026; the 22 Nov tables in `docs/archive/` did not match the CSV).

### 1.1 Throughput by Environment (bits per step)

| Strategy | Low | Medium | High |
|----------|-----|--------|------|
| Fixed | 2.000 | 1.980 | 1.644 |
| Adaptive Modulation | 3.760 | 3.086 | 2.296 |
| Channel Switching | 2.000 | 1.970 | 1.752 |
| Hybrid | 3.760 | 2.957 | 2.192 |
| Reliability-Constrained | 2.122 | 1.875 | 1.481 |
| Cost-Aware Hybrid | 3.760 | 2.972 | 2.224 |
| **Calibrated Hybrid** | **3.999** | **3.684** | **2.986** |

**Key finding:** The calibrated hybrid has the highest throughput in every environment: 3.999 vs 2.000 for fixed QPSK at low interference (+100 %), 3.684 vs 3.086 for the best non-switching strategy (AMC) at medium, and 2.986 vs 2.296 at high.

### 1.2 Packet Delivery Ratio by Environment

| Strategy | Low | Medium | High |
|----------|-----|--------|------|
| Fixed | 1.000 | 0.990 | 0.822 |
| Adaptive Modulation | 1.000 | 0.997 | 0.880 |
| Channel Switching | 1.000 | 1.000 | 0.981 |
| Hybrid | 1.000 | 1.000 | 0.988 |
| Reliability-Constrained | 1.000 | 1.000 | 0.988 |
| Cost-Aware Hybrid | 1.000 | 1.000 | 0.988 |
| **Calibrated Hybrid** | 1.000 | 0.999 | 0.991 |

**Key finding:** Staying on one channel loses packets as interference grows (fixed: 0.822 at high). Every switching strategy keeps PDR at or above 0.98.

### 1.3 Availability by Environment

| Strategy | Low | Medium | High |
|----------|-----|--------|------|
| Fixed | 1.000 | 1.000 | 1.000 |
| Adaptive Modulation | 1.000 | 1.000 | 1.000 |
| Channel Switching | 1.000 | 0.985 | 0.893 |
| Hybrid | 1.000 | 0.928 | 0.796 |
| Reliability-Constrained | 0.999 | 0.918 | 0.809 |
| Cost-Aware Hybrid | 1.000 | 0.939 | 0.819 |
| **Calibrated Hybrid** | 1.000 | 0.933 | 0.825 |

Availability falls for the switching strategies because transmission stops for two steps during each handoff.

### 1.4 Switching Overhead by Environment (switches per 5,000-step run)

| Strategy | Low | Medium | High |
|----------|-----|--------|------|
| Fixed | 0.0 | 0.0 | 0.0 |
| Adaptive Modulation | 0.0 | 0.0 | 0.0 |
| Channel Switching | 0.0 | 37.2 | 266.6 |
| Hybrid | 0.3 | 181.1 | 509.2 |
| Reliability-Constrained | 3.0 | 206.1 | 478.1 |
| Cost-Aware Hybrid | 0.0 | 151.6 | 452.1 |
| **Calibrated Hybrid** | 0.5 | 167.1 | 436.6 |

The cost-aware switching rule cuts handoffs relative to the plain hybrid (medium: 151.6 vs 181.1; high: 452.1 vs 509.2). The calibrated hybrid's switch count differs from the cost-aware hybrid because its calibrated success curves change which channel has the higher utility.

---

## 2. Statistical Analysis (Paired-Seed t-Tests)

All results are 95% paired t-confidence intervals across 30 seeds.

### 2.1 Low Interference

| Comparison | ΔThroughput | 95% CI | Significant? |
|------------|-------------|--------|--------------|
| Calibrated vs Hybrid | +0.239 | [0.230, 0.248] | Yes |
| Calibrated vs Channel Switching | +1.999 | [1.999, 2.000] | Yes |
| Calibrated vs Fixed | +1.999 | [1.999, 2.000] | Yes |

### 2.2 Medium Interference

| Comparison | ΔThroughput | 95% CI | Significant? |
|------------|-------------|--------|--------------|
| Calibrated vs Hybrid | +0.727 | [0.714, 0.740] | Yes |
| Calibrated vs Adaptive Modulation | +0.598 | [0.586, 0.610] | Yes |
| Calibrated vs Fixed | +1.704 | [1.696, 1.713] | Yes |

### 2.3 High Interference

| Comparison | ΔThroughput | 95% CI | Significant? |
|------------|-------------|--------|--------------|
| Calibrated vs Hybrid | +0.795 | [0.781, 0.809] | Yes |
| Calibrated vs Adaptive | +0.690 | [0.672, 0.708] | Yes |
| Calibrated vs Fixed | +1.342 | [1.327, 1.357] | Yes |

**Conclusion:** The calibrated hybrid strategy is statistically superior to all other strategies in all environments.

---

## 3. Machine Learning Analysis

### 3.1 Model Comparison (Random Forest Test Set)

| Metric | Throughput (Baseline) | Throughput (LR) | Throughput (RF) | PDR (Baseline) | PDR (LR) | PDR (RF) |
|--------|----------------------|-----------------|-----------------|----------------|----------|----------|
| R² | -0.000 | 0.924 | **0.997** | -0.000 | 0.543 | **0.985** |
| MAE | 0.728 | 0.176 | **0.029** | 0.025 | 0.024 | **0.002** |
| RMSE | 0.801 | 0.220 | **0.045** | 0.045 | 0.030 | **0.006** |

### 3.2 Feature Importance (Random Forest - Throughput)

| Rank | Feature | Importance |
|------|---------|------------|
| 1 | environment_Low | 0.36 |
| 2 | reliability_constrained strategy | 0.21 |
| 3 | channel_switching | 0.19 |
| ... | ... | ... |

**Conclusion:** Random Forest models R² > 0.98 across all environments, with strong generalization.

---

## 4. Hardware Validation

### 4.1 Receive-only sensing (14–22 Nov)
Both the RTL-SDR and the ADALM-Pluto captured IQ, produced SNR measurements and drove controller decisions on three channels at 500, 501 and 502 MHz, repeated five times per sensor (`results/hardware_stability/`).

### 4.2 Over-the-air link (23 Nov)
Pluto TX (pyadi-iio, cyclic buffer, 2.083 MS/s) → antennas → RTL-SDR RX (2.048 MS/s, gain 28 dB), 866 MHz. Antenna separation was not recorded.

| Test | Result |
|------|--------|
| Tone (TX on vs off) | Detected at all levels (25.0 / 40.4 / 49.5 dB bin ratio at Pluto attenuation 30 / 20 / 10 dB); RTL frequency offset −10.4 kHz (−12 ppm) |
| BPSK frame v2, att 10 dB | 4/4 frames, 0/2,048 bit errors, Es/N0 13.7–15.3 dB |
| BPSK/QPSK/16-QAM sweep, att 0–20 dB (15 runs) + 4 runs | All 76 frames detected; exact 95 % CIs contain theory in 4 of 9 runs with errors, the rest slightly worse; implied loss −0.2 to +0.75 dB above 4 dB Es/N0; 16-QAM 1.2e-3 (CI 4.0e-4–2.8e-3) at 17.1 dB, QPSK error-free at 11–23 dB, BPSK 2.4e-4 at 7.7 dB |

Table and figure: `results/analysis/hardware_ber_runs.csv`, `results/figures/hardware_ber_vs_theory.png` (`scripts/summarize_hardware_sweep.py`). The runs were started with `--rf-path conducted`; the records carry an `rf_path_correction` (actual: OTA).

### 4.3 Deep-learning modulation classifier
A 1-D CNN (85,859 parameters) trained on 24,000 synthetic windows passed through a simulated RTL-SDR chain, tested on the 536 payload windows of the 19 real OTA captures: **98.5 % per window (capture-level bootstrap 95 % CI 96.2–99.8 %), 97.4 % per frame, 19/19 captures**; a cumulant + random-forest baseline reaches 62.9 %. Errors occur only at Es/N0 ≤ 7.2 dB, all with confidence < 0.9; every window above 0.9 confidence is correct. An unseen frame format (BPSK v2) gives 36/36; one damaged frame (8.8 % BER) is called 16-QAM with 0.99 confidence. Outputs: `results/dl/`.

---

### 4.4 Sensitivity and robustness (simulation)
`scripts/sensitivity_analysis.py` reproduces all 630 benchmark runs exactly, then:

| Study | Result |
|-------|--------|
| Switching penalty 0–0.6 | Calibrated hybrid's worst setting beats the cost-aware hybrid's best in every environment. 0.25 beats the benchmark's 0.15 (High: throughput 3.028 vs 2.986, availability 0.903 vs 0.825, switches 242 vs 437, PDR 0.990 vs 0.991). At 0.6 it never switches and High PDR drops to 0.876 |
| 1 dB implementation loss (controllers unaware) | Calibrated hybrid still highest throughput (Medium 3.575, High 2.812 vs AMC 3.085, 2.282) but PDR 0.969 / 0.933 |
| 1 dB loss + 1 dB safety margin | Throughput 3.600 / 2.877, PDR 0.997 / 0.988 |
| 2 dB loss + 2 dB margin | Throughput 3.477 / 2.702, PDR 0.996 / 0.981 |

Outputs: `results/sensitivity/`.

---

## 5. GNU Radio Workflow Validation

### 5.1 Flowgraph
- `gnuradio/joint_cognitive_radio.grc`
- Three-channel generation
- Independent SNR estimation per channel
- Controller integration

### 5.2 Validation
- `test_gnuradio_adapter.py`: 4/4 tests pass
- Three-channel signal generation verified
- Independent SNR estimation verified
- Channel quality measurements verified
- Controller integration verified

---

## 6. Receiver Synchronization

### 6.1 CFO Correction
- 540 trials validated
- 0 timing errors up to ±2 kHz
- CFO MAE < 0.01 Hz

### 6.2 SRO Correction
- 300 trials validated
- 0 timing errors at ≤20 PPM
- SRO MAE: 0.38-0.77 PPM

### 6.3 Combined Validation
- 390 trials
- 12/13 test cases PASS
- Edge case: cfo1500_sro20 @ 5 dB BPSK (1 failure)

---

## 7. Multipath Characterization

### 7.1 Validation Results
- 1,800 trials completed
- Channel: two-path, configurable echo amplitude and delay
- SNR: 5, 10, 15 dB
- Echo amplitudes: 0.1, 0.3, 0.5, 0.7
- Echo delays: 1, 2, 4, 8, 16 samples

### 7.2 Limitations
- Short-delay multipath (2- and 4-sample echoes with amplitude ≥ 0.5) breaks timing correlation in about 50 % of trials; 1-, 8- and 16-sample echoes do not
- Overall timing failure rate: 20% (between conditions)

---

## 8. Known Limitations

1. **Controller evaluated in simulation only.** The hardware closed loop (controller driving the radios) was removed from scope on 23 Nov; the OTA work is open-loop.
2. **One OTA session**, one antenna arrangement, separation not recorded; each BER point is one capture of 4,096 bits.
3. **Calibration from GNU Radio's synthetic AWGN channel**, valid only inside the measured noise range.
4. **Short-delay multipath** (2–4 sample echoes, amplitude ≥ 0.5) breaks timing; no equaliser.
5. **SRO > 20 ppm** may need a higher-order timing-drift model.
6. **ML is offline**: the random forest describes the benchmark; the CNN classifies modulation but is not used by the controller.

See `docs/LIMITATIONS.md` for the full list.

---

## 9. Conclusion

The project demonstrates:
- ✅ A calibrated, cost-aware controller with the highest throughput of seven strategies in all three interference environments (630 runs, paired 95 % CIs exclude zero)
- ✅ Packet-success and SNR calibrations measured with a GNU Radio receiver (2,070 + 1,530 trials)
- ✅ Validated synchronisation (CFO, SRO) and characterised multipath limits
- ✅ An over-the-air Pluto → RTL-SDR link at 866 MHz with BPSK, QPSK and 16-QAM BER matching theory and confirming the switching thresholds
- ✅ A random forest that explains the benchmark (R² 0.997 throughput, 0.985 PDR)
- ✅ A CNN that recognises the modulation of real OTA signals (98.5 %) after training only on simulation
- ✅ The controller's lead holds across switching penalties and under a realistic 1 dB hardware loss (with a matching safety margin)
- ✅ 355 tests pass
