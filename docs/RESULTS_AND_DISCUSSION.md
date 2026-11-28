# Results and Discussion

## Executive Summary

The cognitive radio system was implemented, validated in simulation and GNU Radio, and its physical layer was tested over the air with an ADALM-Pluto transmitter and an RTL-SDR receiver at 866 MHz. A 630-run multi-seed experiment (30 seeds × 3 environments × 7 strategies) shows the calibrated hybrid strategy has the highest throughput in all interference environments while keeping PDR ≥ 0.99. Over the air, measured BER for BPSK, QPSK and 16-QAM follows AWGN theory within about 1 dB, confirming the controller's modulation thresholds. With the loop closed on the radios (28 Nov, 5 sessions), the controller was on the best of three real channels in 72 of 72 rounds, switching exactly when needed and adapting the modulation; channel quality in that demo was set by TX power, not real interference. A CNN modulation classifier trained only on simulated data recognised the modulation in 98.5 % of real OTA windows. The controller's lead holds across switching penalties and under a realistic 1 dB hardware loss. 382 tests pass.

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

### 4.3 Closed-loop channel switching on the radios (28 Nov)
Each round: BPSK probe on 865.7 / 866.5 / 867.3 MHz → RTL-SDR Es/N0 per channel → unchanged `CalibratedCognitiveController` → data burst (2 frames, 2,048 bits) on the chosen channel and modulation. Channel quality scripted by Pluto TX attenuation in five phases (A–C: a different channel best; D: all mediocre; E: all poor), three rounds each; antennas 1.5 m apart (`scripts/run_channel_switching_demo.py`).

| Session | Margin | Switches needed / made / unnecessary | Best channel | Data bit errors |
|------|------|------|------|------|
| 07:17 (A–D) | 0 dB | 3 / 3 / 0 | 12 / 12 | 75 / 24,576 |
| 07:41 | 0 dB | 3 / 3 / 0 | 15 / 15 | 83 / 30,720 |
| 07:43 | 2 dB | 3 / 3 / 0 | 15 / 15 | 48 / 29,696 |
| 07:48 | 0 dB | 3 / 3 / 0 | 15 / 15 | 26 / 30,720 |
| 07:51 | 2 dB | 3 / 3 / 0 | 15 / 15 | 10 / 30,720 |
| **All** | | **15 / 15 / 0** | **72 / 72** (95 % CI 0.95–1.00) | 242 / 146,432 |

| Modulation | Margin | Bit errors | BER (95 % CI) | Mean data Es/N0 | AWGN theory |
|------|------|------|------|------|------|
| BPSK | 0 dB | 101 / 12,288 | 8.2e-3 (6.7e-3–1.0e-2) | 5.5 dB | 5.6e-3 |
| QPSK | 0 dB | 10 / 18,432 | 5.4e-4 (2.6e-4–1.0e-3) | 11.0 dB | 3.0e-4 |
| 16-QAM | 0 dB | 73 / 55,296 | 1.3e-3 (1.0e-3–1.7e-3) | 19.5 dB | 1.0e-4 |
| BPSK | 2 dB | 53 / 23,552 | 2.3e-3 (1.7e-3–2.9e-3) | 8.5 dB | 7.9e-4 |
| QPSK | 2 dB | 0 / 8,192 | < 4.5e-4 | 18.1 dB | ≈ 0 |
| 16-QAM | 2 dB | 5 / 28,672 | 1.7e-4 (5.7e-5–4.1e-4) | 19.4 dB | 2.7e-5 |

- **Switching:** correct channel every round; every needed switch in the first round after the change; none unnecessary despite 1–3 dB round-to-round probe variation.
- **16-QAM errors come from short dips:** 15 of 143 data frames were more than 3 dB (up to 8.5 dB) below the other frame of their burst; they hold 68 of the 78 16-QAM errors. The decision is made on the probe, a few seconds earlier.
- **Safety margin (2 dB):** more robust modulations near the cut-offs, about 20 % lower throughput (2.5 vs 3.1 bits/symbol). The lower BER cannot be attributed to the margin: the link drifted by about 3 dB between sessions, and the two later no-margin sessions had no 16-QAM errors.
- **Audit** (`scripts/verify_closed_loop_captures.py`): all 288 raw captures re-decode to exactly the logged values; every Pluto readback matches its burst; replaying the logged probes reproduces all 72 decisions.
- **Band scan** (`scripts/scan_band.py`, receive only): all three channels within 0.6 dB of the band floor, no wideband activity in 90 sweeps. Without the scripted TX power the channels would have looked the same.

Outputs: `results/hardware/closed_loop/`, `results/analysis/closed_loop_*`, `results/figures/closed_loop_repeatability.png`, `results/figures/closed_loop_real_session.png`, `results/hardware/band_scan/`.

### 4.4 Deep-learning modulation classifier
A 1-D CNN (85,859 parameters) trained on 24,000 synthetic windows passed through a simulated RTL-SDR chain, tested on the 536 payload windows of the 19 real OTA captures: **98.5 % per window (capture-level bootstrap 95 % CI 96.2–99.8 %), 97.4 % per frame, 19/19 captures**; a cumulant + random-forest baseline reaches 62.9 %. Errors occur only at Es/N0 ≤ 7.2 dB, all with confidence < 0.9; every window above 0.9 confidence is correct. An unseen frame format (BPSK v2) gives 36/36; one damaged frame (8.8 % BER) is called 16-QAM with 0.99 confidence. Outputs: `results/dl/`.

---

### 4.5 Sensitivity and robustness (simulation)
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

**What the three channels are:** each is the same 1 kHz test tone with its own Gaussian noise source and a scaled interference term at the same frequency. They differ in noise / interference level only, not in frequency, so this experiment tests the controller's decision logic, not RF channels (point raised in faculty review). Switching between real RF channels is in section 4.3.

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

1. **Closed loop on the radios uses scripted channel quality** (TX power), not real interference, fading or other users; one room, 1.5 m, about 35 minutes. The GNU Radio software-in-the-loop channels differ only in noise level.
2. **One OTA BER session**, one antenna arrangement, separation not recorded; each BER point is one capture of 4,096 bits.
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
- ✅ Closed-loop channel switching on the radios: best of three real channels in 72 / 72 rounds over 5 sessions, every switch when needed and none without reason, modulation adapted 16-QAM → BPSK (channel quality scripted by TX power)
- ✅ A random forest that explains the benchmark (R² 0.997 throughput, 0.985 PDR)
- ✅ A CNN that recognises the modulation of real OTA signals (98.5 %) after training only on simulation
- ✅ The controller's lead holds across switching penalties and under a realistic 1 dB hardware loss (with a matching safety margin)
- ✅ 382 tests pass
