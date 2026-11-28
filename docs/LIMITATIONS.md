# Limitations

*Final version, 28 Nov 2026 (closed-loop hardware results added; the 25 Nov text is otherwise unchanged). The 22 Nov version is in `docs/archive/LIMITATIONS_2026-11-22.md`; it predates the over-the-air experiments and the DL classifier, and some of its statements no longer hold (see section 8).*

## 1. Hardware

### 1.1 Devices
- **ADALM-Pluto Rev.C** (AD9363), firmware v0.32, `ip:192.168.2.1`, driven from Python with pyadi-iio 0.0.21 / libiio 0.26.
- **RTL-SDR** (RTL2832U / R820T), 2.048 MS/s, manual gain 28 dB.

### 1.2 What was done on hardware
- Receive-only sensing on three channels (500, 501, 502 MHz) with both devices, repeated five times per sensor.
- **One over-the-air (OTA) session at 866 MHz on 23 Nov**: tone test, BPSK frames, and a BPSK/QPSK/16-QAM BER sweep (Pluto TX attenuation 0–20 dB, 19 multimod runs).
- **Closed-loop channel switching on 28 Nov**: 5 sessions (72 rounds, 288 bursts) on 865.7 / 866.5 / 867.3 MHz, antennas 1.5 m apart, two sessions with a 2 dB safety margin; plus a 3-minute passive band scan.

### 1.3 Limits of the hardware evidence
- **Channel quality in the closed loop is scripted.** The three channels are real, separate RF channels and the radios really retune, but their difference in quality comes from the Pluto's own TX attenuation, not from interference, fading or other users. A passive scan found each channel within 0.6 dB of the band floor, with no wideband activity, so the real channels would otherwise have looked the same. Behaviour under real interference is untested.
- **Probe-to-data gap.** The controller decides on a probe sent a few seconds before the data. Short Es/N0 dips of up to 8.5 dB within a burst (15 of 143 data frames) carried 68 of the 78 16-QAM errors, so 16-QAM BER on air (1.3 × 10⁻³) was well above the AWGN value for its mean Es/N0 (1.0 × 10⁻⁴). The cause of the dips was not identified.
- **No "do not transmit" option.** With every channel poor (phase E, 3.6–5.5 dB) the controller still sent BPSK and lost up to 3 % of bits.
- **Safety margin not sized on hardware.** The link drifted by about 3 dB between sessions (mean best-channel Es/N0 17.5–20.6 dB at the same setting), so the lower BER with a 2 dB margin cannot be attributed to the margin; its throughput cost (about 20 %) is clear.
- **One room, one antenna spacing, about 35 minutes** of closed-loop operation. Raw closed-loop captures (330 MB) are kept outside the repository.
- **BER sweep: one session, one antenna arrangement.** Antenna separation was not recorded. Es/N0 varied by about ±1.5 dB between runs at the same setting.
- **Small samples.** Each BER point is one 512 ms capture of 4,096 bits. A zero-error run only shows BER < 7.3 × 10⁻⁴ (95 %); the 16-QAM 17.1 dB point rests on 5 errors.
- **BER sweep at a single frequency** (866 MHz); channel switching was exercised in the closed-loop sessions only.
- **No conducted comparison.** The runs were started with `--rf-path conducted --attenuator-db 30` but used antennas; the records carry an `rf_path_correction` block (actual: OTA).
- Indoor link; no fading or multipath measurement on air.
- Measured BER is slightly worse than AWGN theory in 5 of 9 runs with errors (implied loss up to 0.75 dB above 4 dB Es/N0).

## 2. Simulation assumptions

### 2.1 Channel model
- Three channels with base SNRs 18, 13 and 9 dB.
- Interference: AR(1) with coefficient 0.85 plus occasional 6–14 dB bursts; 1 dB measurement noise; SNR clipped to −5…30 dB.
- The two-path multipath model is used only in the synchronisation validation, not in the benchmark.

### 2.1a GNU Radio software-in-the-loop channels
In `gnuradio/joint_cognitive_radio.py` each of the three "channels" is the same 1 kHz test tone with its own Gaussian noise source and a scaled interference term at the same frequency. As a faculty review pointed out, they are effectively one channel with different noise: there is no difference in frequency. The experiment tests the controller's decision logic on a running flowgraph, not RF channel behaviour. This does not affect the calibration (section 3), which measures packet success against SNR per modulation, independent of which channel the SNR occurs on; on air, BPSK and QPSK followed that AWGN behaviour within about 1 dB.

### 2.2 Interference environments
Low, Medium and High set the **interference level** (mean, variation and burst probability), not the channel SNR. Higher interference lowers the SNR of the affected channel.

### 2.3 Packet outcomes
In the benchmark, packet success is drawn from the calibrated logistic curves; packets are not decoded one by one. The calibrated hybrid uses the same curves for its decisions, so it is scored with the model it knows. The robustness study (`results/sensitivity/`) shows that with reality 1 dB worse it still leads in throughput, but its PDR drops to 0.969 / 0.933 (medium / high) unless it keeps a 1 dB safety margin.

## 3. Calibration
- Packet-success curves and the SNR ↔ noise-voltage map come from GNU Radio's synthetic AWGN channel, not from radio hardware. They do not model interference that is not noise-like (narrowband, bursty, another modulated signal) or short fades such as the dips seen on air.
- The logistic models are valid only inside the calibrated noise range; outside it the controller clips to the nearest calibrated value.
- The calibration is fixed during an experiment; it is not updated online.

## 4. Signal processing
- **Multipath:** 2- and 4-sample echoes with amplitude ≥ 0.5 cause timing errors in about 50 % of trials; there is no equaliser.
- **SRO:** corrected up to 20 ppm; 50 ppm needs a higher-order timing-drift model.
- **CFO:** GNU Radio path validated to ±2 kHz. The on-air receivers handle ±100 kHz; −10.4 kHz was observed.
- GNU Radio receiver EVM is about 35 % in AWGN because the simple gain estimate does not equalise the RRC pulse shape.

## 5. Machine learning and deep learning
- **Random forest / linear regression** (`src/ml_analysis.py`): describe the 630-run benchmark from environment and strategy; seed-grouped split (train 18 seeds, test 12). They show association, not causation, and do not predict new radios or channel models. Offline only.
- **CNN modulation classifier** (`src/dl/modulation_classifier.py`): trained on synthetic data only. The real test set (536 windows from 19 captures) shares one payload, one session and one antenna setup; windows from the same frame are not independent, so the per-capture vote (19/19) is the most conservative figure. Three classes only, with no "no signal" class, applied to the payload of frames the receiver had already found. On a damaged frame (8.8 % BER) it answered 16-QAM with 0.99 confidence, so its confidence is only reliable on normal signals. Not used by the controller.
- The cumulant baseline gets no CFO correction; with correction it would do better at high SNR.

## 6. Experimental design
- The 630-run benchmark is one pass over the full grid (3 environments × 30 seeds × 7 strategies); there are no repeated batches.
- `channel_switching` uses fixed QPSK, not fixed BPSK as in the 6 Nov plan.
- The switching penalty (0.15) and minimum utility gain (0.10) were chosen by hand. The sensitivity sweep shows 0.25 is better; the benchmark keeps 0.15 for consistency.

## 7. Software environment
- Three tests need `gnuradio.iio` (legacy GNU Radio TX backend) and one needs `torch`; with both installed, all 382 tests pass.
- The GNU Radio scripts need GNU Radio 3.10.

## 8. Corrections to the 22 Nov version
| 22 Nov statement | Status on 25 Nov (28 Nov where marked) |
|---|---|
| No RF transmission performed | OTA transmission done on 23 Nov (section 1.2) |
| Controller not run on hardware (25 Nov) | 28 Nov: closed-loop channel switching on the radios, 5 sessions (section 1.2) |
| No deep learning used | CNN classifier added (section 5) |
| Calibrated and cost-aware hybrid results identical (frozen calibration) | Not supported by the CSV: throughput 3.684 vs 2.972 at medium, 2.986 vs 2.224 at high |
| Environments defined as Low 0–5 dB, Medium 5–15 dB, High 15–30 dB SNR | The environments set the interference level (section 2.2) |
| Short-delay multipath (< 2 samples) breaks timing | The failures are at 2- and 4-sample echoes; 1-sample echoes did not fail (section 4) |

## 9. Reproduction
```bash
export PYTHONPATH=.
python src/multi_seed_experiment.py      # writes results/calibrated_multi_seed_results.csv
python src/paired_seed_analysis.py > results/paired_seed_analysis_current.txt
python src/ml_analysis.py                                   # -> results/ml/
python scripts/summarize_hardware_sweep.py
python scripts/train_modulation_classifier.py
python scripts/evaluate_dl_strict.py
python scripts/sensitivity_analysis.py
python scripts/summarize_closed_loop.py
python scripts/verify_closed_loop_captures.py   # needs the raw closed-loop captures
python -m pytest -q tests
```
