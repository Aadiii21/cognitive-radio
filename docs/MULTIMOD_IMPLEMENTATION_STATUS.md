# Multi-modulation implementation status

> **Status (25 Nov 2026):** this document is a historical record of the multi-modulation work plan as of 23 Nov; it is kept unchanged below. Final state: the over-the-air Pluto → RTL-SDR link was tested on 23 Nov (BPSK/QPSK/16-QAM BER matches theory), a DL modulation classifier was added (98.5 % on real OTA captures), and the hardware closed loop was removed from scope. Current documents: `MASTER_README.md`, `docs/RESULTS_AND_DISCUSSION.md`, `docs/LIMITATIONS.md` and the reports in `docs/reports/`.

## Added in this revision

- `src/radio/multimod_frame.py`: common framed waveform builder for BPSK, QPSK and
  Gray-coded 16-QAM. Each frame uses a known BPSK acquisition pilot, a 127-symbol
  sync word, a known payload and zero padding in a cyclic buffer.
- `src/radio/cognitive_controller.py`: measurement-driven baseline policy. It
  chooses the highest-SNR channel and maps SNR bands to BPSK, QPSK or 16-QAM.
- `scripts/run_multimod_experiment.py`: generates framed IQ and JSON metadata
  for all requested modulations and can emit a controller decision from measured
  per-channel SNR values.

## Still outstanding

This is not yet a completed physical TX/RX campaign.

- `src/radio/multimod_receiver.py` now decodes BPSK/QPSK/16-QAM
  `multimod_frame_v1` frames in synthetic-IQ tests (see docs/MULTIMOD_RECEIVER.md).
  It has not been tested on any RF capture.
- `map_bits` uint8 overflow fixed; regenerate earlier BPSK/QPSK multimod waveforms.
- The new controller is a baseline policy, not yet integrated with measured
  RTL-SDR scans and a live Pluto transmit/capture cycle.
- The current `scripts/run_hardware_experiment.py` is explicitly a conducted
  loopback runner. It must not be used to label an antenna-to-antenna test as
  conducted loopback or to bypass RF authorization/output requirements.
- `pipelines/integrated_pipeline.py` imports `src.controller_cost_aware` and
  `src.gnuradio_adapter`, which are not present in this archive. Those missing
  dependencies must be restored or the pipeline imports refactored before it
  can run.

## Generate framed waveforms

From the project root:

```bash
python scripts/run_multimod_experiment.py \
  --modulations BPSK QPSK 16QAM \
  --output-dir results/baseband/multimod
```

Optional controller decision using already measured SNR values:

```bash
python scripts/run_multimod_experiment.py \
  --modulations BPSK QPSK 16QAM \
  --snr 7.5 14.2 19.8
```

The SNR values in that example are illustrative. Use actual measured values
when evaluating the controller.

This preparation script does not transmit RF. Physical OTA operation requires
a separate, reviewed OTA implementation and applicable authorization.
