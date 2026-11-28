# cognitive-radio: master copy (2026-11-23, v5)

This single folder replaces both `~/projects/cognitive-radio` and
`~/Downloads/cognitive-radio-modified-files`. No other zip is needed.

## What it contains

- The complete original project, including `src/controller_cost_aware.py` and `src/gnuradio_adapter.py`, so `pipelines/integrated_pipeline.py` imports again.
- All hardware-path work from 23 Nov:
  - BPSK frame v2 and its receiver;
  - safe experiment runner: band check, Pluto readback, conducted-path and ≥ 30 dB attenuator gate, CW tone test, stream/cyclic TX;
  - RTL-SDR capture fixes, including no `-b 196608` anywhere;
  - SRO fix in `receiver_sync.py`;
  - multimodulation frame (with the `map_bits` fix), the multimod receiver and the updated controller;
  - synthetic BER curves.
- Your results from today: RX-only and TX captures in `results/hardware/`, OTA plots in `results/plots/`.

Removed: `results/baseband/prepared/qpsk_seed42.cf32/` and `16qam_seed42.cf32/`. They were folders holding byte-identical copies of `results/baseband/qpsk_seed42.cf32` and `16qam_seed42.cf32`.

## Install

```bash
mkdir -p ~/projects/final && cd ~/projects/final
unzip ~/Downloads/cognitive-radio-master.zip
cd cognitive-radio
source ~/miniforge3/bin/activate cognitive-radio
python -m pytest -q tests          # 326 tests
```

Then follow `docs/TRANSMISSION_DAY_RUNBOOK.md`.

## Key docs

| Doc | What |
|---|---|
| `docs/TRANSMISSION_DAY_RUNBOOK.md` | Step-by-step for today's conducted tests |
| `docs/MULTIMOD_RECEIVER.md` | Receiver design, synthetic results, issue register |
| `docs/HARDWARE_PATH_AUDIT.md` | Original audit of the TX/RX path |
| `docs/BPSK_RECEIVE_PATH_STAGE1.md` | BPSK receive path and runner changes |
| `docs/PHYSICAL_EXPERIMENT_CHECKLIST.md` | Pre-transmission checklist |

**Physical link status (23 Nov):** over-the-air link (antenna on the Pluto and on the RTL-SDR) measured for BPSK, QPSK and 16-QAM; see v5 below. The conducted (attenuator) path has not been used.


## v2 changes

- `pipelines/integrated_pipeline.py`: TX amplitude was applied twice (0.01 instead of 0.1). `PlutoTXAdapter.prepare()` now applies it exactly once. There is a regression test in `tests/test_adaptive_pipeline.py`.
- This copy matches `Cognitive_Radio_Project_Progress_and_Code_Guide` (20 Nov): expanded calibration coefficients, the 7-strategy / 630-run calibrated benchmark, and `results/figures/`. Do **not** use `cognitive-radio-main-merged.zip`: it is based on the 6 Nov snapshot and reverts those files.


## v3 changes (owner decisions, 23 Nov)

- **O1 (withdrawn in v5, see below):** the original `CalibratedCognitiveController` drives the hardware loop. New `src/radio/calibrated_hardware_bridge.py` feeds it receiver Es/N0 converted to the calibration SNR (`Es/N0 − 10·log10(4)`, from `gnuradio/measure_channel_snr.py`'s definition). It maps "16-QAM" ↔ "16QAM" and picks the matching `multimod_v2` waveform. The controller, calibration and benchmark files are unchanged; there are 9 tests.
- **O6:** `scripts/pluto_to_rtl_sdr_demo.py` and `scripts/test_pluto_tx_adapter.py` now refuse `--enable-rf`. Their software-only modes are unchanged.
- **O2:** GNU Radio is for synthetic data; Python controls the hardware.


## v4 changes (owner decisions, 23 Nov)

- **Pure-Python TX:** new `src/radio/pluto_pyadi_tx.py` (pyadi-iio, ADI's documented cyclic-buffer pattern) is the runner's default (`--tx-backend pyadi`).
  - Safe order: minimum gain first, then rate, bandwidth and LO, then the requested gain, then cyclic TX.
  - Stop: destroy the buffer, then minimum gain.
  - Samples are scaled once to int16 full scale (amplitude 0.1 = −20 dBFS).
  - The GNU Radio adapter is kept unchanged as `--tx-backend gnuradio`.
- **Pipeline RF disabled:** `pipelines/integrated_pipeline.py` refuses `--enable-rf` (hardware closed loop out of scope, v5). Its software modes are unchanged.
- **Runbook:** TX checks `import adi, iio` and uses pyadi by default.
- **Tests:** 348.


## v5 changes: project scope (owner decision, 23 Nov)

**Hardware closed loop removed from scope.** The hardware part of the project is open-loop transmission and BER measurement only. The cognitive controller stays a simulation result, exactly as in the 20 Nov guide.

- Removed `src/radio/calibrated_hardware_bridge.py` and `tests/test_calibrated_hardware_bridge.py` (the O1 adapter; nothing else imported it).
- `pipelines/integrated_pipeline.py`: RF path still refused; message now says the closed loop is out of scope. Software modes unchanged.
- Unchanged: the original controller, calibration, benchmark and simulation files; the runner, receivers and TX backends.
- Added `results/analysis/hardware_ber_sweep_day01.csv`: 15 OTA runs (antennas; the runs were started with `--rf-path conducted --attenuator-db 30`, but no cable or attenuator was used) (BPSK/QPSK/16-QAM × Pluto attenuation 0–20 dB, RX gain 28, 4,096 bits each), mean receiver Es/N0, bit errors, measured BER and AWGN theory BER. Measured BER is within about 1–2.5× of theory. Each zero-error cell only bounds BER below about 7.3e-4 (95 %).
- **OTA is the project's RF path.** The runner now accepts `--rf-path ota --antenna-separation-m <m>` (recorded in every result and sidecar; `mode` becomes `physical_ota_loopback` / `physical_ota_tone_test`). `--rf-path conducted --attenuator-db >=30` is kept. The 865–868 MHz occupied-band check applies to both.
- `scripts/annotate_rf_path.py`: adds an `rf_path_correction` block to result JSONs and sidecars in a time window, leaving the original field. Use it once for the 23 Nov runs (13:50–14:01), which were recorded as conducted.
- Tests: 343.

## v7 changes (25 Nov): flowcharts, DL classifier, part reports

- **Flowcharts** (`python scripts/make_flowcharts.py`, needs graphviz): `docs/flowcharts/01_project_workflow`, `02–04_code_map_part1..3`, `05_code_map_all` (.svg/.png/.dot).
- **DL modulation classifier** (`src/dl/modulation_classifier.py`, `python scripts/train_modulation_classifier.py`, needs `pip install torch`): 1-D CNN, 85,859 parameters, trained on 24,000 synthetic windows through a simulated RTL-SDR chain; tested on the 536 payload windows of the 19 real OTA captures: **98.5 % per window, 19/19 captures** (cumulant + random-forest baseline: 62.9 %). Outputs in `results/dl/`.
- **Hardware BER from the run records** (`python scripts/summarize_hardware_sweep.py`): `results/analysis/hardware_ber_runs.csv` (19 runs) and `results/figures/hardware_ber_vs_theory.png`. Matches the log-derived sweep CSV (two values differ by 0.1 dB from log rounding; the JSON values are exact).
- `scripts/plot_ber_synthetic.py` → `results/figures/ber_vs_esn0_synthetic.png`.
- `results/paired_seed_analysis_current.txt`: the unchanged `paired_seed_analysis.py` re-run on the current 630-row CSV. The older `paired_seed_analysis_v3.txt` and the 20 Nov guide's `channel_switching` rows come from an earlier run and do not match the CSV; the calibrated-hybrid comparisons are identical in both. No data was changed.
- **Part reports** (`node docs/reports/build_reports.js`): `docs/reports/Part1_Simulation_Control_ML_Report.docx`, `Part2_PHY_Calibration_Receivers_DL_Report.docx`, `Part3_SDR_Hardware_OTA_Report.docx`.
- Tests: `tests/test_dl_and_summary.py` (6). Total 349.

## v8 changes (25 Nov): master report, docs and GitHub preparation

- `docs/reports/Master_Report.docx` (whole project, 10 pages) added; all four reports built by `node docs/reports/build_reports.js`.
- `README.md` rewritten as the GitHub front page (20 Nov version kept in `docs/archive/`); `requirements.txt` added; `.gitignore` extended (lock files, `node_modules/`, stray `/main`).
- `docs/RESULTS_AND_DISCUSSION.md`: section 1 tables regenerated from the 630-run CSV (the 22 Nov tables did not match it), hardware / limitations / conclusion sections updated; old version in `docs/archive/`.
- `docs/LIMITATIONS.md` rewritten for the final state, with a table of corrections to the 22 Nov version (kept in `docs/archive/`).
- Historical docs (status, hand-off, audits, checklists) kept unchanged, each with a dated status note at the top; `docs/README.md` indexes all documents.
- Analysis commands in the docs simplified: `multi_seed_experiment.py`, `paired_seed_analysis.py` and `ml_analysis.py` take no command-line arguments (they use fixed default paths).

## v9 changes (26 Nov): confidence intervals, sensitivity, robustness, stricter DL checks

- `scripts/summarize_hardware_sweep.py`: exact 95 % Clopper–Pearson interval and implied implementation loss per run; error bars in `results/figures/hardware_ber_vs_theory.png`. 4 of 9 runs with errors contain theory; implied loss −0.2 to +0.75 dB above 4 dB Es/N0.
- `scripts/sensitivity_analysis.py` (reproduces all 630 benchmark runs exactly with `--check`): switching-penalty sweep 0–0.6, 1–2 dB implementation loss, safety margin. Outputs in `results/sensitivity/`. The calibrated hybrid leads at every penalty; 0.25 beats the benchmark's 0.15; under 1 dB loss it still leads, and a 1 dB margin keeps PDR at 0.997 / 0.988. The benchmark itself is unchanged.
- `scripts/evaluate_dl_strict.py`: capture-level bootstrap CI 96.2–99.8 %; all errors below 0.9 confidence; 36/36 on the unseen BPSK v2 format; one damaged frame confidently misclassified. Outputs `results/dl/strict_evaluation.json`, `bpsk_v2_predictions.csv`.
- Reports, flowcharts, README and docs updated. Tests: `tests/test_sensitivity_and_stats.py` (6); total 355.

## v10 changes (26 Nov): closed-loop channel-switching demo

- `scripts/run_channel_switching_demo.py`: every round the Pluto probes three channels (865.7 / 866.5 / 867.3 MHz), the RTL-SDR measures Es/N0, the unchanged `CalibratedCognitiveController` picks channel and modulation, and the Pluto transmits a data frame there. Channel quality is scripted by Pluto TX attenuation (no second transmitter). Same safety gates as the experiment runner, plus a TX-LO powerdown check. Modes: `--simulate` (no hardware), `--dry-run` (checks only), `--enable-rf --rf-path ota --antenna-separation-m D`.
- Simulated session: 3 switches, best channel 12/12 rounds, 0 data bit errors (`results/hardware/closed_loop_simulated/`, figure `results/figures/channel_switching_simulated.png`). **Real-radio run pending** (runbook: `docs/TRANSMISSION_DAY_RUNBOOK.md`, first section).
- This reverses the 23 Nov decision to leave the closed loop out of scope (owner request, 26 Nov). Tests: `tests/test_channel_switching_demo.py` (14); total 369.

## v10.1–v11 changes (28 Nov): closed loop run on the radios

- v10.1 / v10.2 fixes found during the first attempts: the Pluto TX bandwidth is now passed explicitly (`--tx-bandwidth`, default 1 MHz; `bandwidth=None` had stopped the first attempt before anything was transmitted); a clear message when the Pluto does not answer; line-buffered output with one progress line per burst and a realistic time estimate.
- v10.3: phase E (all poor) added to the default schedule; `--margin-db` safety margin; `scripts/scan_band.py` (passive rtl_power scan, refuses while the TX LO is on); `scripts/summarize_closed_loop.py` (pooled results with exact 95 % intervals).
- v11: `scripts/verify_closed_loop_captures.py` (offline re-decode of every capture, readback check, decision replay).
- **Real-radio results (5 sessions, 72 rounds, 288 bursts, antennas 1.5 m):** highest-probe-Es/N0 channel selected in 72 / 72 rounds; 15 / 15 needed switches made in the first round, 0 unnecessary; 16-QAM / QPSK / BPSK used as conditions worsened; data BER per modulation and safety-margin comparison in Part 3, Section 5.9. Audit: all 288 captures re-decode to the logged values, all readbacks match, all 72 decisions replay.
- Band scan: the three channels within 0.6 dB of the band floor, no wideband activity. Channel quality differences in the demo come from scripted TX power only (stated in every output and report).
- Faculty review point recorded: the GNU Radio software-in-the-loop "channels" are one test tone with different noise levels; described as such in Part 1 §5.4, Part 3 §5.10, the master report and `docs/LIMITATIONS.md`. The calibration data are unaffected.
- Raw closed-loop captures (about 330 MB) excluded from git via `.gitignore`; sidecars, rounds, session records and plots are committed. Two aborted attempts (07:11, 07:13) are kept and excluded from the summary with their reason.
- Tests: demo 19, scan 4, summary 2, audit 2; total 382.

