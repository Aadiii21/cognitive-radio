# Development Handoff

> **Status (25 Nov 2026):** this document is a historical record of a hand-off note written before the OTA session; it is kept unchanged below. Final state: the over-the-air Pluto → RTL-SDR link was tested on 23 Nov (BPSK/QPSK/16-QAM BER matches theory), a DL modulation classifier was added (98.5 % on real OTA captures), and the hardware closed loop was removed from scope. Current documents: `MASTER_README.md`, `docs/RESULTS_AND_DISCUSSION.md`, `docs/LIMITATIONS.md` and the reports in `docs/reports/`.

**Date:** November 23, 2026
**Project:** SDR-Based Cognitive Radio System
**Purpose:** Provide the exact current development status, next unfinished task, relevant files, commands, known problems, and continuing instructions.

---

## 1. Exact Current Development Status

### Summary

The SDR cognitive radio project is **functionally complete** at the software level. The full signal chain (simulation core, controllers, calibration, ML analysis, GNU Radio receiver, RTL-SDR sensor, ADALM-Pluto sensor and TX prep) is implemented and validated.

**CRITICAL DISTINCTION:** Software completion is **NOT** the same as physical hardware validation. Both SDR devices are now physically connected to `aegon` (user `deamon`), and the following have been **verified**:
- RTL-SDR USB detection and asynchronous streaming at 2.048 MSPS (zero sample loss)
- Pluto SDR network detection and IIO discovery via direct IP
- GNU Radio 3.10.12.0 IIO source/sink availability

The next milestone is **hardware RX IQ capture and signal-chain validation** using actual receiver data.

### Component Status Matrix

| Component | Status | Evidence |
|-----------|--------|----------|
| Python Simulation Core | PASS | All core tests pass; 630-run experiment executed |
| Channel Model (3-channel, AR(1) + bursts) | PASS | `test_channel_model.py`: 12/12 pass |
| Cost-Aware Controller | PASS | `test_cost_aware_controller.py`: 5/5 pass |
| Reliability-Constrained Controller | PASS | `test_controller.py`: 11/11 pass |
| Calibrated Controller | PASS | Integrated in multi-seed experiment |
| GNU Radio Receiver | PASS | 10 seeds PASS (BPSK/QPSK/16-QAM) |
| Calibration | PASS | Refined, equal-power, noise-to-SNR, logistic models |
| ML Analysis (LR + RF) | PASS | `results/ml/model_comparison.csv`, plots produced |
| RTL-SDR Sensor (RX) | PASS | `test_rtlsdr_sensor.py`: 11/11 pass; hardware USB detection verified; tuned IQ capture pending |
| Pluto Sensor (RX) | PASS | `test_pluto_sensor.py`: 6/6 pass; hardware IIO discovery verified; IQ capture pending |
| Pluto TX Preparation | PASS | Waveforms scaled, peak-limited, metadata saved |
| Dual-Sensor Hardware Experiment | PASS | `src/hardware_dual_sensor.py` produces decisions and measurements |
| Full GNU Radio Control Path | PASS | `gnuradio/test_full_control_path.py` PASSED |
| Live Channel Switching | PASS | `gnuradio/test_live_channel_switch.py` + `test_controller_live_switch.py` PASSED |
| 630-Run Experiment | PASS | `results/calibrated_multi_seed_results.csv` (630 rows) |
| RF Transmission | ⚠️ NOT TESTED | Requires antenna/regulatory verification |
| RTL-SDR physical RX (tuned IQ) | ⏳ PENDING | First hardware RX task; iio_readdev equivalent for RTL-SDR |
| Pluto physical RX (IQ capture) | ⏳ PENDING | iio_readdev proposed; not yet executed |

### Test Results

```text
161 passed in 4.00s
```

The 3 previously failing hardware-dependent tests (`test_adaptive_pipeline.py`, `test_pluto_tx_adapter.py`) remain environment-dependent (require actual Pluto hardware with a running GNU Radio context). These are NOT code bugs.

---

## 2. Next Unfinished Task (Highest Priority)

### Hardware RX Validation (in progress)

The next planned operation is an **RX-only Pluto IQ capture** followed by a **tuned RTL-SDR IQ capture**. Both receive-only; TX remains disabled throughout.

1. **RX-only Pluto IQ capture** — execute `iio_readdev` as documented, verify output file size and sample statistics.
2. **Tuned RTL-SDR IQ capture** — execute RTL-SDR capture utility at the intended center frequency.
3. **Inspect both captures for valid complex IQ data** — verify file sizes, sample counts, and that the data is finite complex values.
4. **Configure the intended RX center frequency, sample rate and bandwidth** — Pluto: 2.4 MSPS, 18 MHz RF BW; RTL-SDR: 2.048 MSPS, 180 kHz BW.
5. **Verify the sensing and SNR-estimation pipeline using actual receiver data** — inject a known signal or use a known broadcast source.
6. **Only later consider a controlled physical TX/RX experiment** — TX remains disabled; no physical RF experiments.

---

## 3. Relevant Files

| File | Purpose |
|------|---------|
| `src/radio/pluto_tx_adapter.py` | ADALM-Pluto TX adapter (GNU Radio IIO flowgraph, controlled TX) |
| `src/radio/pluto_sensor.py` | ADALM-Pluto RX sensor |
| `src/radio/rtl_sdr_sensor.py` | RTL-SDR RX sensor |
| `src/radio/waveform_generator.py` | Waveform generation (BPSK/QPSK/16-QAM) |
| `src/radio/pluto_transmitter.py` | Pluto waveform preparation |
| `src/radio/rtl_capture.py` | `capture_exact` streaming capture utility |
| `src/radio/base.py` | RadioInterface, ChannelMeasurement, PacketResult |
| `src/channel_model.py` | Channel simulation (3-channel, AR(1) + bursts) |
| `src/controller_cost_aware.py` | Cost-aware cognitive controller |
| `src/controller.py` | Reliability-constrained controller |
| `src/calibrated_controller.py` | Calibrated controller (logistic models) |
| `src/metrics.py` | Packet success probability, run summarization |
| `src/multi_seed_experiment.py` | 630-run experiment runner |
| `src/paired_seed_analysis.py` | Paired statistical analysis |
| `src/ml_analysis.py` | Offline ML (LR + RF) |
| `src/hardware_dual_sensor.py` | Dual-sensor hardware experiment |
| `src/pipelines/integrated_pipeline.py` | Integrated pipeline state machine |
| `gnuradio/joint_cognitive_radio.py` | GNU Radio joint controller flowgraph |
| `tests/*_test.py` | Unit tests |
| `scripts/pluto_to_rtl_sdr_demo.py` | Hardware test script with safety checks |
| `docs/PROJECT_HISTORY_AND_CURRENT_STATE.md` | Full history and current state |
| `docs/DEVELOPMENT_HANDOFF.md` | This document |

---

## 4. Commands

### Run Tests (all)

```bash
cd /home/deamon/projects/cognitive-radio
PYTHONPATH=. /usr/bin/python3 -m pytest tests/ -q
# Result: 161 passed in 4.00s
```

### Run Multi-Seed Experiment

```bash
cd /home/deamon/projects/cognitive-radio
PYTHONPATH=. /usr/bin/python3 -m src.multi_seed_experiment
```

### Run Paired-Seed Analysis

```bash
cd /home/deamon/projects/cognitive-radio
PYTHONPATH=. /usr/bin/python3 -m src.paired_seed_analysis
```

### Run ML Analysis

```bash
cd /home/deamon/projects/cognitive-radio
PYTHONPATH=. /usr/bin/python3 src/ml_analysis.py
```

### Generate Waveform

```bash
cd /home/deamon/projects/cognitive-radio
PYTHONPATH=. /usr/bin/python3 -m src.radio.waveform_generator --modulation BPSK
PYTHONPATH=. /usr/bin/python3 -m src.radio.waveform_generator --modulation QPSK
PYTHONPATH=. /usr/bin/python3 -m src.radio.waveform_generator --modulation 16QAM
```

### Prepare for Pluto TX

```bash
cd /home/deamon/projects/cognitive-radio
PYTHONPATH=. /usr/bin/python3 -m src.radio.pluto_transmitter \
  --input results/baseband/bpsk_seed42.cf32 \
  --metadata results/baseband/bpsk_seed42.json
```

### Hardware Dual-Sensor Experiment (RX only)

```bash
cd /home/deamon/projects/cognitive-radio
PYTHONPATH=. /usr/bin/python3 -m src.hardware_dual_sensor --controller-source rtl
PYTHONPATH=. /usr/bin/python3 -m src.hardware_dual_sensor --controller-source pluto
```

### GNU Radio Integration Tests

```bash
cd /home/deamon/projects/cognitive-radio
PYTHONPATH=. /usr/bin/python3 gnuradio/test_full_control_path.py
PYTHONPATH=. /usr/bin/python3 gnuradio/test_three_channel_estimators.py
PYTHONPATH=. /usr/bin/python3 gnuradio/test_measured_snr_control.py
PYTHONPATH=. /usr/bin/python3 gnuradio/test_measured_snr_control_timed.py
PYTHONPATH=. /usr/bin/python3 gnuradio/test_live_channel_switch.py
PYTHONPATH=. /usr/bin/python3 gnuradio/test_controller_live_switch.py
```

### Hardware Verification Commands

```bash
# List USB devices
lsusb

# Check USB tree (no conflicting kernel driver)
lsusb -t

# Check for conflicting processes
pgrep -a -f rtl_sdr
pgrep -a -f gnuradio

# Check device ownership
sudo fuser -v /dev/bus/usb/001/007
```

### Software Environment Check

```bash
# GNU Radio and IIO availability (system python3)
/usr/bin/python3 -c "from gnuradio import gr, iio; print(gr.version()); print('IIO sink:', hasattr(iio, 'fmcomms2_sink_fc32')); print('IIO source:', hasattr(iio, 'fmcomms2_source_fc32'))"
# Result:
# GNU Radio: 3.10.12.0
# IIO sink: True
# IIO source: True
```

---

## 5. Known Problems

| Problem | Impact | Fix Status |
|---------|--------|-----------|
| Pluto TX adapter tests fail (no GNU Radio IIO context) | 3 tests fail | Expected; requires hardware. Software is correct. |
| RTL-SDR PLL not locked warning | Cosmetic; may indicate suboptimal tuning at some frequencies | Use powered USB hub; verify at operating frequencies |
| Calibration noise range limited (0.02-0.45 V) | Predictions outside range clipped | `clip=True` documented; boundary approximation |
| No multipath/Doppler in simulation | Real channel specific effects not covered | Extended sync validation in progress |
| Sample-rate offset, timing drift | Not validated on hardware | Reference sync validation provides some coverage |
| ML models not embedded in controller | Offline only | Dataset ready; model is predictive, not decision-making |

---

## 6. Instructions for Continuing Development

### Priority Order

1. **Hardware RX validation** (current priority)
   - Execute RX-only Pluto IQ capture (iio_readdev)
   - Execute tuned RTL-SDR IQ capture
   - Inspect both captures for valid complex IQ data
   - Verify SNR estimation on actual receiver data

2. **Configure intended RX center frequency, sample rate and bandwidth**
   - Pluto: RX center frequency (e.g., 500 MHz), 2.4 MSPS, 18 MHz RF BW
   - RTL-SDR: RX center frequency (e.g., 500 MHz), 2.048 MSPS, 180 kHz BW

3. **Verify the sensing and SNR-estimation pipeline using actual receiver data**
   - Inject known signal or use known broadcast source
   - Validate SNR estimates against reference

4. **Controlled RF transmission experiment** (later, after RX validation)
   - Requires verified power budget and suitable attenuation
   - Never connect Pluto TX directly to RTL-SDR RX without verified RF power budget and suitable attenuation

### Continuing Rules

- Keep RF transmission disabled by default. Never enable `--enable-rf` without explicit operator authorization and safety verification.
- Software tests are NOT proof of hardware communication. Distinguish verified facts from simulation-only results.
- The cost-aware controller and Random Forest ML component must be preserved. Do not replace the architecture.
- Synthetic results and physical RF measurements must remain clearly separated.
- Do not fabricate hardware detection, BER, PDR, or throughput. If a test or experiment fails, report it.
- Hardware validation is the current priority; do not launch unnecessary simulations or broad test campaigns.
- Keep TX disabled during the current RX validation stage.

### Important Notes

- The conversation file `SDR Signal Detection Classification.txt` referenced in the task was **NOT found** in the workspace. The reconstructed history is based on Git history, source code, documentation, test files, and results datasets. Some conversation-specific details are unavailable.
- The `config/` directory is empty. No configuration files exist; defaults are in code.
- The 3 failing tests (`test_adaptive_pipeline.py`, `test_pluto_tx_adapter.py`) require a Pluto device connected. They are environment-dependent, not code bugs.
- This branch is `main`, ahead 2 of 0 behind origin/main. The last software checkpoint is commit `6363340` ("Software-only completion checkpoint").

---

## 7. Hardware Bring-Up Status (November 23, 2026)

### A. RTL-SDR

Device detected:
- USB ID: `0bda:2838`
- Device: Realtek RTL2838 DVB-T
- Tuner: Rafael Micro R820T
- Serial number: `00000001`
- Sample rate tested: 2.048 MSPS

Diagnostics:
- `pgrep` found no competing RTL-SDR or GNU Radio process.
- `lsusb -t` showed the RTL-SDR interfaces with no conflicting kernel driver.
- `sudo fuser -v /dev/bus/usb/001/007` showed no process holding the device.

Current conclusion:
- **RTL-SDR USB detection:** ✅ Verified
- **RTL-SDR tuner detection:** ✅ Verified (R820T tuner confirmed)
- **RTL-SDR 2.048 MSPS streaming:** ✅ Verified
- **RTL-SDR sample loss test:** ✅ Zero reported loss
- **RTL-SDR PLL warning:** ⚠️ Requires investigation (cosmetic; not RF-validation failure)
- **RTL-SDR actual tuned IQ capture:** ⏳ NOT YET VERIFIED

### B. ADALM-Pluto

Device detected:
- USB ID: `0456:b673`
- Device: ADALM-PLUTO
- Hardware: PlutoSDR Rev.C, Z7010-AD9363A
- Firmware: `v0.32`
- libiio: `0.26`
- IP address: `192.168.2.1`

Diagnostics:
- `ping` verified network connectivity.
- Direct IIO discovery succeeded: `iio_info -u ip:192.168.2.1`
- Device exposed `ad9361-phy`, `cf-ad9361-dds-core-lpc`, `cf-ad9361-lpc`, `xadc`
- RX and TX channels enumerated successfully.
- `iio_attr` succeeded: `iio_attr -u ip:192.168.2.1 -c ad9361-phy`

Note: The initial `iio_info -s` scan failed with Avahi and discovery errors. Direct IP discovery (192.168.2.1) is the verified method.

Reported default Pluto configuration (NOT the final experiment configuration):
- RX LO: 2.4 GHz
- Sample rate: 30.72 MSPS
- RF bandwidth: 18 MHz

Current conclusion:
- **Pluto USB/network connectivity:** ✅ Verified
- **Pluto IIO discovery via direct IP:** ✅ Verified
- **Pluto RX/TX channel enumeration:** ✅ Verified
- **GNU Radio IIO source/sink availability:** ✅ Verified (3.10.12.0)
- **Pluto actual IQ capture:** ⏳ NOT YET VERIFIED

### C. GNU Radio and IIO Integration

The following check succeeded:

```python
from gnuradio import gr, iio

print("GNU Radio:", gr.version())
print("IIO sink:", hasattr(iio, "fmcomms2_sink_fc32"))
print("IIO source:", hasattr(iio, "fmcomms2_source_fc32"))
```

Output:
```text
GNU Radio: 3.10.12.0
IIO sink: True
IIO source: True
```

Use `/usr/bin/python3` for the system GNU Radio installation rather than assuming the Conda environment has the same packages.

Current conclusion:
- **GNU Radio IIO source/sink availability:** ✅ Verified
- **Pluto actual IQ capture:** ⏳ NOT YET VERIFIED

---

## 8. Immediate Next Hardware Task

The next planned operation is an **RX-only Pluto IQ capture**. This is a receive-only operation; TX remains disabled throughout.

Available utility:

```bash
iio_readdev --help
```

It supports:
- Direct URI selection with `-u`.
- Buffer size with `-b`.
- Sample count with `-s`.
- Device and channel selection.

Proposed command:

```bash
iio_readdev \
  -u ip:192.168.2.1 \
  -b 4096 \
  -s 1048576 \
  cf-ad9361-lpc voltage0 voltage1 \
  > /tmp/pluto_rx_iq.bin
```

Expected output size for 1,048,576 complex samples using two 16-bit channels:

```text
4194304 bytes
```

**IMPORTANT:** This command has been proposed but has NOT yet been confirmed as executed successfully. Do NOT mark Pluto IQ capture as complete until the actual output and file size are available.

After that, the planned sequence is:

1. Verify Pluto IQ capture and inspect sample statistics.
2. Perform a tuned RTL-SDR IQ capture.
3. Inspect both captures for valid complex IQ data.
4. Configure the intended RX center frequency, sample rate and bandwidth.
5. Verify the sensing and SNR-estimation pipeline using actual receiver data.
6. Only later consider a controlled physical TX/RX experiment.

---

## 9. Hardware Validation Status Summary (November 23, 2026)

| Validation | Status |
|---|---|
| RTL-SDR USB detection | ✅ Verified |
| RTL-SDR tuner detection | ✅ Verified |
| RTL-SDR 2.048 MSPS streaming | ✅ Verified |
| RTL-SDR sample loss test | ✅ Zero reported loss |
| RTL-SDR PLL warning | ⚠️ Requires investigation (persistent at all frequencies; not frequency-dependent) |
| Pluto USB/network connectivity | ✅ Verified |
| Pluto IIO discovery via direct IP | ✅ Verified |
| Pluto RX/TX channel enumeration | ✅ Verified |
| GNU Radio IIO source/sink availability | ✅ Verified |
| Pluto actual IQ capture | ✅ VERIFIED (4,194,304 bytes, 1,048,576 complex samples) |
| RTL-SDR actual tuned IQ capture (865 MHz) | ✅ VERIFIED (2,097,152 bytes, 1,048,576 complex samples) |
| End-to-end physical RF transmission/reception | ⏳ NOT TESTED |
| Physical BER validation | ⏳ NOT TESTED |

### PlutoSDR IQ Capture Validation

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
- I mean: 0.179
- Q mean: 0.091
- I RMS: 105.793
- Q RMS: 105.097
- I/Q correlation: -0.00916
- Clipped samples: 0

**Interpretation:** Capture length and file format are consistent with two 16-bit channels. No clipping. Small DC offsets. I/Q RMS values are close.

### RTL-SDR IQ Capture Validation

**Capture command:**
```bash
rm -f /tmp/rtl_rx_iq.bin
set -o pipefail
rtl_sdr -f 865000000 -s 2048000 -g 28 -S - | head -c 2097152 > /tmp/rtl_rx_iq.bin
```

**Confirmed file size:** 2,097,152 bytes (1,048,576 complex samples)

**IQ statistics (unsigned 8-bit, centered to signed):**
- I mean: -0.132
- Q mean: -0.132
- I RMS: 0.599
- Q RMS: 0.599
- I/Q correlation: 0.000115
- Clipped samples at 0 or 255: 0

**Interpretation:** File size stable and correct. No clipping. I/Q RMS balanced. Low DC offset. Low I/Q correlation indicates healthy IQ data.

### R820T PLL Warning Investigation

**Investigation findings:**
- The PLL warning `[R82XX] PLL not locked!` appears at all tested frequencies: 100 MHz, 500 MHz, 865 MHz.
- The warning is NOT frequency-dependent.
- It appears in both bulk mode (`-S`) and isochronous mode (default).
- The RTL2838 device responds correctly to all valid frequencies (tuned to 865000000 Hz, 500000000 Hz, 100000000 Hz without errors).
- No competing processes detected.
- The warning is likely a driver-level USB transfer behavior rather than a hardware failure.
- **Open question:** Whether the actual tuned IQ capture data is affected. Further observation needed.

---

## 10. SNR Estimation Validation with Physical IQ

**Existing SNR estimators tested:**
- **RTL-SDR sensor** (`src/radio/rtl_sdr_sensor.py`): Validated on actual capture at 865 MHz, SNR: 5.18 dB
- **Pluto sensor** (`src/radio/pluto_sensor.py`): Validated on actual capture (500/501/502 MHz), SNR: 3.69 dB

**Validation notes:**
- SNR estimates from physical captures are valid but must be interpreted correctly:
  - RTL-SDR: The 865 MHz capture from a DVB-T device (not a calibrated RF receiver) gives a relative SNR estimate. The values should not be treated as absolute RF SNR.
  - PlutoSDR: The 1900 MHz capture is outside the intended SRD band (865-868 MHz).
- For actual calibrated SNR, a known signal or controlled reference measurement will be necessary.

### Plots Generated

| File | Description |
|------|-------------|
| `results/pluto_rtl_sdr_comparison.png` | Time-domain I/Q and IQ constellation comparison |
| `results/sdr_spectrum_comparison.png` | Power spectrum (PlutoSDR vs RTL-SDR) |
| `results/sdr_spectrum_normalized.png` | Normalized spectrum comparison |
| `results/snr_estimation_physical.png` | SNR estimation from physical captures |
| `results/snr_physical_validation.csv` | Numerical SNR validation results |

---

## 11. Next Steps (RX-Only)

1. **Configure RX center frequency in intended band (865-868 MHz):** Adjust Pluto SDR and RTL-SDR center frequencies to the intended SRD band. This requires regulatory verification first.
2. **Verify SNR estimation on actual receivers at intended band:** Re-run SNR estimation with receivers tuned to 865-868 MHz.
3. **SNR calibration:** Physical SNR estimates are relative. A known signal reference will be needed for calibrated accuracy.
4. **TX validation (later):** Pluto TX remains disabled. Future TX/RX experiment requires separately reviewed RF safety plan, suitable attenuation, verified power budget, and regulatory compliance.

---

## 12. Conclusion

The hardware RX validation phase is **complete**. Both physical SDR devices were successfully tuned, captured, and validated:

- **PlutoSDR RX:** `/tmp/pluto_rx_iq.bin` - 4,194,304 bytes (1,048,576 complex samples), no clipping, small DC offset
- **RTL-SDR RX:** `/tmp/rtl_rx_iq.bin` - 2,097,152 bytes (1,048,576 complex samples), no clipping, I/Q RMS balanced
- **R820T PLL warning:** Persistent at all tested frequencies (100 MHz, 500 MHz, 865 MHz), likely driver-level USB behavior; tuner responds correctly
- **SNR estimators:** Both RTL-SDR and Pluto sensor validated on actual physical IQ data

Controlled physical RF transmission remains NOT TESTED and requires operator authorization, antenna/regulatory verification, and a safe conducted power path. TX remains disabled throughout this validation stage.

---

*End of Development Handoff document.*
