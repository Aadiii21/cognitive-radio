const { P, H1, H2, B, NUM, CODE, NOTE, T, FIG, cover, build, resetFig } = require("./lib");

module.exports = function part2() {
  resetFig();
  const c = [];
  c.push(...cover(2, "Physical Layer, Calibration, Receivers and DL Classifier",
    "The signal-processing side of the cognitive radio: the GNU Radio packet receiver and its calibration, the noise-to-SNR mapping, the synchronisation work, the framed BPSK/QPSK/16-QAM waveforms and receivers used on air, the synthetic BER curves that set the switching thresholds, and the deep-learning modulation classifier."));

  c.push(H1("1. Purpose of this part"));
  c.push(P("The controller in Part 1 needs to know **how likely a packet is to succeed** for each modulation at a given channel quality. Part 2 answers that with real signal processing rather than a hand-written formula: it builds receivers, measures packet success and bit error rate under controlled noise, and turns the measurements into models and thresholds. It also builds the waveforms and receivers that Part 3 used over the air, and adds a deep-learning model that recognises the modulation directly from raw IQ samples."));
  c.push(...B([
    "**To Part 1:** logistic packet-success models (per modulation) and the SNR ↔ noise-voltage calibration used by the calibrated controller.",
    "**To Part 3:** the framed TX waveforms, the BPSK and multi-modulation receivers, and the synthetic BER curves that the hardware results are compared against.",
    "**From Part 3:** real over-the-air captures, used as the test set for the DL classifier.",
  ]));

  c.push(H1("2. Where this part fits"));
  c.push(...FIG("docs/flowcharts/01_project_workflow.png", "Project workflow. Green: Part 2 (this report). Blue: Part 1. Orange: Part 3."));

  c.push(H1("3. Code in this part"));
  c.push(...FIG("docs/flowcharts/03_code_map_part2.png", "Part 2 code → outputs map.", 6.27, 7.6));
  c.push(H2("3.1 Code files and their role"));
  c.push(...T(["File(s)", "Role"], [
    ["gnuradio/packet_receiver_general.py", "GNU Radio packet receiver for BPSK/QPSK/16-QAM: 400 training + 64 sync + 2,000 payload symbols, 16 pilots every 128 symbols, 4 samples/symbol, RRC roll-off 0.35, 32-filter polyphase timing recovery, carrier recovery and pilot correction. A packet succeeds if sync score ≥ 0.80, SER ≤ 0.01 and BER ≤ 0.005. (packet_receiver_test*.py are earlier versions.)"],
    ["gnuradio/first_signal, packet_link_test, ideal_16qam_test, pulse_shaping / timing_recovery / carrier_recovery_16qam_test, channel_transparency_test, channel_receiver_alignment_test, diagnose_stage_decisions", "Step-by-step development checks: signal path, end-to-end link, then each receiver stage on its own."],
    ["gnuradio/calibrate_receiver.py, refine_calibration.py, expand_calibration.py", "Run the receiver many times at each noise voltage and record packet success: coarse, refined around the transition, then expanded."],
    ["gnuradio/analyze_calibration.py, validate_logistic_models.py", "Fit P(success | v) = 1 / (1 + exp(−(a + b·v))) per modulation; leave-one-seed-out validation."],
    ["gnuradio/measure_channel_snr.py, extend_channel_snr.py, extend_modulation_snr.py, snr_measurement, receiver_snr_estimator, test_three_channel_estimators.py", "Matched clean/noisy paths: subtracting the clean output isolates the added noise, giving SNR in dB for each noise voltage; three-channel estimator check."],
    ["src/noise_calibration.py", "Interpolates the measured SNR ↔ noise-voltage table so the controller can convert SNR to the receiver's noise voltage (clips at the measured bounds)."],
    ["src/generate_faculty_results.py", "Calibration figures (packet success vs noise; SNR vs noise)."],
    ["src/receiver_sync.py, multipath_channel.py, validate_*_sync.py, validate_*_correction.py, validate_multipath*.py, validate_reference_snr.py", "Synchronisation pipeline (timing, CFO, SRO) and its validation under each impairment, including two-path multipath."],
    ["src/radio/waveform_generator.py, bpsk_frame.py, multimod_frame.py, scripts/run_multimod_experiment.py", "TX waveforms: RRC pulse shaping, BPSK frame v2 (64-chip preamble + 512 payload bits) and multimod frame v1 (64-symbol pilot + 127-chip sync word + 1,024 payload bits) for BPSK, QPSK and Gray 16-QAM."],
    ["src/radio/bpsk_receiver.py, multimod_receiver.py", "Burst receivers for the on-air frames: DC removal, rate conversion (RX 2.048 → TX 2.083 MS/s), pilot-based coarse and fine CFO, sync-word timing, decision-directed phase tracking, BER and data-aided Es/N0."],
    ["scripts/ber_curves.py, plot_ber_synthetic.py\nsrc/radio/cognitive_controller.py", "BER vs Es/N0 of the multimod receiver on synthetic frames; thresholds for BER ≤ 10⁻³; a threshold controller that reads them."],
    ["src/dl/modulation_classifier.py\nscripts/train_modulation_classifier.py", "**New:** 1-D CNN that classifies BPSK / QPSK / 16-QAM from 512 raw IQ samples; trained on synthetic data, tested on the real OTA captures; compared with a classical baseline."],
  ], [0.38, 0.62], 2));

  c.push(H1("4. Outputs and what they signify"));
  c.push(...T(["Output", "Produced by", "Contents", "What it signifies"], [
    ["results/packet_receiver_{bpsk,qpsk,16qam}_validation.csv, packet_receiver_seed_sweep.csv", "packet_receiver_* scripts", "Per-seed sync score, SER, BER, success", "The receiver decodes all three modulations"],
    ["results/equal_power_modulation_calibration.csv (330 trials), refined_… (930), expanded_… (2,070)", "calibrate / refine / expand_calibration.py", "Packet outcome vs noise voltage, per modulation and seed", "Measured packet-success curves"],
    ["Logistic coefficients and LOSO scores (console)", "analyze_calibration.py, validate_logistic_models.py", "a, b per modulation; Brier, log loss, accuracy", "The model Part 1's calibrated controller uses, and how trustworthy it is"],
    ["results/channel_snr_calibration.csv (1,530), channel_snr_extension*.csv", "measure / extend_*_snr.py", "Noise voltage vs measured SNR", "Converts the controller's SNR into the receiver's noise setting"],
    ["results/figures/01_packet_success_calibration.png, 02_snr_noise_comparison.png", "generate_faculty_results.py", "Calibration plots", "Visual check of both calibrations"],
    ["results/synchronization/** and *_sync_validation_*.csv", "validate_* scripts", "Timing, CFO, SRO and SNR errors per trial", "Where synchronisation works and where it breaks"],
    ["results/baseband/prepared/bpsk_frame_v2_seed42.*, results/baseband/multimod_v2/*", "frame builders", "complex64 IQ + JSON metadata (payload, layout)", "The exact signals transmitted in Part 3"],
    ["results/analysis/ber_vs_snr_multimod_synthetic.csv, controller_thresholds_synthetic.json, results/figures/ber_vs_esn0_synthetic.png", "ber_curves.py, plot_ber_synthetic.py", "BER per Es/N0 with theory; thresholds", "The receiver matches theory; switching points 6.8 / 9.9 / 16.7 dB"],
    ["results/dl/ (modulation_cnn.pt, metrics.json, accuracy_vs_esn0.*, confusion_*.png, real_predictions.csv, real_by_capture.csv, training_history.csv)", "train_modulation_classifier.py", "Trained model, accuracy curves, confusion matrices, per-window and per-capture predictions", "Deep learning can identify the modulation from raw over-the-air IQ"],
  ], [0.3, 0.2, 0.26, 0.24], 2));

  c.push(H1("5. Results"));
  c.push(H2("5.1 Packet receiver"));
  c.push(P("On ten seeds per modulation, every packet was decoded successfully (sync score ≥ 0.994); BPSK and QPSK had zero bit errors and 16-QAM a mean BER of 7.5 × 10⁻⁵. Before calibration the constellations were normalised to equal average power: QPSK originally had 6.02 dB more symbol power than BPSK and 16-QAM, which would have made the noise comparison unfair."));
  c.push(H2("5.2 Packet-success calibration"));
  c.push(P("The expanded calibration (3 modulations × 23 noise levels × 30 seeds = 2,070 trials) gives these logistic models, where v is the GNU Radio noise voltage:"));
  c.push(...T(["Modulation", "a", "b", "v at 90 % success", "v at 50 %", "v at 10 %", "LOSO Brier", "LOSO accuracy"], [
    ["BPSK", "42.198", "−153.935", "0.2599", "0.2741", "0.2884", "0.0157", "97.97 %"],
    ["QPSK", "180.956", "−994.912", "0.1797", "0.1819", "0.1841", "0.0054", "99.42 %"],
    ["16-QAM", "79.256", "−1032.793", "0.0746", "0.0767", "0.0789", "0.0015", "99.86 %"],
  ], [0.13, 0.1, 0.13, 0.13, 0.11, 0.11, 0.13, 0.16], 2));
  c.push(P("**What it shows.** 16-QAM fails at the lowest noise and BPSK tolerates the most, as expected. Leave-one-seed-out validation (no seed in both the fit and the test) gives low Brier scores, so the probabilities are reliable inside the measured range."));
  c.push(...FIG("results/figures/01_packet_success_calibration.png", "Measured packet success (points) and logistic fits (lines) vs noise voltage."));
  c.push(H2("5.3 Noise voltage ↔ SNR"));
  c.push(P("From 1,530 matched-path measurements: noise voltage 0.020 → 21.9 dB, 0.100 → 7.9 dB, 0.250 → −0.04 dB, 0.500 → −6.1 dB, with a standard deviation of about 0.04 dB. The three-channel estimator test recovered 16.98, 9.03 and 3.01 dB for expected 16.99, 9.03 and 3.01 dB."));
  c.push(H2("5.4 Synchronisation"));
  c.push(...T(["Impairment", "Result (validation scripts, 22 Nov)", "Meaning"], [
    ["CFO up to ±2 kHz", "540 trials, 0 timing errors, CFO error < 0.01 Hz", "Frequency offset is fully corrected"],
    ["SRO 5–20 ppm", "SRO estimate within 0.64 ppm; SNR error ≤ 0.19 dB; 292 / 300 trials pass overall (failures at 50 ppm)", "Sample-rate offset is corrected up to 20 ppm"],
    ["SRO without correction", "Timing fails in 60 / 60 trials from 5 ppm", "Why the correction was needed"],
    ["Two-path multipath", "1,800 trials; timing errors 50 % at 2- and 4-sample echoes with amplitude ≥ 0.5, 0 % at 1, 8 and 16 samples", "Short, strong echoes need an equaliser (not implemented)"],
  ], [0.2, 0.48, 0.32], 2));
  c.push(P("On 23 Nov, `apply_sro_correction` in `receiver_sync.py` was corrected to use the estimated ppm. The 22 Nov figures above are reported as recorded."));
  c.push(H2("5.5 On-air frames, receivers and BER thresholds"));
  c.push(P("The hardware receivers were developed on synthetic captures first. Four defects were found and fixed before transmission: a uint8 wrap in `map_bits` that turned bit 1 into +255 for BPSK/QPSK; whole-capture DC removal that limited SNR to about 30 dB (replaced by DC estimated from quiet blocks); a phase tracker that diverged at low SNR (replaced by block decision-directed tracking); and a coarse CFO error of about 5 kHz at low SNR (fixed by a second, 16-symbol-lag CFO stage)."));
  c.push(...FIG("results/figures/ber_vs_esn0_synthetic.png", "Multimod receiver BER on synthetic AWGN frames (points) vs theory (lines)."));
  c.push(P("**What it shows.** The receiver tracks theory closely for all three modulations. BER ≤ 10⁻³ is reached at **6.80 dB (BPSK), 9.93 dB (QPSK) and 16.67 dB (16-QAM)** Es/N0, within about 0.2 dB of theory (6.8 / 9.8 / 16.5 dB). These are the modulation-switching thresholds; Part 3 confirmed them over the air."));

  c.push(H2("5.6 Deep-learning modulation classifier (new)"));
  c.push(P("**Question.** Can a neural network tell BPSK, QPSK and 16-QAM apart from raw received samples, without the receiver's synchronisation, and does a model trained only on simulated data work on real over-the-air signals?"));
  c.push(P("**Model.** A 1-D convolutional network with six convolution layers (32 → 96 channels), batch normalisation, global average pooling and dropout: 85,859 parameters. Input: 512 consecutive IQ samples (128 symbols) of a frame's payload, scaled to unit RMS. The input is **not** corrected for frequency offset or phase; the network must handle them."));
  c.push(P("**Training data (synthetic).** 24,000 windows, with random payload bits each time so the network cannot memorise the fixed on-air payload. Each window passes through a simulated RTL-SDR chain: random Es/N0 (0–26 dB), CFO (±30 kHz), phase and timing; resampling to 2.048 MS/s; 8-bit quantisation at a random input level with DC offset; then the same DC removal and rate conversion as the real receiver. Training: AdamW, one-cycle learning rate, random phase-rotation and conjugation augmentation, 14 epochs (final validation accuracy 94.7 %, including windows down to 0 dB)."));
  c.push(P("**Test data (real).** The payload of every frame decoded in the 19 multimod OTA captures from 23 Nov: 536 windows (BPSK 336, QPSK 144, 16-QAM 56) from 76 frames, Es/N0 2.8–23.7 dB. None of this data was used for training."));
  c.push(P("**Baseline.** The textbook non-DL method: a random forest on higher-order-cumulant features (|C20|, |C40|, C42, amplitude kurtosis, amplitude spread), trained on the same synthetic windows."));
  c.push(...T(["Test set", "CNN", "Cumulant + random forest"], [
    ["Synthetic, 0 dB", "60.1 %", "33.9 %"],
    ["Synthetic, 6 dB", "94.9 %", "38.3 %"],
    ["Synthetic, 10 dB", "99.7 %", "55.9 %"],
    ["Synthetic, ≥ 12 dB", "100 %", "71.4–98.2 %"],
    ["**Real OTA, per window (536)**", "**98.5 %**", "62.9 %"],
    ["Real OTA, majority vote per frame (76)", "97.4 %", "—"],
    ["Real OTA, majority vote per capture (19)", "100 %", "—"],
  ], [0.44, 0.24, 0.32], 2));
  c.push(...FIG("results/dl/accuracy_vs_esn0.png", "Classification accuracy vs Es/N0: CNN and baseline on synthetic data (lines), CNN on each real OTA capture (orange markers)."));
  c.push(...FIG("results/dl/confusion_real.png", "CNN confusion matrix on the 536 real OTA windows.", 3.6));
  c.push(P("**What it shows.** BPSK is recognised perfectly; the only errors are QPSK ↔ 16-QAM confusions, all in captures at or below about 8 dB Es/N0, exactly where the synthetic curve also drops. The real points sit on the synthetic curve, so the simulated RTL-SDR chain is realistic: **a model trained only on simulation transfers to real hardware**. The cumulant baseline fails mainly because the residual frequency offset (about −10.6 kHz on air) rotates the constellation within a window and destroys the phase-dependent features that separate BPSK from QPSK; the CNN learns local structure that survives the rotation."));
  c.push(P("**Why it matters for a cognitive radio.** A receiver that can identify the modulation blindly does not need the transmitter to announce its modulation change in advance, and the same approach can recognise other users' signals when sensing a channel."));

  c.push(H1("6. How to reproduce"));
  c.push(...CODE([
    "python gnuradio/calibrate_receiver.py",
    "python gnuradio/refine_calibration.py",
    "python gnuradio/expand_calibration.py",
    "python gnuradio/analyze_calibration.py",
    "python gnuradio/validate_logistic_models.py",
    "python gnuradio/measure_channel_snr.py",
    "PYTHONPATH=. python src/validate_sync_corrections_combined.py",
    "python scripts/run_multimod_experiment.py --modulations BPSK QPSK 16QAM \\",
    "    --output-dir results/baseband/multimod_v2",
    "python scripts/ber_curves.py",
    "python scripts/plot_ber_synthetic.py",
    "pip install torch",
    "python scripts/train_modulation_classifier.py",
    "python -m pytest -q tests/test_multimod_receiver.py tests/test_bpsk_receiver.py \\",
    "    tests/test_dl_and_summary.py",
  ]));
  c.push(P("The GNU Radio scripts need GNU Radio installed. `pip install torch` is needed once for the classifier (the CPU build is enough); training takes about 8 minutes on a laptop CPU."));

  c.push(H1("7. Limitations"));
  c.push(...B([
    "Packet-success and SNR calibrations come from GNU Radio's synthetic AWGN channel, not from radio hardware.",
    "No equaliser: short, strong multipath echoes break timing (Section 5.4).",
    "DL test set: 536 windows, but all share the same seed-42 payload and come from one session and one antenna setup; windows from the same frame are not independent. The per-capture vote (19 / 19) is the most conservative figure.",
    "The classifier only knows three classes. It has no 'no signal' or 'unknown' class, and is applied to the payload part of frames that the receiver had already found.",
    "The cumulant baseline is not given CFO correction; a baseline with CFO correction would do better at high SNR.",
  ]));

  c.push(H1("8. Contribution summary"));
  c.push(P("The member responsible for Part 2 owns:"));
  c.push(...B([
    "the GNU Radio packet receiver, its development checks and its validation;",
    "the equal-power packet-success calibration, logistic models and leave-one-seed-out validation;",
    "the noise-voltage ↔ SNR calibration and the three-channel estimator;",
    "the synchronisation pipeline and its validation under CFO, SRO and multipath;",
    "the on-air frame formats, the BPSK and multi-modulation receivers and the synthetic BER thresholds;",
    "the deep-learning modulation classifier, its classical baseline and its evaluation on real OTA captures.",
  ]));
  return build(2, "Part2_PHY_Calibration_Receivers_DL_Report.docx", c);
};
