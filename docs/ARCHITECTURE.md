# System Architecture

## Project Overview

The **SDR-Based Cognitive Radio System** is an intelligent wireless communication platform that dynamically adapts modulation scheme and transmission channel based on real-time channel condition sensing. The system implements a cost-aware hybrid controller that balances throughput, packet delivery, availability, and switching overhead.

**Key Capabilities:**
- Multi-channel sensing (three independent SDR receivers)
- Adaptive modulation (BPSK, QPSK, 16-QAM)
- Channel switching with cost-aware decision making
- Offline machine-learning performance analysis
- GNU Radio workflow integration
- Physical SDR hardware (RTL-SDR and PlutoSDR)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA SOURCES                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  Channel 1   │  │  Channel 2   │  │  Channel 3   │  │  Offline     │   │
│  │  (RTL-SDR)   │  │  (Pluto SDR) │  │  (RTL-SDR)   │  │  Dataset     │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SIGNAL GENERATION & RECEPTION                       │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐ │
│  │  Waveform Generator  │  │  AWGN + Interference │  │  SNR Estimation     │ │
│  │  (BPSK/QPSK/16-QAM)  │  │  (AWGN)              │  │  (3-channel)        │ │
│  └──────────────────────┘  └──────────────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      COGNITIVE CONTROL & DECISION MAKING                    │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │  Fixed Strategy  │  │  Adaptive        │  │  Channel         │          │
│  │                  │  │  Modulation      │  │  Switching       │          │
│  ├──────────────────┤  ├──────────────────┤  ├──────────────────┤          │
│  │  Hybrid Strategy │  │  Reliability-    │  │  Cost-Aware      │          │
│  │                  │  │  Constrained     │  │  Hybrid (Cal.)   │          │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              RESULTS & ANALYSIS                             │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐ │
│  │  Multi-Seed Exp.    │  │  Statistical Analysis │  │  Offline ML Analysis│ │
│  │  (630 runs)         │  │  (Paired-seed t-tests)│  │  (LR + RF)         │ │
│  └──────────────────────┘  └──────────────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            OUTPUT & VISUALIZATION                           │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐ │
│  │  CSVs (raw data)    │  │  CSV summary tables   │  │  PNG plots          │ │
│  └──────────────────────┘  └──────────────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

### 1. Signal Generation (`src/radio/waveform_generator.py`)
- Generates BPSK, QPSK, 16-QAM waveforms
- RRC pulse shaping with configurable roll-off
- Symbol timing and upsampling

### 2. Channel Model (`src/channel_model.py`)
- Three-channel model with AR(1) process
- AWGN and interference generation
- SNR control and channel quality variation
- Burst interference simulation

### 3. Cognitive Controller (`src/controller_cost_aware.py`)
- Cost-aware hybrid strategy
- Calibrated logistic regression models
- Decision logging and strategy execution
- Dwell-time enforcement

### 4. Metrics Calculation (`src/metrics.py`)
- Packet Delivery Ratio (PDR)
- Throughput calculation
- Availability estimation
- Switching count and overhead

### 5. Multi-Seed Experiment (`src/multi_seed_experiment.py`)
- 630-run experiment generator
- 30 seeds × 3 environments × 7 strategies
- Results aggregation and CSV output

### 6. Statistical Analysis (`src/paired_seed_analysis.py`)
- Paired t-tests across seeds
- 95% confidence intervals
- Strategy comparison table

### 7. Offline ML Analysis (`src/ml_analysis.py`)
- Linear Regression baseline
- Random Forest regressor
- Feature importance and permutation importance
- R², MAE, RMSE evaluation

### 8. GNU Radio Integration
- Flowgraph: `gnuradio/joint_cognitive_radio.grc`
- SNR estimation and channel quality measurement
- Controller integration via message ports

---

## Data Flow

1. **Configuration:** Seeds, environments, strategies defined
2. **Experiment:** For each seed × environment × strategy:
   - Generate signal
   - Apply channel impairments
   - Run controller decision loop
   - Record metrics
3. **Aggregation:** CSV output with 630 rows
4. **Analysis:** Paired-seed statistics
5. **ML:** Feature engineering + model training
6. **Reports:** Tables and plots generation
7. **Documentation:** Results and methodology

---

## Controller Decision Flow

```
┌──────────────┐
│  Measure SNR │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Check dwell  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Cost         │
│ calculation  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Switch?      │
└──────┬───────┘
       │
       ├── No → Remain on current channel
       │
       ▼ Yes
┌──────────────┐
│ Apply cost   │
│ model →     │
│ choose new   │
│ modulation   │
└──────────────┘
```

---

## SDR Hardware Integration

- **RTL-SDR** (Realtek RTL2838/R820T): USB receiver, 500/501/502 MHz
- **PlutoSDR** (ADALM-Pluto, AD9363A): Network receiver, 192.168.2.1
- Both operate in receive-only mode (no RF transmission enabled)
- Dual-sensor experiments measure IQ signals from both devices

---

## Directory Structure

```
cognitive-radio/
├── archive/
│   └── experimental-equalization/   # Deprecated equalizer work
├── docs/
│   ├── ARCHITECTURE.md              # This file
│   ├── METHODOLOGY.md
│   ├── RESULTS_AND_DISCUSSION.md
│   ├── LIMITATIONS.md
│   ├── DEMO_GUIDE.md
│   └── [existing docs]
├── results/
│   ├── calibrated_multi_seed_results.csv
│   ├── decision_trace.csv
│   ├── dual_sensor_measurements.csv
│   ├── dual_sensor_decisions.csv
│   ├── final_experiment_metrics.csv
│   ├── figures/
│   └── final/
│       ├── plots/
│       └── tables/
├── src/
│   ├── channel_model.py
│   ├── controller_cost_aware.py
│   ├── controller.py
│   ├── metrics.py
│   ├── simulate.py
│   ├── multi_seed_experiment.py
│   ├── paired_seed_analysis.py
│   ├── ml_analysis.py
│   └── radio/                       # SDR hardware wrappers
├── tests/
│   └── test_*.py                    # 110 unit tests
├── gnuradio/
│   └── joint_cognitive_radio.grc
└── results/final/execution_log.md
```
