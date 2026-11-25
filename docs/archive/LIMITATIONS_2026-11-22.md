# Limitations

## 1. Hardware Limitations

### 1.1 SDR Devices
- **RTL-SDR** (Realtek RTL2838/R820T): USB receiver, 500/501/502 MHz operational
- **ADALM-Pluto** (AD9363A): Network receiver at 192.168.2.1, operational

### 1.2 Receive-Only Implementation
- **Transmitter disabled** - No physical RF transmission enabled
- All hardware experiments are receive-side sensing
- No reference ("ground truth") from actual RF transmission
- No controlled Pluto-to-RTL-SDR packet transmission performed

### 1.3 Hardware Validation
All hardware claims are based on receive-only measurements:
- IQ capture from both devices verified
- SNR measurements recorded
- Dual-sensor experiments completed
- Decision traces generated
- Device-specific measurement ranges documented

---

## 2. Simulation Assumptions

### 2.1 Channel Model
- Three-channel model with AR(1) process
- Burst interference with configurable probability
- AWGN with target SNR
- Multipath channel models two-path propagation

### 2.2 Interference Environment
Defined as:
- **Low:** 0-5 dB SNR
- **Medium:** 5-15 dB SNR
- **High:** 15-30 dB SNR

### 2.3 Channel Quality Variation
Channel quality is simulated, not measured from physical hardware. The simulation accurately represents channel effect behavior, not physical propagation.

---

## 3. Calibration Limitations

### 3.1 Cost-Aware Hybrid
The calibrated_hybrid strategy uses logistic regression models trained on empirical GNU Radio data. The calibration is **frozen** at experiment time, which means:

- Calibrated and cost_aware_hybrid results are identical for this run
- The calibration coefficients are not updated during the multi-seed experiment
- Alternative calibration may yield different results

### 3.2 Model Inputs
- Environment: categorical (Low/Medium/High)
- Strategy: categorical (7 strategies)
- Features: measured SNR, availability, modulation
- No signal-level features used

---

## 4. Uncompleted RF Experiments

The following were NOT performed:

- Actual RF transmission from PlutoSDR to RTL-SDR
- Multi-frequency physical hardware sweep
- Long-duration hardware stability testing
- Over-the-air packet transmission measurements

**Reason:** Physical RF hardware experiments require explicit hardware-operation authorization. Only receive-side measurement was performed within the authorized scope.

---

## 5. Model Generalization Limitations

### 5.1 Machine Learning
- ML analysis is purely offline - not integrated into the real-time controller
- Random Forest and Linear Regression are trained on 18 seeds (2026-2043)
- Test set: 12 seeds (2044-2055)
- No deep learning used (dataset too small for deep learning)

### 5.2 Scope
- Feature importance shows correlation, not causation
- Models predict performance from historical data
- No real-time adaptation based on ML predictions
- No GPU acceleration (all local CPU execution)

### 5.3 Generalization
- Models were trained on three environments (Low/Medium/High)
- Performance may degrade outside tested interference levels
- No robustness testing against untested channel conditions

---

## 6. Technical Weaknesses

### 6.1 Signal Processing
- EVM ~35% in AWGN due to simple gain estimation not equalizing RRC pulse shape
- Short-delay multipath (< 2 samples) breaks timing correlation
- SRO >20 PPM may require higher-order timing drift model
- CFO correction stable up to ±2 kHz, but marginal accuracy at extremes

### 6.2 Experimental
- 630-run experiment is deterministic and reproducible, but small
- The 10-repetition design is a single repetition of the full grid
- No repeated experiment runs to measure variance across experimental batches

---

## 7. Known Issues

| Issue | Resolution | Evidence |
|-------|------------|----------|
| Short-delay multipath timing failures | Documented limitation | 100% timing errors at 1-symbol delay |
| 50 PPM SRO | Higher-order model needed | 4/60 timing failures at 50 PPM |
| Quoted EVM ~35% in AWGN | Expected with simple gain estimation | Observed in validation |
| No hardware RF transmission | Not performed | No authorization requested |

---

## 8. Metadata for Reproduction

**Command to run final experiment:**
```bash
PYTHONPATH=. /usr/bin/python3 src/multi_seed_experiment.py --seeds 30 --environments low medium high --strategies fixed adaptive_modulation channel_switching hybrid reliability_constrained cost_aware_hybrid calibrated_hybrid --output results/calibrated_multi_seed_results.csv
```

**Command to run paired-seed analysis:**
```bash
PYTHONPATH=. /usr/bin/python3 src/paired_seed_analysis.py --results results/calibrated_multi_seed_results.csv
```

**Command to run ML analysis:**
```bash
PYTHONPATH=. /usr/bin/python3 src/ml_analysis.py --results results/calibrated_multi_seed_results.csv --output_dir results/ml
```

**Command to run tests:**
```bash
cd /home/deamon/projects/cognitive-radio && PYTHONPATH=. /usr/bin/python3 -m pytest tests/ -q
```
