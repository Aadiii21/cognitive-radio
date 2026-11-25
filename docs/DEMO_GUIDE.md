# Demo Guide

> **Status (25 Nov 2026):** this document is a historical record of the demo guide written for the receive-only stage; it is kept unchanged below. Final state: the over-the-air Pluto → RTL-SDR link was tested on 23 Nov (BPSK/QPSK/16-QAM BER matches theory), a DL modulation classifier was added (98.5 % on real OTA captures), and the hardware closed loop was removed from scope. Current documents: `MASTER_README.md`, `docs/RESULTS_AND_DISCUSSION.md`, `docs/LIMITATIONS.md` and the reports in `docs/reports/`.

This guide provides exact commands to run the final demonstration of the SDR-Based Cognitive Radio System.

---

## 1. Prerequisites

### Software Requirements
- Python 3.10+
- GNU Radio 3.10.x
- libiio 0.26 (for PlutoSDR)
- NumPy, SciPy, Pandas, Matplotlib, Scikit-learn

### Hardware Requirements
- **RTL-SDR** (Realtek RTL2838/R820T) - optional
- **ADALM-Pluto** (AD9363A) - optional
- No RF transmission required for software demonstration
- No RF transmission required for hardware receive-only demonstration

### No special Python packages required beyond standard installation

---

## 2. Software-Only Demonstration

Run the complete demonstration without any physical SDR devices:

```bash
cd /home/deamon/projects/cognitive-radio
PYTHONPATH=. /usr/bin/python3 src/multi_seed_experiment.py \
  --seeds 30 \
  --environments low medium high \
  --strategies fixed adaptive_modulation channel_switching hybrid reliability_constrained cost_aware_hybrid calibrated_hybrid \
  --output results/calibrated_multi_seed_results.csv
```

**Expected output:** 630 rows in results/calibrated_multi_seed_results.csv

---

## 3. Five-Minute Smoke Test

If you just want to verify the system works quickly:

```bash
cd /home/deamon/projects/cognitive-radio
PYTHONPATH=. /usr/bin/python3 -m pytest tests/ -q
PYTHONPATH=. /usr/bin/python3 src/paired_seed_analysis.py
```

**Expected output:** 110 unit tests pass, statistics printed

---

## 4. Hardware Receive-Only Demonstration

If you have physical SDR devices, run the receive-only demonstration:

### Required Hardware
- RTL-SDR (Realtek RTL2838/R820T) connected via USB
- ADALM-Pluto (AD9363A) with IP 192.168.2.1

### Setup
1. Connect RTL-SDR via USB
2. Configure PlutoSDR network: `ip:192.168.2.1`
3. Run the receive-only demo:

```bash
cd /home/deamon/projects/cognitive-radio
PYTHONPATH=. /usr/bin/python3 src/hardware_dual_sensor.py
```

### Expected Output
- RTL-SDR captures at approximately 5 dB SNR
- PlutoSDR captures at approximately 8 dB SNR
- Dual-sensor measurements and decisions generated

### Troubleshooting
- **Device not found:** Check USB connection and `lsusb`
- **Pluto not found:** Check network configuration and `ping 192.168.2.1`
- **No capture:** Ensure GNU Radio 3.10.x and libiio 0.26 are installed

---

## 5. Generate Final Plots

```bash
cd /home/deamon/projects/cognitive-radio
PYTHONPATH=. /usr/bin/python3 -c "
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

df = pd.read_csv('results/calibrated_multi_seed_results.csv')
strategies = ['fixed', 'adaptive_modulation', 'channel_switching', 'hybrid', 'reliability_constrained', 'cost_aware_hybrid', 'calibrated_hybrid']
colors = plt.cm.tab10(np.linspace(0, 1, len(strategies)))

# Strategy comparison
fig, ax = plt.subplots(figsize=(10, 6))
x = np.arange(len(strategies))
width = 0.25
throughput = [df[df['strategy']==s]['throughput_bits_per_step'].mean() for s in strategies]
pdr = [df[df['strategy']==s]['packet_delivery_ratio'].mean() for s in strategies]
ax.bar(x - width/2, throughput, width, label='Throughput', color=colors)
ax.bar(x + width/2, pdr, width, label='PDR', color=colors)
ax.set_xlabel('Strategy')
ax.set_ylabel('Score')
ax.set_title('Strategy Comparison: Throughput vs PDR')
ax.set_xticks(x)
ax.set_xticklabels(strategies, rotation=30, ha='right')
ax.legend()
plt.tight_layout()
plt.savefig('results/final/plots/strategy_comparison.png', dpi=150)
plt.close()

# Additional plots...
print('Plots generated')
"
```

---

## 6. Run Complete Validation

```bash
cd /home/deamon/projects/cognitive-radio
PYTHONPATH=. /usr/bin/python3 -m pytest tests/ -q
PYTHONPATH=. /usr/bin/python3 src/paired_seed_analysis.py
PYTHONPATH=. /usr/bin/python3 src/ml_analysis.py
```

---

## 7. Documentation Files

| Document | Location |
|----------|----------|
| README.md | `README.md` |
| Architecture | `docs/ARCHITECTURE.md` |
| Methodology | `docs/METHODOLOGY.md` |
| Results | `docs/RESULTS_AND_DISCUSSION.md` |
| Limitations | `docs/LIMITATIONS.md` |
| Demo Guide | `docs/DEMO_GUIDE.md` |
| HR Files | `docs/EXTENDED_SYNC_VALIDATION.md`, `docs/MULTIPATH_VALIDATION.md`, `docs/ML_ANALYSIS.md`, `docs/IMPLEMENTATION_STATUS.md` |

---

## 8. Expected Results Summary

| Metric | Value |
|--------|-------|
| Unit Tests | 110/110 passing |
| Multi-Seed Runs | 630 (30 seeds × 3 environments × 7 strategies) |
| Best Strategy | Calibrated Hybrid (highest throughput, 100% PDR) |
| ML Model | Random Forest R² ≈ 0.997 for throughput |
| Hardware | RTL-SDR and PlutoSDR operational (receive-only) |
| GNU Radio | Workflow validated |

---

## 9. Key Commands

### Run all tests
```bash
cd /home/deamon/projects/cognitive-radio && PYTHONPATH=. /usr/bin/python3 -m pytest tests/ -q
```

### Run multi-seed experiment
```bash
cd /home/deamon/projects/cognitive-radio && PYTHONPATH=. /usr/bin/python3 src/multi_seed_experiment.py
```

### Run paired-seed analysis
```bash
cd /home/deamon/projects/cognitive-radio && PYTHONPATH=. /usr/bin/python3 src/paired_seed_analysis.py
```

### Run ML analysis
```bash
cd /home/deamon/projects/cognitive-radio && PYTHONPATH=. /usr/bin/python3 src/ml_analysis.py
```

### Generate final plots
```bash
cd /home/deamon/projects/cognitive-radio && python3 scripts/make_final_plots.py
```

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|----------|-------|-----|
| Tests fail to import | PYTHONPATH not set | Use `PYTHONPATH=.` prefix |
| No SDR device found | Driver/hardware issue | Check `lsusb` and `ping 192.168.2.1` |
| GNU Radio error | Version mismatch | Use GNU Radio 3.10.x |
| ML plot fails | Missing matplotlib | Install via `pip install matplotlib` |
| Plots missing | Plot generation failed | Check `results/final/plots/` directory |

---

## 11. Demo Flow

1. **Run tests:** Verify functionality (5 seconds)
2. **Run multi-seed experiment:** Generate 630 results (2 minutes)
3. **Run paired-seed analysis:** Statistical comparison (10 seconds)
4. **Run ML analysis:** Model training and evaluation (30 seconds)
5. **Generate plots:** Visualizations (10 seconds)
6. **Show results:** Strategy comparison, ML model, hardware status
