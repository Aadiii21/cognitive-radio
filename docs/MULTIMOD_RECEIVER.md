# multimod_frame_v1 receiver and audit (2026-11-23)

> **Status (25 Nov 2026):** this document is a historical record of the multimod receiver design and issue register (23 Nov); it is kept unchanged below. Final state: the over-the-air Pluto → RTL-SDR link was tested on 23 Nov (BPSK/QPSK/16-QAM BER matches theory), a DL modulation classifier was added (98.5 % on real OTA captures), and the hardware closed loop was removed from scope. Current documents: `MASTER_README.md`, `docs/RESULTS_AND_DISCUSSION.md`, `docs/LIMITATIONS.md` and the reports in `docs/reports/`.

**Evidence level: synthetic IQ only.** No RF was transmitted. Nothing here is
conducted or over-the-air (OTA) evidence.

## Files changed

| File | Change | Evidence |
|---|---|---|
| `src/radio/multimod_frame.py` | `map_bits` uses signed ints. `1 - 2*b` on `uint8` wrapped to 255, so every "1" bit was sent as +255 (BPSK) or +180 (QPSK). The pilot comment is corrected | Noise-free round trip before the fix: 646/1024 (BPSK) and 638/1024 (QPSK) bit errors; 16-QAM unaffected (level table) |
| `scripts/run_multimod_experiment.py` | Adds the project root to `sys.path` | Without it: `ModuleNotFoundError: No module named 'src'` unless `PYTHONPATH` is set |
| `src/radio/multimod_receiver.py` (new) | Receiver for `multimod_frame_v1` | Tests below |
| `tests/test_multimod_receiver.py` (new) | 61 synthetic-IQ tests | — |

Not modified: `bpsk_receiver.py`, `bpsk_frame.py`, `pluto_tx_adapter.py`,
`run_hardware_experiment.py`, the pipeline, the controller.

**Regenerate** `results/baseband/multimod/` and `results/baseband/controller_test/`.
The BPSK and QPSK files there were produced before the `map_bits` fix.

## Receiver chain (`receive_multimod`)

1. Validation.
2. DC removal, estimated from the quiet zero-padding blocks. The whole-capture mean is biased by the DC pilot near 0 Hz CFO: it cost 7–14 dB of noiseless SNR.
3. Rate conversion with the actual TX/RX rates.
4. RRC matched filter.
5. Pilot acquisition: lag-1-symbol autocorrelation, energy-weighted. Gives the coarse CFO, unambiguous to ±Rs/2.
6. Fine CFO with a 16-symbol lag. The coarse error at 4 dB was about 5 kHz, which rotated the sync word by about 7.7 rad and dropped frames.
7. 127-symbol sync correlation, normalised, threshold 0.6. The sync word defines the frame boundary.
8. Fractional timing.
9. Gain and phase from the 191 known symbols.
10. Block-wise decision-directed phase/frequency tracker. A single linear phase fit extrapolated over long payloads gave BPSK BER 6–25× theory.
11. Amplitude refit.
12. Demapping.
13. Payload-only BER, data-aided EVM and SNR, per frame and aggregate.

Truncated frames are counted and not decoded. With no frame detected, there is no BER.

Modulation and payload length are **inputs** (`MultimodFrameSpec`, or `from_metadata` for offline tests). There is no in-band header and no blind modulation detection.

## Measured (synthetic, fixed seeds)

CFO +23 kHz, 2.083333 → 2.048 MS/s, AWGN, 256-byte payload, about 115 k bits per point:

| Modulation | Es/N0 (dB) | BER | Theory | Ratio | SNR estimate (dB) |
|---|---|---|---|---|---|
| BPSK | 2 / 4 / 6 | 3.97e-2 / 1.32e-2 / 2.50e-3 | 3.75e-2 / 1.25e-2 / 2.39e-3 | 1.06 / 1.06 / 1.05 | 2.20 / 4.08 / 6.05 |
| QPSK | 6 / 8 / 10 | 2.47e-2 / 6.48e-3 / 9.68e-4 | 2.30e-2 / 6.00e-3 / 7.83e-4 | 1.07 / 1.08 / 1.24 | 6.05 / 8.01 / 10.01 |
| 16-QAM | 12 / 14 / 16 | 3.07e-2 / 1.00e-2 / 1.84e-3 | 2.81e-2 / 9.38e-3 / 1.79e-3 | 1.09 / 1.07 / 1.03 | 11.92 / 13.95 / 15.97 |

Detection (QPSK, CFO −41 kHz), complete frames detected / available:

| Es/N0 | −2 dB | 0 dB | 2 dB | 4 dB | 6 dB | 8 dB |
|---|---|---|---|---|---|---|
| Detected | 11/42 | 35/42 | 42/42 | 42/42 | 42/42 | 42/42 |

False alarms: 0 frames in 30 noise-only captures; highest sync metric 0.317 (threshold 0.6).

Noiseless payload SNR: 41.9 / 42.0 / 43.1 dB. An ideal matched filter on the same waveform gives 43.1 / 42.8 / 42.9 dB.

The 16-QAM theory is the nearest-neighbour Gray approximation.

## Issue register (prioritised)

| Sev. | Issue | Evidence | Status |
|---|---|---|---|
| High | `map_bits` uint8 wrap (BPSK/QPSK) | Above | **Fixed** |
| High | `PlutoTXAdapter.build_flowgraph` uses `vector_source_c(repeat=False)`. The flowgraph can finish after one buffer push, ending TX before the RTL-SDR captures | Source; GNU Radio list reports for non-repeating vector sources | **Fixed in software** (2026-11-23): `repeat=True`, plus `--tx-mode stream|cyclic` (stream is the default). Verify on air with the tone test |
| High | The 11:34 and 12:02 captures contain no burst: raw range 125–130, RMS 0.86 LSB, identical to RX-only. Every manual-gain (19.7/28 dB) capture in the original repo looks like an idle ADC, including at 100 MHz, while gain-0 (auto) captures show signals | Analysis of the `.cu8` files | Open. Receive-only gain comparison needed |
| High | Those two runs are recorded as `mode: physical_conducted_loopback`, but the setup was antenna-to-antenna without an attenuator | Result JSONs, `ota_*` plots, handoff §2.2 | Open. Annotate the records; do not cite them as conducted tests |
| Medium | `integrated_pipeline` scales amplitude twice: `prepare_waveform()` multiplies by `amplitude_scale` (L177), then `prepare(waveform)` (L413) applies the default scale again → 0.01 (−40 dB) instead of 0.1 | Source | Open (Phase E) |
| Medium | `integrated_pipeline` imports `src.controller_cost_aware` and `src.gnuradio_adapter`, which are absent from this archive | Source / tree | Open. Check the active tree |
| Medium | `integrated_pipeline` uses unframed `generate_waveform()` output; `PlutoTXAdapter.close()` sets `_closed`, so one adapter can run once | Source | Out of scope (hardware closed loop removed, 2026-11-23). Pipeline RF path disabled |
| Medium | `CognitiveRadioController.decide()` raises `IndexError` if the channel list shrinks during dwell; below `bpsk_min_db` it still returns BPSK (`bpsk_min_db` is unused); its first call assumes channel 0 is current | Executed | **Fixed**: `initial` and `insufficient_snr` actions, shrinking channel list handled, hysteresis added, thresholds from BER curves (`from_ber_curve`) |
| Low | `results/baseband/prepared/qpsk_seed42.cf32/` and `16qam_seed42.cf32/` are directories that contain the files | Tree | Open |
| Low | `scripts/pluto_to_rtl_sdr_demo.py`, `scripts/test_pluto_tx_adapter.py`: legacy `--enable-rf` paths (500 MHz default, blocking TX) | Source | Open. Do not use |

## Known limitations

* The 64-symbol pilot is only for CFO; timing comes from the sync word. The pilot and sync are hard-coded to the `multimod_frame_v1` layout.
* No channel equalisation (flat channel assumed); no coding or CRC; no in-band header.
* CFO range ±100 kHz by default (hard limit ±Rs/2 = 260 kHz).
* Detection falls off below 2 dB Es/N0 (35/42 frames at 0 dB).
* The phase tracker's gains (32-symbol blocks, frequency gain 0.15) were tuned on AWGN only.

## Next milestone

Phase C from the handoff: BER-vs-SNR curves from this receiver → controller thresholds with hysteresis. Fix the controller edge cases above.

No live RF until the open High items have a reviewed plan.


## Update — transmission preparation (2026-11-23)

* `pluto_tx_adapter.py`: `vector_source_c(repeat=True)`; `cyclic` parameter; stream mode uses a non-cyclic sink with 32 768-sample buffers.
* `run_hardware_experiment.py`:
  * accepts `multimod_frame_v1` waveforms (dispatches to `receive_multimod`);
  * `--tone` CW test that compares TX-on vs TX-off captures at the tone bin;
  * `--tx-mode stream|cyclic`;
  * transmission requires `--rf-path conducted --attenuator-db >= 30`;
  * `--rx-gain 0` selects automatic gain and is recorded.
* `cognitive_controller.py`: see the issue register.
* `scripts/ber_curves.py`: synthetic BER-vs-Es/N0 curves and thresholds (BER ≤ 1e-3: BPSK 6.80, QPSK 9.93, 16-QAM 16.67 dB).
* Runbook: `docs/TRANSMISSION_DAY_RUNBOOK.md`.
