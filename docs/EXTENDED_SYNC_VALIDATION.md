# Extended Synchronization Validation Report

**Date:** November 22, 2026  
**Project:** SDR-Based Cognitive Radio System

---

## Executive Summary

Extended synchronization validation was performed to test the existing correlation-based timing recovery and reference-based SNR estimation pipeline under three new impairment categories:

1. **Sample Rate Offset (SRO)** — 0 to 50 PPM
2. **Multipath Fading** — 6 channel configurations
3. **Combined Impairments** — 10 test cases combining CFO, SRO, and multipath

**Key Finding:** The existing correlation-based timing synchronization **fails completely** under even mild SRO (≥5 PPM) and short-delay multipath (1 symbol). The reference-based SNR estimator treats all signal distortions (ISI, CFO rotation, SRO-induced misalignment) as noise, leading to large SNR estimation errors.

---

## Test Configurations

### Common Parameters
| Parameter | Value |
|-----------|-------|
| Modulations | BPSK, QPSK, 16-QAM |
| Target SNRs | 5, 10, 15 dB |
| Repetitions per condition | 20 (SRO/Multipath), 10 (Combined) |
| Symbols | 65,536 |
| Samples per symbol | 4 |
| RRC roll-off | 0.35 |
| Sample rate | 2.4 MSPS |
| Max timing delay | 256 samples |
| Random seeds | Controlled per modulation/repetition/SNR |

---

## 1. Sample Rate Offset (SRO) Validation

**Script:** `src/validate_sro_sync.py`  
**Results:** `results/synchronization/sro_validation_*.csv`  
**Trials:** 900 (3 mod × 20 rep × 3 SNR × 5 SRO)

### SRO Values Tested
| SRO (PPM) | Description |
|-----------|-------------|
| 0 | Baseline (ideal sample alignment) |
| 5 | ±5 PPM = ±12 Hz at 2.4 MSPS |
| 10 | ±10 PPM = ±24 Hz |
| 20 | ±20 PPM = ±48 Hz |
| 50 | ±50 PPM = ±120 Hz |

### Results Summary

| SRO (PPM) | Timing Errors (60 trials) | Mean SNR MAE (dB) | Max SNR Error (dB) |
|-----------|---------------------------|-------------------|---------------------|
| 0 | 0/60 | 0.008 | 0.037 |
| 5 | **60/60** | 2.57 | 4.69 |
| 10 | **60/60** | 4.80 | 7.86 |
| 20 | **60/60** | 9.53 | 13.62 |
| 50 | **60/60** | 19.86 | 24.45 |

### Observations
- **0 PPM**: Perfect timing recovery, SNR error < 0.04 dB (matches existing validation)
- **≥5 PPM**: **100% timing failure** — correlation peak shifts due to sample misalignment
- SNR error scales approximately linearly with SRO magnitude
- CFO-like rotation from SRO causes reference-based estimator to treat signal as noise

---

## 2. Multipath Fading Validation

**Script:** `src/validate_multipath_sync.py`  
**Results:** `results/synchronization/multipath_validation_*.csv`  
**Trials:** 1,080 (3 mod × 20 rep × 3 SNR × 6 configs)

### Multipath Configurations

| Config | Delays (samples) | Amplitudes | Phases | ISI Power |
|--------|------------------|------------|--------|-----------|
| awgn_only | [0] | [1.0] | [0] | 0% |
| two_path_short | [0, 4] | [1.0, 0.5] | [0, 0] | 20% |
| two_path_medium | [0, 16] | [1.0, 0.3] | [0, π/4] | 8.3% |
| two_path_long | [0, 64] | [1.0, 0.2] | [0, π/2] | 3.8% |
| three_path | [0, 8, 24] | [1.0, 0.4, 0.2] | [0, -π/6, π/3] | 20% |
| three_path_strong | [0, 4, 12] | [1.0, 0.7, 0.5] | [0, π/2, π] | 74% |

### Results Summary

| Config | Timing Errors (90 trials) | Mean SNR MAE (dB) | Max SNR Error (dB) | Mean EVM (%) |
|--------|---------------------------|-------------------|---------------------|--------------|
| awgn_only | 0/90 | 0.007 | 0.023 | 35.2 |
| two_path_short | **90/90** | 4.99 | 8.17 | 57.3 |
| two_path_medium | 0/90 | 3.43 | 5.95 | 48.6 |
| two_path_long | 0/90 | 1.96 | 3.63 | 41.9 |
| three_path | 0/90 | 5.47 | 8.76 | 60.5 |
| three_path_strong | 0/90 | 9.90 | 14.01 | 99.4 |

### Observations
- **Short-delay multipath (≤1 symbol)**: **100% timing failure** — correlation peak shifts to the stronger delayed path
- **Longer-delay multipath (≥4 symbols)**: Timing succeeds (main path correlation peak dominates)
- **SNR error correlates with ISI power**: Reference-based estimator treats ISI as noise
- **EVM is high even for AWGN** (35%): The simple channel gain estimation doesn't account for RRC pulse shape properly
- Three-path with strong echoes causes catastrophic SNR error (>10 dB)

---

## 3. Combined Impairment Validation

**Script:** `src/validate_combined_sync.py`  
**Results:** `results/synchronization/combined_validation_*.csv`  
**Trials:** 900 (3 mod × 10 rep × 3 SNR × 10 cases)

### Test Cases

| Case | CFO (Hz) | SRO (PPM) | Multipath |
|------|----------|-----------|-----------|
| awgn_only | 0 | 0 | none |
| cfo_only | 1500 | 0 | none |
| sro_only | 0 | 20 | none |
| multipath_mild | 0 | 0 | mild (2-path, 4 sym) |
| multipath_severe | 0 | 0 | severe (3-path, strong) |
| cfo_sro | 1000 | 10 | none |
| cfo_multipath_mild | 1000 | 0 | mild |
| sro_multipath_mild | 0 | 10 | mild |
| cfo_sro_multipath_mild | 500 | 5 | mild |
| all_moderate | 1000 | 20 | severe |

### Results Summary

| Case | Timing Errors (30 trials) | Mean SNR MAE (dB) | Pass Rate |
|------|---------------------------|-------------------|-----------|
| awgn_only | 0/90 | 0.008 | **PASS** |
| cfo_only | 30/90 | 52.6 | FAIL |
| sro_only | 30/90 | 9.53 | FAIL |
| multipath_mild | 0/90 | 3.43 | FAIL |
| multipath_severe | 0/90 | 7.14 | FAIL |
| cfo_sro | 30/90 | 52.1 | FAIL |
| cfo_multipath_mild | 30/90 | 52.3 | FAIL |
| sro_multipath_mild | 30/90 | 6.11 | FAIL |
| cfo_sro_multipath_mild | 30/90 | 52.1 | FAIL |
| all_moderate | 30/90 | 52.4 | FAIL |

### Observations
- **Only AWGN-only passes** — any single impairment beyond timing delay breaks the synchronization
- **CFO is catastrophic**: Even 1.5 kHz CFO causes ~50 dB SNR error because correlation-based timing fails completely
- **SRO is severe**: 20 PPM causes ~9.5 dB error and 100% timing failure
- **Mild multipath**: No timing errors but 3.4 dB SNR error (ISI treated as noise)
- **Combined impairments**: CFO dominates error; SRO + multipath adds timing failures

---

## Root Cause Analysis

The existing synchronization pipeline has fundamental limitations:

### 1. Correlation-Based Timing Detection
```python
correlation = correlate(received, reference, mode="valid", method="fft")
detected_delay = argmax(|correlation|)
```
- **Assumes**: Perfect sample alignment, no CFO, no multipath
- **Fails when**: SRO > 0 (correlation peak smears), CFO > 0 (rotation destroys correlation), short-delay multipath (stronger delayed path wins)

### 2. Reference-Based SNR Estimation
```python
gain = vdot(reference, aligned) / vdot(reference, reference)
residual = aligned - gain * reference
SNR = 10*log10(signal_power / noise_power)
```
- **Assumes**: `aligned = gain * reference + noise`
- **Fails when**: `aligned = gain * reference + ISI + CFO_rotation + noise`
- All distortions (ISI, CFO, SRO misalignment) are attributed to `noise_power`

### 3. EVM Calculation Issues
Even for AWGN-only, EVM ≈ 35% because:
- Channel gain estimation uses simple dot product
- Doesn't equalize the RRC pulse shape
- The "residual" includes pulse-shaping mismatch, not just noise

---

## Files Created

| File | Description |
|------|-------------|
| `src/validate_sro_sync.py` | SRO validation (0-50 PPM) |
| `src/validate_multipath_sync.py` | Multipath validation (6 configs) |
| `src/validate_combined_sync.py` | Combined impairment validation (10 cases) |
| `results/synchronization/sro_validation_*.csv` | SRO raw results |
| `results/synchronization/multipath_validation_*.csv` | Multipath raw results |
| `results/synchronization/combined_validation_*.csv` | Combined raw results |

---

## Reproduction Commands

```bash
cd /home/deamon/projects/cognitive-radio

# SRO validation (900 trials, ~2 min)
PYTHONPATH=. /usr/bin/python3 src/validate_sro_sync.py

# Multipath validation (1080 trials, ~2 min)
PYTHONPATH=. /usr/bin/python3 src/validate_multipath_sync.py

# Combined validation (900 trials, ~1 min)
PYTHONPATH=. /usr/bin/python3 src/validate_combined_sync.py
```

---

## Whether Existing Pipeline Needs Improvement

**YES — Critical improvements needed:**

### Priority 1: Timing Synchronization
- **Replace correlation-based timing** with:
  - Gardner TED (Timing Error Detector) for symbol-rate synchronization
  - Mueller-Muller TED for non-data-aided timing recovery
  - Works under SRO, CFO, multipath

### Priority 2: CFO Compensation
- **Add CFO estimation/correction before timing**:
  - Schmidl-Cox preamble-based CFO estimation
  - Decision-directed Costas loop for residual CFO
  - Works up to ±f_symbol/2

### Priority 3: SNR Estimation
- **Separate noise from distortion**:
  - Use equalized signal for SNR estimation
  - Measure residual after equalization, not after simple gain correction
  - Or use pilot-based SNR estimation on known subcarriers

### Priority 4: Equalization
- **Add linear equalizer** (ZF/MMSE) before SNR estimation:
  - Compensates multipath ISI
  - Reduces EVM from 35% → <5% in AWGN
  - Enables accurate SNR measurement in multipath

---

## Limitations of Current Validation

1. **Synthetic only** — No hardware validation of these impairments
2. **No packet-level evaluation** — SNR ≠ packet success under ISI/CFO
3. **Fixed reference** — Uses full waveform as preamble; real systems use shorter pilots
4. **No decision-directed loops** — Real receivers track continuously, not one-shot
5. **No channel coding** — FEC would mask some SNR degradation

---

## Conclusion

The existing synchronization pipeline (correlation timing + reference SNR) is **only valid for ideal AWGN channels with perfect sample alignment**. It fails completely under:

| Impairment | Threshold for Failure |
|------------|----------------------|
| SRO | ≥5 PPM |
| CFO | ≥100 Hz (estimated) |
| Short multipath | ≤1 symbol delay |
| Combined | Any single non-AWGN impairment |

**Recommendation:** Before any hardware transmission experiments, implement Gardner TED timing recovery and CFO compensation. The current pipeline will not work for real-world channels.