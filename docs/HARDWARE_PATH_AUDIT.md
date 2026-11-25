# Hardware TX/RX Path Audit — 2026-11-23

> **Status (25 Nov 2026):** this document is a historical record of the hardware-path audit made before the OTA session; it is kept unchanged below. Final state: the over-the-air Pluto → RTL-SDR link was tested on 23 Nov (BPSK/QPSK/16-QAM BER matches theory), a DL modulation classifier was added (98.5 % on real OTA captures), and the hardware closed loop was removed from scope. Current documents: `MASTER_README.md`, `docs/RESULTS_AND_DISCUSSION.md`, `docs/LIMITATIONS.md` and the reports in `docs/reports/`.

Scope: `scripts/run_hardware_experiment.py`, `src/radio/pluto_tx_adapter.py`,
`src/radio/rtl_capture.py`, `src/radio/rtl_sdr_sensor.py`,
`src/radio/bpsk_receiver.py`, `src/receiver_sync.py`,
`src/radio/waveform_generator.py`, prepared waveforms and JSON under
`results/baseband/prepared/` and `results/hardware/`.

Audit environment: Python 3.13, NumPy 2.5.3, SciPy 1.18.1, **no GNU Radio, no
SDR hardware**. Nothing below is a hardware result.

Baseline test run (unmodified tree): 158 passed, 3 failed
(`tests/test_pluto_tx_adapter.py`, all `module 'gnuradio' has no attribute 'iio'`).

## A. Confirmed defects (reproduced or proven by reading/executing the code)

| # | Location | Defect | Evidence |
|---|---|---|---|
| A1 | runner `run_ber_calculation()` | Returns undefined `errors`, `total_bits`; `ber = 0.5` placeholder | pyflakes: undefined names L201 |
| A2 | runner `main()` | `load_waveform()` return discarded; `iq` undefined at `transmitter.prepare(iq, …)` | pyflakes L385 |
| A3 | runner `main()` | `payload_bytes`, `received_iq`, `sync_result` never created — the receive pipeline is missing, not mistyped | pyflakes L401–403 |
| A4 | runner `run_rtl_sdr_capture()` | Reloads the **TX** file and saves it as `capture_*.cf32` | L303, L311 |
| A5 | runner `run_experiment_ber_calculation()` | Thresholds every sample (4 SPS ignored), takes bits `[:512]` (preamble not removed), no timing/phase used | L229–239 |
| A6 | runner `main()` | TX then RX are **sequential**: `transmit()` blocks ~60 s, stops and closes the Pluto, *then* the RTL-SDR captures → the capture can never contain the signal | `run_pluto_tx` → `transmitter.transmit()` → `close()` |
| A7 | runner `main()` | `RTLSDRReceiver(sample_rate=256000, capture_samples=2048)` — 256 kS/s cannot contain a ~700 kHz-wide signal; 2048 samples = 8 ms | L393–397 |
| A8 | runner `main()` | `receiver.measure()` called without `init_device()` → always `RuntimeError("Device not initialized")` | adapter L520 |
| A9 | runner `check_rf_safety_confirmed()` | Falls off the end (returns `None`) when the checklist passes → RF path always aborts | L285–286 |
| A10 | runner `main()` | `PlutoTXAdapter()` built with defaults: URI `usb:3.2.5` (handoff: working URI is `ip:192.168.2.1`), sample rate 2.4 MS/s (waveform metadata says 2.048 MS/s) | adapter L142–143 |
| A11 | runner | Results JSON written twice; second overwrites first and drops `ber_calculation`; `payload_bytes: 64`, `preamble_bits_detected: 64` are hardcoded, not measured | L412–463 |
| A12 | runner `load_waveform()` | Ignores modulation/seed args, hardcodes path and `sample_rate_sps: 2048000`; never reads the JSON metadata | L134–136 |
| A13 | adapter `RTLSDRReceiver.detect_signal()` | `noise = median(psd*0.1)` ⇒ "SNR" ≈ 10 dB + mean/median ratio, always > 0 ⇒ `detected` is always True; `ber` and `pdr` are formulae of that number, not measurements | L612–629 |
| A14 | adapter `build_flowgraph()` | Sink is **cyclic** with buffer 32 768 samples, waveform is 262 144 samples. In gr-iio cyclic mode only the first buffer is repeated, so the frame would be truncated to the first 12.5 % | L247–252 |
| A15 | `bpsk_receiver.py` | On the clean prepared TX waveform `run_receiver_pipeline()` returns `success=True, ber=0.693` (BER > 0.5): decision polarity inverted (`real >= 0 → 1` while mapping is 0→+1), payload placed at bits `[0:512]` in the reference (should be `[64:576]`), MSB-first bit order (waveform is LSB-first), sampling at fixed indices ignoring detected delay, 1-sample-per-symbol reference correlated against a 4-SPS signal | executed |
| A16 | `bpsk_receiver.py`, `receiver_sync.apply_sro_correction()` | Hardcoded `Fraction(2083333, 2048000)` regardless of actual rates; `receiver_sync` ignores its own `sro_ppm` estimate except for the `== 0` test | source |
| A17 | `bpsk_joined_seed42_tx.cf32` | Despite its name it is **byte-identical to `bpsk_seed42_tx.cf32`** (random seed-42 BPSK). It contains no preamble or payload. Transmitting it could never yield a payload BER | `np.allclose` = True |
| A18 | `bpsk_joined_seed42.cf32` frame design | Preamble `0101…` with `|corr|` timing gives a peak of 129.9 vs **129.1 at ±1 symbol** (noise-free). A 1-symbol slip also inverts polarity. Frame timing is not reliably decidable under any noise | executed (`/tmp/pre.py` equivalent in tests) |
| A19 | `bpsk_joined_seed42.cf32` padding | All 64 960 padding symbols are bit 0 → constant +1 → 99 % of the transmission is an unmodulated carrier | demodulated file |
| A20 | Bit order | Joined waveform uses **LSB-first** per byte (0 errors LSB vs 190 MSB). Runner's BER uses LSB-first (consistent); `bpsk_receiver.bytes_to_bits` uses MSB-first (inconsistent). Not documented anywhere in metadata | executed |

## B. Suspected problems (need verification on the Arch machine / hardware)

| # | Item | How to verify |
|---|---|---|
| B1 | **Resolved 2026-11-23:** now `[True, True]` (GR 3.10 GRC Pluto sink generates `fmcomms2_sink_fc32(uri, [True, True], …)`; FMComms2 uses `[tx1, tx1, tx2, tx2]` → one flag per I/Q rail). Was: `PlutoTXAdapter` passes `ch_en=[True]` to `fmcomms2_sink_fc32`; GRC's Pluto sink template uses one bool per I/Q *rail* (`[True, True]` for TX1) | `grep -n fmcomms2_sink /usr/share/gnuradio/grc/blocks/iio_pluto_sink.block.yml` |
| B2 | `self._top_block.wait(timeout=60)` — GNU Radio 3.10 `top_block.wait()` takes no timeout | `python -c "from gnuradio import gr; help(gr.top_block.wait)"` |
| B3 | Payload bytes are 0–7 only (mean 3.88, var 1.64): consistent with *sum of 8 bits* instead of *packing 8 bits*. 62.5 % of payload bits are always 0. The generating script is not in the repo | find the script that wrote `combined_payload.json` |
| B4 | Pluto rate 2 048 000: allowed only if the AD9361 FIR interpolator is loaded (gr-iio "Auto" filter). `sampling_frequency_available = [2083333 1 61440000]` is what is reported *without* FIR | `iio_attr -u ip:192.168.2.1 -o -c ad9361-phy voltage0 sampling_frequency` while transmitting (`-o` = output/TX channel; without it the RX `voltage0` may be read). Now automated by the runner. |
| B5 | 30.72 MS/s readback = Pluto power-on default; the adapter only sets the rate inside `transmit()`, so any earlier readback is meaningless | read back *while* TX is running |
| B6 | `rtl_sdr` exit status after SIGINT in `capture_exact` (non-zero would turn a good capture into an error) | run one capture, inspect `returncode` |
| B7 | RF level: −50 dBm estimate in `experiment_config.json` assumes "9.5 dBm" Pluto output; RTL-SDR at 28 dB gain may clip well below its damage level | check raw 8-bit capture for samples at 0/255 (now reported by the receiver) |

## C. Configuration inconsistencies

* Sample rates: `experiment_config.json` 2.048 MS/s; `bpsk_joined_seed42.json` 2.048; `bpsk_joined_seed42_tx.json` 2.4; adapter default 2.4; runner comment 2.083333; `bpsk_receiver` constants 2.083333 (TX) / 2.048 (RX); runner RX 0.256.
* RX bandwidth 180 kHz in config; signal occupies Rs(1+β) ≈ 0.70 MHz (at 2.083 MS/s, 4 SPS).
* Centre 865.000 MHz with ±0.35 MHz occupied bandwidth puts ~half the signal **below 865 MHz**, i.e. outside the 865–868 MHz band being considered. Even for conducted tests, choose a centre such that the whole occupied band is inside (e.g. 866.0–866.5 MHz), and separately check the band's bandwidth/power/duty-cycle conditions.
* Two RRC generators: `waveform_generator.py` uses `convolve(mode="same")` (group delay removed); `pluto_tx_adapter.generate_waveform` uses `np.convolve` default (`full` → length +40, delay 20 samples). Same function names, different alignment.

## D. Missing implementation steps

1. A frame definition shared by TX generator and receiver (preamble, payload length, bit order, padding, SPS, β, span).
2. Non-blocking TX (start → settle → capture → stop).
3. RX capture that records the *actual* RTL rate (`rtl_sdr` prints "Exact sample rate is …") and clipping statistics.
4. Receiver: DC removal, rate conversion from actual TX/RX rates, matched filter, CFO acquisition, frame detection with a detection threshold, fractional timing, data-aided phase, decision-directed phase tracking, payload extraction, BER over payload bits only, data-aided SNR estimate.
5. Result records that distinguish "no frame detected" from "BER measured".

## E. Hardware dependencies (cannot be exercised here)

GNU Radio `gnuradio.iio`, Pluto at `ip:192.168.2.1`, `rtl_sdr` binary, a conducted path with suitable 50 Ω attenuation, operator confirmation.

## F. Minimal ordered repair plan

1. `src/radio/bpsk_frame.py`: one frame spec (PN preamble, zero-amplitude padding, explicit LSB-first bit order) + generator writing a new `bpsk_frame_v2_seed*.cf32/.json`. Old files untouched.
2. Rebuild `src/radio/bpsk_receiver.py` around that spec; test with software impairments (rate mismatch, CFO, fractional delay, phase, DC, 8-bit quantisation, AWGN, noise-only).
3. `PlutoTXAdapter`: add `start()`/`stop()`, cyclic buffer = waveform length, `uri`/`sample_rate` passed in. `transmit()` kept for compatibility.
4. Runner: load waveform + metadata + payload, safety gate (checklist **and** typed operator confirmation), start TX, capture real RX IQ, stop TX, save RX IQ + sidecar, run receiver, write one result file; `--rx-file` mode to re-process a saved capture offline.
5. Hardware: conducted BPSK loopback; only after frame detection and payload recovery is reliable, report BER.

Not changed: channel model, controllers, metrics, ML analysis, simulation dataset, `receiver_sync.py` (still used by the simulation validation scripts; its fixed-ratio SRO path is listed above but the new hardware receiver does not depend on it).
