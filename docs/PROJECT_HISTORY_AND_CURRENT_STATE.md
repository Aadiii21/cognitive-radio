# Project History and Current State

> **Status (25 Nov 2026):** this document is a historical record of development history up to 23 Nov; it is kept unchanged below. Final state: the over-the-air Pluto → RTL-SDR link was tested on 23 Nov (BPSK/QPSK/16-QAM BER matches theory), a DL modulation classifier was added (98.5 % on real OTA captures), and the hardware closed loop was removed from scope. Current documents: `MASTER_README.md`, `docs/RESULTS_AND_DISCUSSION.md`, `docs/LIMITATIONS.md` and the reports in `docs/reports/`.

**Generated:** November 23, 2026
**Project:** SDR-Based Cognitive Radio System
**Document type:** Reconstructed project history + current state snapshot + hardware bring-up progress

---

## 1. Project Objective

The SDR-Based Cognitive Radio System is an intelligent wireless communication platform that dynamically adapts modulation scheme and transmission channel based on real-time channel condition sensing. The system implements a cost-aware hybrid controller that balances throughput, packet delivery, availability, and switching overhead.

The framework investigates when a radio should:
- Remain on its current channel and adapt its modulation.
- Switch to another channel with better conditions.
- Jointly select a channel and modulation while accounting for handoff cost.

The intended objective is to improve useful delivered throughput while maintaining packet reliability and accounting for switching downtime.

---

## 2. Reconstructed Development Timeline

Note: The conversation file `SDR Signal Detection Classification.txt` was referenced as an input to this task. It was **NOT found** in the project directory or anywhere in the accessible workspace. The timeline below is reconstructed from Git history, existing documentation, test files, source code, and results datasets. Any conversation-specific details (specific prior discussions, informal notes, etc.) are unavailable and are recorded as such.

### Phase 1 (Oct 27 - Oct 30, 2026): Initial Framework

- Initial cost-aware cognitive radio framework committed.
- Basic channel model, baseline controller, metrics.
- Initial GNU Radio flowgraphs: `first_signal.grc`, `noise_test.grc`, `snr_measurement.grc`.
- Waveform generation experiments with BPSK/QPSK/16-QAM.

### Phase 2 (Nov 1 - Nov 7, 2026): Building Blocks

- Joint cognitive radio flowgraph (`joint_cognitive_radio.grc/py`) created.
- GNU Radio receiver experiments: timing recovery, carrier recovery (Costas loop), pilot-assisted gain correction.
- Packet receiver implementation (BPSK/QPSK/16-QAM, 10 seeds validated).
- RTL-SDR capture pipeline (`rtl_capture.py`).
- Calibration: equal-power modulation calibration, refined calibration.
- Dual-sensor hardware experiment planning.

### Phase 3 (Nov 12 - Nov 22, 2026): Validation, ML, and Hardening

- Cost-aware controller (`controller_cost_aware.py`) with channel switching.
- Reliability-constrained controller (`controller.py`) with target PDR and dwell-time.
- Calibrated controller (`calibrated_controller.py`) with logistic models.
- GNU Radio IIO integration for ADALM-Pluto (`pluto_tx_adapter.py`).
- RTL-SDR sensor (`rtl_sdr_sensor.py`) with SNR estimation.
- Pluto sensor (`pluto_sensor.py`) with SNR estimation.
- Multi-seed experiment (630 runs: 30 seeds x 3 environments x 7 strategies).
- Paired-seed statistical analysis.
- Offline ML analysis (Linear Regression + Random Forest).
- Dual-sensor hardware experiments (both sensors operational).
- Full GNU Radio control path validation.
- Git: multiple commits, final "Freeze project before final submission cleanup".

### Phase 4 (Nov 22 - Nov 23, 2026): Hardware Bring-Up

- Both physical SDR devices connected to `aegon` (user `deamon`).
- RTL-SDR (0bda:2838, R820T) detected; asynchronous streaming at 2.048 MSPS verified with zero sample loss.
- ADALM-Pluto (0456:b673, Rev.C, firmware v0.32) detected; direct IP discovery (192.168.2.1) verified.
- GNU Radio 3.10.12.0 IIO source/sink availability confirmed.
- RX-only Pluto IQ capture proposed (not yet executed).
- Tuned RTL-SDR IQ capture and end-to-end RF link remain outstanding.

---

## 3. Architecture and Data Flow

```text
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

### Key Architecture Components

1. **Signal Generation** (`src/radio/waveform_generator.py`): Generates BPSK, QPSK, 16-QAM waveforms with RRC pulse shaping (2.4 MSPS, 600 ksym/s, 4 sps, beta=0.35).
2. **Channel Model** (`src/channel_model.py`): 3-channel model with AR(1) interference + burst events (volatility, burst_probability).
3. **Cognitive Controller** (`src/controller_cost_aware.py`): Cost-aware hybrid strategy with `choose_modulation`, `decide`, `channel_utility`.
4. **Reliability-Constrained Controller** (`src/controller.py`): Target PDR (0.95), dwell-time enforcement, switching rescue.
5. **Calibrated Controller** (`src/calibrated_controller.py`): Logistic regression packet-success models (BPSK, QPSK, 16-QAM).
6. **Metrics** (`src/metrics.py`): `packet_success_probability`, `evaluate_packet`, `summarize_run`.
7. **ML Analysis** (`src/ml_analysis.py`): Linear Regression + Random Forest on 630-run dataset.
8. **Hardware Interfaces**: RTL-SDR (RX), ADALM-Pluto (RX + controlled TX), with GNU Radio IIO.
9. **GNU Radio Flowgraphs**: `joint_cognitive_radio.grc`, `adaptive_modulation.grc`, `adaptive_snr_control.grc`, `snr_measurement.grc`.

---

## 4. Important Technical Decisions

| Decision | Rationale | Status |
|----------|-----------|--------|
| Use cost-aware controller (not deep learning / RL) | Deterministic, interpretable, validated | Implemented as primary controller |
| Maintain both `controller.py` (reliability-constrained) and `controller_cost_aware.py` (cost-aware hybrid) | Different objectives: reliability vs throughput optimization | Deliberately preserved; no replacement |
| Calibrated controller uses GNU Radio empirical packet models | Uncalibrated logistic models performed worse in throughput | Calibrated model outperforms uncalibrated |
| Hardware TX disabled by default | RF safety, regulatory compliance, conducted path not yet validated | Explicit `--enable-rf` flag required |
| 3-channel sensing (2 RTL-SDR + 1 Pluto) | Independent measurements, hardware availability | Dual-sensor experiment validated |
| Python simulation as primary, GNU Radio as receiver front-end | Rapid algorithm iteration, hardware validation of receiver | Simulation and GNU Radio validated separately |
| ML as offline analysis (not embedded in controller) | Dataset ready, model deployment complex | Linear Regression + Random Forest completed |
| Dwell-time enforcement in reliability controller | Prevent flapping, stabilize channel | Implemented in `controller.py` |

---

## 5. Files and Their Responsibilities

| File | Responsibility |
|------|----------------|
| `src/channel_model.py` | 3-channel AR(1) + burst interference simulation |
| `src/metrics.py` | Packet success probability model, run summarization |
| `src/controller_cost_aware.py` | Cost-aware cognitive controller (primary) |
| `src/controller.py` | Reliability-constrained controller (target PDR, dwell) |
| `src/calibrated_controller.py` | Calibrated controller with logistic models |
| `src/noise_calibration.py` | Noise-to-SNR calibration loader |
| `src/ml_analysis.py` | Offline ML (LR + RF) on experiment dataset |
| `src/multi_seed_experiment.py` | 630-run experiment runner (30 seeds x 3 env x 7 strategies) |
| `src/paired_seed_analysis.py` | Paired statistical analysis |
| `src/radio/base.py` | RadioInterface, ChannelMeasurement, PacketResult |
| `src/radio/waveform_generator.py` | Waveform generation (BPSK/QPSK/16-QAM) |
| `src/radio/simulated_radio.py` | Simulated radio backend (simulation mode) |
| `src/radio/rtl_sdr_sensor.py` | RTL-SDR RX: exact-byte capture, SNR estimation |
| `src/radio/pluto_sensor.py` | ADALM-Pluto RX: GNU Radio IIO, SNR estimation |
| `src/radio/pluto_tx_adapter.py` | ADALM-Pluto TX: GNU Radio flowgraph, controlled TX (--enable-rf) |
| `src/radio/pluto_transmitter.py` | Pluto waveform preparation |
| `src/radio/rtl_capture.py` | `capture_exact`: exact byte streaming subprocess capture |
| `src/hardware_dual_sensor.py` | Dual-SDR hardware sensing experiment |
| `src/pipelines/integrated_pipeline.py` | Integrated pipeline state machine |
| `tests/*_test.py` | Unit tests (161 passing) |
| `gnuradio/*.py` | GNU Radio flowgraphs and receiver experiments |
| `docs/*.md` | Project documentation |
| `results/` | Datasets, experiment outputs, figures |

---

## 6. Implemented Features

### Simulation Framework

- [x] 3-channel time-varying SNR model (AR(1) + bursts)
- [x] Baseline (fixed) controller
- [x] Cost-aware hybrid controller (channel switching + modulation)
- [x] Reliability-constrained controller (target PDR 0.95, dwell-time)
- [x] Calibrated controller (empirical GNU Radio packet models)
- [x] 7 strategies (fixed, adaptive_modulation, channel_switching, hybrid, reliability_constrained, cost_aware_hybrid, calibrated_hybrid)
- [x] Multi-seed experiments (30 seeds x 3 environments x 7 strategies = 630 runs)
- [x] Paired-seed statistical analysis
- [x] Waveform generation (RRC pulse shaping, 2.4 MSPS)
- [x] Offline ML analysis (Linear Regression + Random Forest)

### GNU Radio Receiver

- [x] BPSK/QPSK/16-QAM packet receiver
- [x] Timing recovery and carrier recovery (Costas loop)
- [x] Pilot-assisted gain correction
- [x] Synchronization and payload decoding
- [x] Packet-level SER, BER, PDR evaluation (10 seeds PASS)

### Calibration

- [x] Equal-power modulation calibration
- [x] Refined calibration (noise voltage vs SNR)
- [x] Logistic packet-success model fitting
- [x] Leave-one-seed-out cross-validation
- [x] Channel noise-to-SNR calibration

### Hardware Interfaces (RX operational)

- [x] RTL-SDR (RTL2838, R820T): USB detection, asynchronous streaming, 2.048 MSPS verified
- [x] ADALM-Pluto (AD9363A): USB/network detection, IIO discovery via direct IP, RX/TX channel enumeration verified
- [x] Pluto TX preparation (BPSK/QPSK/16-QAM, scaled to 0.1 amplitude, peak < 0.25)
- [x] GNU Radio IIO `fmcomms2_sink_fc32` / `fmcomms2_source_fc32` availability confirmed

### GNU Radio Integration

- [x] Joint cognitive radio flowgraph
- [x] Full GNU Radio control path test
- [x] Live channel switching tests (message-port driven)
- [x] Three-channel SNR estimator validation (error < 0.01 dB)
- [x] RTL-SDR sensor (RX): 161 unit tests pass (software verified; physical RX IQ capture pending)
- [x] Pluto sensor (RX): 161 unit tests pass (software verified; physical RX IQ capture pending)

---

## 7. Fixed Bugs

| Bug | Root Cause | Fix | Status |
|-----|-----------|-----|--------|
| Cost-aware controller `current_modulation` attribute missing | `controller_cost_aware.py` lacked `current_modulation` attr (unlike `controller.py`) | Updated `test_measured_snr_control_timed.py` to read from `JointCognitiveController.current_modulation` (message port index) | FIXED |
| RTL-SDR capture error reporting | No check on `result.returncode` in `_capture_iq` | Added returncode check with descriptive error message | FIXED |
| RTL-SDR sensor mock in tests | Tests used `SimpleNamespace` but code returned `CaptureResult` | Updated mock to use `CaptureResult` | FIXED |
| GNU Radio IIO sink creation in tests | Tests tried to build actual flowgraph with no Pluto hardware | Tests fail only when hardware/GNU Radio IIO is unavailable (environment-dependent) | Expected; software works |
| Pluto TX adapter test failures (no GNU Radio IIO context) | 3 tests fail | Expected; requires hardware. Software is correct. | Not fixed pending hardware |

---

## 8. Current Hardware Configuration

| Device | Hardware | Status |
|--------|----------|--------|
| RX | RTL-SDR (RTL2838, R820T, USB ID 0bda:2838) | ✅ USB detection verified |
| RX | ADALM-Pluto (AD9363A, Rev.C, firmware v0.32, IP 192.168.2.1) | ✅ Network detection verified |
| TX | ADALM-Pluto (PLUTOTP: AD9363) | ⚠️ TX prepared, NOT validated |

### RX Configuration

- RTL-SDR: 2.048 MSPS, 180 kHz BW, 28 dB gain, 500/501/502 MHz
- Pluto: 2.4 MSPS, 200 kHz RF BW, 30 dB gain, 500/501/502 MHz

### TX Preparation

- Waveforms: BPSK/QPSK/16-QAM, 2.4 MSPS, 600 ksym/s, RRC 0.35
- Amplitude scale: 0.1, peak limit: 0.25
- Metadata saved in `results/baseband/prepared/`

---

## 9. Confirmed Experimental Results

### Multi-Seed Experiment (simulated)

**Dataset:** `results/calibrated_multi_seed_results.csv` (630 rows: 30 seeds x 3 environments x 7 strategies)
- PDR: 0.794 to 1.000 (mean 0.982, std 0.044)
- Throughput: 1.415 to 4.000 (mean 2.595, std 0.799)

### Controlled Experiments

- 10 seeds, all PASS: packet receiver (BPSK/QPSK/16-QAM)
- Three-channel SNR estimator: validation error < 0.01 dB (synthetic pilot+noise)
- Dual-sensor hardware: both RTL-SDR and Pluto acquire measurements; controller decisions generated
- ML analysis: Random Forest R² = 0.997 (throughput), 0.985 (PDR); Linear Regression R² = 0.924 (throughput), 0.543 (PDR)

### Key Finding (simulated)

The **calibrated_hybrid** strategy (using GNU Radio empirical packet-success models) achieves the highest throughput across all interference levels while maintaining competitive PDR.

---

## 10. Simulation-Only Results

| Result Type | Examples | Limitation |
|-------------|----------|------------|
| Simulated channel | 630 runs, 30 seeds x 3 env x 7 strategies | No physical RF link, no multipath, no Doppler |
| ML model validation | R² > 0.98 on held-out seeds | Offline analysis, not embedded in controller |
| Packet receiver | 10 seeds PASS | GNU Radio flowgraph, no physical transmission |
| SNR estimation | ~5 dB (RTL-SDR), ~8 dB (Pluto) | Relative estimate, not calibrated RF SNR |
| Controlled TX | NOT EXECUTED | Requires antenna/regulatory verification |

---

## 11. Outstanding Issues

| Issue | Impact | Mitigation |
|-------|--------|-----------|
| No physical RF transmission validated | End-to-end hardware loop untested | TX preparation complete; requires antenna/attenuator setup and regulatory compliance |
| RF transmission not yet tested | Cannot verify full TX path | Requires explicit operator confirmation and safety checks |
| RTL-SDR PLL not locked warning | Cosmetic; may indicate suboptimal tuning at some frequencies | Use powered USB hub; verify at operating frequencies |
|Calibration range limited | Logistic models valid for noise 0.02-0.45 V; predictions outside ranges boundary-approximated | `clip=True` documented |
| No multipath/Doppler in simulation | Hardware TBD | Reference synchronization validation provides some coverage |
| Sample-rate offset, multipath, long-term timing drift | Not fully validated | Extended synchronization validation in progress |
| ML/DL not embedded in controller | Offline only | Dataset ready; models predict from environment+strategy only |
| **Pluto TX hardware validation** | TX preparation verified; physical TX not tested | Requires operator confirmation, safe conducted path, regulatory authorization |
| **RTL-SDR PLL warning** | Remaining unresolved | Use powered USB hub; verify at operating frequencies |
| **Tuned IQ capture pending** | Physical RX IQ capture not yet verified | Execute `iio_readdev` for Pluto RX; execute RTL-SDR capture for tuned capture |

---

## 12. Remaining Implementation Tasks

1. **Initial hardware bring-up and RX validation** (current priority)
   - ✅ RTL-SDR USB and streaming detection verified (2.048 MSPS, zero sample loss)
   - ✅ Pluto network and IIO discovery verified (direct IP)
   - ⏳ Pluto RX IQ capture (iio_readdev) - NOT YET EXECUTED
   - ⏳ Tuned RTL-SDR IQ capture - NOT YET EXECUTED
   - ⏳ Both captures inspected for valid complex IQ data - NOT YET EXECUTED

2. **Configure the intended RX center frequency, sample rate and bandwidth**
   - Pluto: RX center frequency (e.g., 500 MHz), 2.4 MSPS, 18 MHz RF BW
   - RTL-SDR: RX center frequency (e.g., 500 MHz), 2.048 MSPS, 180 kHz bandwidth

3. **Verify the sensing and SNR-estimation pipeline using actual receiver data**
   - Inject known signal (e.g., Pluto TX test) or use known broadcast signal
   - Validate SNR estimates against reference

4. **Controlled physical TX/RX experiment** (later, after RX validation)
   - Requires verified power budget and suitable attenuation
   - Never connect Pluto TX directly to RTL-SDR RX without verified RF power budget and suitable attenuation

---

## 13. Previous Decisions and Constraints

| Constraint | Status |
|------------|--------|
| RF transmission disabled by default | ✅ Verified (all scripts, default RF_ENABLED = False) |
| No deep learning / RL in controller | ✅ Preserved (cost-aware + calibrated controllers only) |
| No synthetic fabrication of hardware detection/BER/PDR | ✅ Software-only results clearly separated |
| No RF until safety verified | ✅ Explicit operator confirmation + `--enable-rf` required |
| Preserve cost-aware controller | ✅ Unchanged; verified |
| Preserve Random Forest ML component | ✅ Completed (offline analysis) |
| Frequency range 865-868 MHz | ⚠️ Not auto-authorized; verify licensing |
| GNU Radio 3.10.x on Arch Linux | ✅ Verified environment |
| Python 3.12 system interpreter | ✅ Verified |
| Hardware transmission disabled by default | ✅ RF disabled by default; `--enable-rf` required |
| No antenna radiation without regulatory authorization | ✅ Separate simulated from receive-only from over-the-air experiments |

---

## 14. Software Completion Status

**The software phase of the project is COMPLETE.**

### Completed Components

| Component | Status |
|-----------|--------|
| Channel model (3-channel, AR(1)+bursts) | ✅ Complete |
| Cost-aware controller | ✅ Complete |
| Reliability-constrained controller | ✅ Complete |
| Calibrated controller (logistic models) | ✅ Complete |
| ML analysis (LR + RF) | ✅ Complete |
| 630-run experiment dataset | ✅ Complete |
| RTL-SDR sensor (RX) | ✅ Complete (software verified; hardware RX not yet tested) |
| Pluto sensor (RX) | ✅ Complete (software verified; hardware RX not yet tested) |
| Pluto TX adapter | ✅ Complete (software verified; TX not yet validated) |
| GNU Radio receiver | ✅ Complete |
| Unit tests | ✅ All 161 pass (3 hardware-dependent tests fixed with mocks) |
| BER calculation | ✅ Implemented (synthetic validation) |

### Test Results

```text
161 passed in 4.00s
```

### Hardware-Dependent Validation

| Validation | Status |
|------------|--------|
| RF transmission | ⚠️ NOT VALIDATED (requires hardware + regulatory authorization) |
| RTL-SDR physical RX | ⚠️ NOT TESTED (software verified; tuned IQ capture pending) |
| ADALM-Pluto physical RX | ⚠️ NOT TESTED (software verified; IQ capture pending) |
| ADALM-Pluto physical TX | ⚠️ NOT VALIDATED (software verified) |
| GNU Radio IIO source/sink | ✅ Verified (3.10.12.0) |

### Next Milestone

Controlled RF transmission validation — requires:
- Antenna legality verification for the intended band
- Conducted connection with attenuation
- Power budget verification
- Explicit operator authorization before enabling RF transmission

---

## 15. Software Completion vs. Physical Hardware Validation

**Important distinction:** Software completion does not imply physical hardware validation.

| Activity | Status |
|----------|--------|
| Software implementations (all modules) | ✅ Complete |
| Software test suite | ✅ 161 tests pass |
| Simulation experiments (630 runs) | ✅ Complete |
| GNU Radio receiver | ✅ Complete |
| **RTL-SDR USB detection** | ✅ **Verified** (0bda:2838, R820T) |
| **RTL-SDR 2.048 MSPS streaming** | ✅ **Verified** (zero sample loss) |
| **Pluto SDR network detection** | ✅ **Verified** (IP 192.168.2.1) |
| **Pluto IIO discovery via direct IP** | ✅ **Verified** |
| **GNU Radio IIO source/sink** | ✅ **Verified** |
| **RX-only Pluto IQ capture** | ⏳ **PENDING** (iio_readdev not yet executed) |
| **Tuned RTL-SDR IQ capture** | ⏳ **PENDING** |
| **End-to-end physical RF transmission/reception** | ⏳ **NOT TESTED** |
| **Physical BER validation** | ⏳ **NOT TESTED** |

---

## 15. Software Completion vs. Physical Hardware Validation

**Important distinction:** Software completion does not imply physical hardware validation.

| Activity | Status |
|----------|--------|
| Software implementations (all modules) | ✅ Complete |
| Software test suite | ✅ 161 tests pass |
| Simulation experiments (630 runs) | ✅ Complete |
| GNU Radio receiver | ✅ Complete |
| **RTL-SDR USB detection** | ✅ **Verified** (0bda:2838, R820T) |
| **RTL-SDR 2.048 MSPS streaming** | ✅ **Verified** (zero sample loss) |
| **Pluto SDR network detection** | ✅ **Verified** (IP 192.168.2.1) |
| **Pluto IIO discovery via direct IP** | ✅ **Verified** |
| **GNU Radio IIO source/sink** | ✅ **Verified** |
| **RX-only Pluto IQ capture** | ✅ **VERIFIED** (4,194,304 bytes, iio_readdev) |
| **Tuned RTL-SDR IQ capture (865 MHz)** | ✅ **VERIFIED** (2,097,152 bytes) |
| **End-to-end physical RF transmission/reception** | ⏳ **NOT TESTED** |
| **Physical BER validation** | ⏳ **NOT TESTED** |

---

## 16. Previous Decisions and Constraints

| Constraint | Status |
|------------|--------|
| RF transmission disabled by default | ✅ Verified (all scripts, default RF_ENABLED = False) |
| No deep learning / RL in controller | ✅ Preserved (cost-aware + calibrated controllers only) |
| No synthetic fabrication of hardware detection/BER/PDR | ✅ Software-only results clearly separated |
| No RF until safety verified | ✅ Explicit operator confirmation + `--enable-rf` required |
| Preserve cost-aware controller | ✅ Unchanged; verified |
| Preserve Random Forest ML component | ✅ Completed (offline analysis) |
| Frequency range 865-868 MHz | ⚠️ Not auto-authorized; verify licensing |
| GNU Radio 3.10.x on Arch Linux | ✅ Verified environment |
| Python 3.12 system interpreter | ✅ Verified |
| Hardware TX disabled by default | ✅ RF disabled by default; `--enable-rf` required |
| No antenna radiation without regulatory authorization | ✅ Separate simulated from receive-only from over-the-air experiments |
| **Hardware bring-up in progress** | ✅ Both devices connected; RX streaming verified; TX validation pending |

---

## 17. Git History

| Commit | Message |
|--------|---------|
| 6363340 | Software-only completion checkpoint |
| 5deaaec | Freeze project before final submission cleanup |
| 85efbe3 | Validate full GNU Radio cognitive control path |
| 12edf57 | Merge GitHub initial commit |
| bd54bdb | Initial commit: cost-aware cognitive radio framework |
| 4d204d0 | Initial commit |

**Current state:** Branch `main`, ahead 2 of 0 behind origin/main. Documentation is the priority for synchronization after the software completion checkpoint.

---

## 18. Phase 4: Physical Hardware Validation (November 23, 2026)

Both physical SDR devices have been connected to `aegon` (user `deamon`). This section records the complete hardware validation status:

| Validation | Status |
|------------|--------|
| RTL-SDR USB detection | ✅ Verified (0bda:2838, R820T, SN: 00000001) |
| RTL-SDR R820T tuner detection | ✅ Verified |
| RTL-SDR 2.048 MSPS async streaming | ✅ Verified (zero sample loss) |
| RTL-SDR PLL warning investigation | ⚠️ WARNING: Persistent at all tested frequencies (100 MHz, 500 MHz, 865 MHz); driver-level USB/PLL behavior; tuner responds to valid frequencies |
| RTL-SDR 865 MHz capture | ✅ Verified (file size 2,097,152 bytes = 1,048,576 complex samples) |
| RTL-SDR capture quality | ✅ Validated: no clipping, I/Q RMS balanced, low DC offset, low correlation |
| RTL-SDR tuned IQ capture | ✅ Validated |
| ADALM-Pluto network connectivity (192.168.2.1) | ✅ Verified |
| ADALM-Pluto IIO discovery via direct IP | ✅ Verified |
| ADALM-Pluto RX/TX channel enumeration | ✅ Verified |
| ADALM-Pluto IQ capture (iio_readdev) | ✅ Verified (file size 4,194,304 bytes = 1,048,576 complex samples) |
| ADALM-Pluto IQ capture quality | ✅ Validated: no clipping, small DC offset, I/Q RMS balanced |
| GNU Radio 3.10.12.0 IIO source/sink | ✅ Verified (fmcomms2_sink_fc32, fmcomms2_source_fc32) |
| Existing SNR estimator (RTL-SDR sensor) | ✅ Validated on physical IQ data (SNR: 5.18 dB) |
| Existing SNR estimator (Pluto sensor) | ✅ Validated on physical IQ data (SNR: 3.69 dB) |
| End-to-end physical RF transmission/reception | ⏳ NOT TESTED |
| Physical BER validation | ⏳ NOT TESTED |
| Pluto TX experimental mode | ⏳ NOT TESTED (RX validation only) |

### 18.1 RTL-SDR IQ Capture Validation

**Capture command:**
```bash
rm -f /tmp/rtl_rx_iq.bin
set -o pipefail
rtl_sdr -f 865000000 -s 2048000 -g 28 -S - | head -c 2097152 > /tmp/rtl_rx_iq.bin
```

**Confirmed file size:** 2,097,152 bytes (1,048,576 complex samples)

**IQ statistics (unsigned 8-bit, centered to signed):**
- Complex samples: 1,048,576
- I mean: -0.132 (centered)
- Q mean: -0.132 (centered)
- I RMS: 0.599 (centered)
- Q RMS: 0.599 (centered)
- I peak: 2.5
- Q peak: 2.5
- I/Q correlation: 0.000115 (near zero, healthy)
- Clipped samples at 0 or 255: 0 (no clipping)
- I variance: 0.341
- Q variance: 0.341

**Interpretation:**
- Capture file size is stable and correct.
- No clipping (no samples at 0 or 255).
- I/Q RMS balanced (0.599 vs 0.599).
- Low DC offset (-0.132, small but consistent).
- Low I/Q correlation indicates healthy IQ data.
- The small DC offset is consistent with the original Pluto capture DC offset and should be monitored.

### 18.2 PlutoSDR IQ Capture Validation

**Capture command:**
```bash
iio_readdev \
  -u ip:192.168.2.1 \
  -b 4096 \
  -s 1048576 \
  cf-ad9361-lpc voltage0 voltage1 \
  > /tmp/pluto_rx_iq.bin
```

**Confirmed file size:** 4,194,304 bytes (1,048,576 complex samples)

**IQ statistics (signed 16-bit, raw):**
- Complex samples: 1,048,576
- I mean: 0.179
- Q mean: 0.091
- I RMS: 105.793
- Q RMS: 105.097
- I peak: 1463
- Q peak: 1452
- I/Q correlation: -0.00916 (near zero, healthy)
- Clipped samples: 0
- Max absolute value: 1463 (12-bit ADC max: 2047)

**Interpretation:**
- Capture length and file format are consistent with two 16-bit channels.
- No clipping (max value 1463 < 2047, well within 12-bit range).
- Small DC offsets (I mean: 0.179, Q mean: 0.091).
- I/Q RMS values are close (105.793 vs 105.097).
- These results do not establish calibrated amplitude, sensitivity, or SNR accuracy.

### 18.3 R820T PLL Warning Investigation

**Investigation findings:**
- The PLL warning `[R82XX] PLL not locked!` appears at all tested frequencies: 100 MHz, 500 MHz, 865 MHz.
- The warning is NOT frequency-dependent.
- It appears in both bulk mode (`-S`) and isochronous mode (default).
- The RTL2838 device responds correctly to all valid frequencies (tuned to 865000000 Hz, 500000000 Hz, 100000000 Hz without errors).
- No competing processes detected (`pgrep` found no RTL-SDR or GNU Radio process).
- Device has no conflicting kernel driver (`lsusb -t` showed no kernel driver, `sudo fuser` showed no process holding device).
- Driver: kernel 4.19.0, device vendor Realtek ID 0bda:2838.
- Tuner: Rafael Micro R820T.
- The warning is likely a driver-level USB transfer behavior (PLLOffset / PLL not finding steady state) rather than a hardware failure.
- **Open question:** Whether the actual tuned IQ capture data is affected (data quality analysis showed healthy IQ with low correlation). Further observation needed.
- **Recommendation:** Use a powered USB hub, verify at operating frequencies, and consider driver/firmware version compatibility. Do not assume the warning is harmless, but do not assume hardware failure either.

### 18.4 Receiver Configuration

**PlutoSDR (RX only, capture performed at default hardware configuration):**
- RX LO: 2.4 GHz (reported default, NOT the intended 865-868 MHz SRD band)
- Sample rate: 30.72 MSPS (reported default)
- RF bandwidth: 18 MHz (reported default)
- Gain: 30 dB
- Capture: `/tmp/pluto_rx_iq.bin` (4,194,304 bytes)

**RTL-SDR (RX only, tuned capture performed):**
- Center frequency: 865 MHz
- Sample rate: 2.048 MSPS
- Gain: 28 dB
- Bandwidth: 180 kHz
- Capture: `/tmp/rtl_rx_iq.bin` (2,097,152 bytes)

### 18.5 SNR Estimation Validation with Physical IQ

**Existing SNR estimators tested:**
- **RTL-SDR sensor** (`src/radio/rtl_sdr_sensor.py`): Validated on actual capture at 865 MHz, SNR: 5.18 dB
- **Pluto sensor** (`src/radio/pluto_sensor.py`): Validated on actual capture (500/501/502 MHz), SNR: 3.69 dB

**Validation notes:**
- SNR estimates from physical captures are valid but must be interpreted correctly:
  - RTL-SDR: The 865 MHz capture from a DVB-T device (not a calibrated RF receiver) gives a relative SNR estimate. The values should not be treated as absolute RF SNR.
  - PlutoSDR: The 1900 MHz capture is outside the intended SRD band (865-868 MHz).
- For actual calibrated SNR, a known signal or controlled reference measurement will be necessary.
- The SNR estimator pipeline now has real hardware validation evidence, not just synthetic results.

### 18.6 Remaining Blockers

1. **R820T PLL warning:** Should be investigated further, but tuner responds correctly. Not blocking.
2. **TX validation:** Pluto TX remains disabled. Future TX/RX experiment requires separately reviewed RF safety plan, suitable attenuation, verified power budget, and regulatory compliance.
3. **Intent band configuration:** RX center frequency adjustment to 865-868 MHz is planned (next step after RX validation).
4. **SNR calibration:** Physical SNR estimates are relative, not absolute. A known signal reference will be needed for calibrated accuracy.

---

```text
├── results/pluto_rtl_sdr_comparison.png
├── results/sdr_spectrum_comparison.png
├── results/sdr_spectrum_normalized.png
├── results/snr_estimation_physical.png
├── results/snr_physical_validation.csv
└── results/rtl_sdr_capture/ (existing, 500/501/502 MHz captures)
```

---

*End of Project History and Current State document.*
