const { P, H1, H2, B, NUM, CODE, NOTE, T, FIG, cover, build, resetFig } = require("./lib");

module.exports = function part3() {
  resetFig();
  const c = [];
  c.push(...cover(3, "SDR Hardware Integration and Over-the-Air Experiments",
    "The real-radio side of the project: driving an ADALM-Pluto transmitter and an RTL-SDR receiver from Python, the safety and verification gates, receive-only sensing work, the over-the-air (OTA) experiments at 866 MHz (tone test, BPSK frames and a 15-point BER sweep for BPSK, QPSK and 16-QAM compared with theory), and closed-loop channel switching on the radios: 5 sessions, 72 rounds."));

  c.push(H1("1. Purpose of this part"));
  c.push(P("Parts 1 and 2 are simulation and signal processing on a computer. Part 3 shows that the signals and receivers work on **real radios**: a waveform from Part 2 is transmitted by the Pluto, travels over the air, is captured by the RTL-SDR, and is decoded by Part 2's receivers. The measured bit error rate is then compared with theory and with the modulation-switching thresholds that the controller uses."));
  c.push(...B([
    "**Uses from Part 2:** the framed TX waveforms, the BPSK and multimod receivers, and the synthetic BER thresholds.",
    "**Gives to Part 2:** 19 real OTA captures, the test set for the DL classifier.",
    "**Gives to the project:** evidence that the modulation thresholds behind the controller hold on a real link, and that the controller switches channel and modulation correctly when it drives the real radios.",
  ]));
  c.push(NOTE("**Scope.** The 23 Nov OTA session is open-loop: transmit known frames, receive them, measure BER and Es/N0. On 28 Nov the loop was closed on the radios (Section 5.9): the controller sensed three real channels, chose one and a modulation, and the Pluto transmitted accordingly, in 5 sessions. Channel quality in that demo is set by scripted TX power, not by real interference (Section 5.10)."));

  c.push(H1("2. Where this part fits"));
  c.push(...FIG("docs/flowcharts/01_project_workflow.png", "Project workflow. Orange: Part 3 (this report). Blue: Part 1. Green: Part 2."));

  c.push(H1("3. Code in this part"));
  c.push(...FIG("docs/flowcharts/04_code_map_part3.png", "Part 3 code → outputs map.", 6.27, 7.0));
  c.push(H2("3.1 Code files and their role"));
  c.push(...T(["File(s)", "Role"], [
    ["src/radio/hardware_config.py", "Verified constants: Pluto URI ip:192.168.2.1, Pluto minimum rate 2,083,333 S/s, RTL-SDR valid rate ranges and its exact-rate formula, TX1 channel settings."],
    ["src/radio/pluto_pyadi_tx.py", "Default transmitter (pure Python, pyadi-iio). Hardware is touched only in start(): gain set to minimum, old buffer destroyed, rate / bandwidth / LO set, gain set, then a cyclic buffer starts. close() destroys the buffer and returns the gain to minimum. Peak level limited to 0.25 of full scale."],
    ["src/radio/pluto_tx_adapter.py, pluto_transmitter.py", "Original GNU Radio (gr-iio) transmitter, kept as an alternative backend; Pluto readback through iio_attr."],
    ["src/radio/rtl_sdr_sensor.py, rtl_capture.py, pluto_sensor.py", "RTL-SDR capture through rtl_sdr (valid rates, discard of the first samples, exact actual rate) and Pluto receive-only sensing."],
    ["src/hardware_dual_sensor.py", "Receive-only power/SNR measurements on three channels (500, 501, 502 MHz) with the RTL-SDR and the Pluto."],
    ["src/radio/capture_rtl_dataset.py, src/extract_features.py", "Labelled RTL-SDR capture dataset with metadata and spectral features."],
    ["src/plot_rtlsdr_scan.py, plot_rtlsdr_peaks.py, plot_iq_comparison.py", "FM-band spectrum scan and IQ plots: first proof the RTL-SDR works."],
    ["scripts/run_hardware_experiment.py", "The OTA experiment runner: dry run, tone test, frame tests, receive-only and offline re-processing. Enforces all safety gates, overlaps TX and RX, saves raw captures with metadata, runs the receiver and writes one result record per run."],
    ["scripts/run_channel_switching_demo.py", "Closed-loop demo: probe three channels, run the calibrated controller, transmit on the chosen channel; scripted channel quality (5 phases); optional --margin-db safety margin; --simulate and --dry-run modes."],
    ["scripts/summarize_closed_loop.py", "Pools all real closed-loop sessions: switches needed / made / unnecessary, best-channel rounds and BER per modulation with exact 95 % intervals."],
    ["scripts/verify_closed_loop_captures.py", "Offline audit: re-decodes every saved capture, checks every Pluto readback and replays every controller decision from the logged measurements."],
    ["scripts/scan_band.py", "Passive (receive-only) rtl_power scan of 865–868 MHz; refuses to run while the Pluto TX LO is on."],
    ["scripts/annotate_rf_path.py", "Adds an rf_path_correction block to run records whose declared RF path differs from the real setup (used for the 23 Nov runs)."],
    ["scripts/summarize_hardware_sweep.py", "Builds the BER table and figure from the run records (no hardware needed)."],
    ["pipelines/integrated_pipeline.py; scripts/pluto_to_rtl_sdr_demo.py, test_pluto_tx_adapter.py", "Software-mode pipeline and two legacy demos; their RF paths are disabled."],
  ], [0.34, 0.66], 3));

  c.push(H1("4. Outputs and what they signify"));
  c.push(...T(["Output", "Produced by", "Contents", "What it signifies"], [
    ["results/hardware/captures/*.cu8 + .json (30 pairs)", "run_hardware_experiment.py", "Raw 8-bit IQ from the RTL-SDR plus a sidecar: rates, gain, TX readback, RF path", "The real signal, kept so every result can be re-processed offline"],
    ["results/hardware/experiment_results/*.json (27 runs)", "run_hardware_experiment.py", "Configuration, Pluto readback, receiver output per frame (CFO, Es/N0, EVM, BER)", "The measured outcome of each transmission"],
    ["results/hardware/day_01_*.log", "terminal (tee)", "Console log of each run", "Human-readable record of the session"],
    ["rf_path_correction blocks in 26 records", "annotate_rf_path.py", "Actual path = OTA, note, date", "Honest labelling: the runs were declared as conducted but used antennas"],
    ["results/analysis/hardware_ber_runs.csv, results/figures/hardware_ber_vs_theory.png", "summarize_hardware_sweep.py", "One row per multimod run: Es/N0, errors, BER, theory", "Measured BER follows AWGN theory; the switching thresholds hold"],
    ["results/analysis/hardware_ber_sweep_day01.csv", "derived from the logs (23 Nov)", "The 15 sweep runs", "Same data as above, sweep only"],
    ["results/hardware/closed_loop/session_*/ (rounds.csv, session.json, session.png, captures/*.json)", "run_channel_switching_demo.py", "Per round: Es/N0 on every channel, decision, data BER; per-burst Pluto readback. Raw IQ (288 captures, 330 MB) kept outside git", "Channel switching and modulation adaptation on real radios"],
    ["results/analysis/closed_loop_sessions.csv, closed_loop_summary.json, results/figures/closed_loop_repeatability.png", "summarize_closed_loop.py", "Per-session and pooled results with 95 % intervals", "The demo is repeatable; BER per modulation vs theory"],
    ["results/analysis/closed_loop_verification.json", "verify_closed_loop_captures.py", "Re-decode, readback and decision-replay results", "Every logged number can be reproduced from the raw data"],
    ["results/hardware/band_scan/scan_*/ (rtl_power.csv, scan.png, summary.json)", "scan_band.py", "90 sweeps of 865–868 MHz, per-channel power vs floor", "What the real channels look like without our transmitter"],
    ["results/hardware_corrected/, hardware_stability/, dual_sensor_*.csv", "hardware_dual_sensor.py", "Per-channel SNR from RTL-SDR and Pluto sensing, repeated 5 times each", "Receive-only sensing works and is repeatable"],
    ["results/figures/rtl_sdr_fm_spectrum.png, rtl_sdr_fm_scan.csv, results/features/, data/raw/", "plot / capture scripts", "FM-band scan; feature tables; raw captures", "The receiver sees real signals"],
  ], [0.29, 0.19, 0.28, 0.24], 3));

  c.push(H1("5. Results"));
  c.push(H2("5.1 Setup"));
  c.push(...T(["Item", "Setting"], [
    ["Transmitter", "ADALM-Pluto Rev.C (AD9363), firmware v0.32, ip:192.168.2.1, pyadi-iio 0.0.21 with libiio 0.26, cyclic buffer"],
    ["Receiver", "RTL2832U / R820T RTL-SDR, 2.048 MS/s, manual gain 28 dB"],
    ["Frequency", "866 MHz centre; occupied band 865.65–866.35 MHz, inside the 865–868 MHz short-range-device band"],
    ["TX sample rate", "2,083,333 S/s (Pluto minimum without FIR), 4 samples/symbol → 520.8 kBd; RRC roll-off 0.35"],
    ["TX level", "Amplitude scale 0.1 of full scale; Pluto TX attenuation 0–30 dB as the power control"],
    ["RF path", "Over the air: antenna on the Pluto TX port and on the RTL-SDR; separation not recorded"],
  ], [0.22, 0.78], 3));
  c.push(H2("5.2 Safety and verification gates"));
  c.push(P("The runner refuses to transmit unless every gate passes. Nothing touches the hardware before the operator confirms, and the transmitter is always stopped, even on an error."));
  c.push(...NUM([
    "`--enable-rf` and a declared RF path (`--rf-path ota --antenna-separation-m D`, or conducted with ≥ 30 dB attenuator).",
    "Band check: the whole occupied band must lie inside 865–868 MHz.",
    "Pre-flight: Pluto reachable; pyadi-iio, rtl_sdr and iio_attr available.",
    "Operator types `TRANSMIT` after reading a summary of every setting.",
    "Readback from the Pluto after start: LO within 1 kHz, gain within 0.5 dB, rate within 100 ppm, band rechecked. On 23 Nov every run read back LO 865,999,998 Hz and rate 2,083,332 S/s.",
    "Capture must hold at least two frames; each capture is saved with a provenance sidecar, and offline re-processing refuses files without one.",
  ]));
  c.push(H2("5.3 Choosing the receiver gain"));
  c.push(P("An FM station at 98.3 MHz was captured at three gains (antenna on the RTL-SDR, no transmission):"));
  c.push(...T(["RTL gain", "Raw range (0–255)", "RMS (LSB)", "Verdict"], [
    ["0 (automatic)", "0–255", "152.8", "Clipping"],
    ["**28 dB**", "**36–212**", "**54.6**", "**Clean, headroom on both sides: chosen**"],
    ["49.6 dB", "0–255", "151.7", "Clipping"],
  ], [0.2, 0.22, 0.18, 0.4], 3));
  c.push(P("A later BPSK check confirmed the choice: at 40 dB gain, Es/N0 fell from about 15 dB to 9–10 dB and one frame was corrupted (45 / 1,536 bit errors), so 28 dB was used for every result below."));
  c.push(H2("5.4 Tone test"));
  c.push(P("A CW tone 100 kHz above the 866 MHz LO was captured with TX on and with TX off; the runner compares the power in the tone's frequency bin."));
  c.push(...T(["Pluto attenuation", "Tone bin, TX on vs off", "RMS on / off (LSB)", "Frequency offset"], [
    ["30 dB", "25.0 dB", "0.88 / 0.88", "−10.25 kHz (−11.8 ppm)"],
    ["20 dB", "40.4 dB", "1.24 / 0.87", "−10.38 kHz (−12.0 ppm)"],
    ["10 dB", "49.5 dB", "2.58 / 0.87", "−10.38 kHz (−12.0 ppm)"],
  ], [0.22, 0.26, 0.24, 0.28], 3));
  c.push(P("**What it shows.** The transmitter is on air and the receiver hears it; the tone grows by about 10 dB per 10 dB of attenuation removed, so the link is linear. The steady −10.4 kHz offset is the RTL-SDR's crystal error (about −12 ppm), well inside the receivers' ±100 kHz range."));
  c.push(H2("5.5 First frames: BPSK frame v2"));
  c.push(P("At Pluto attenuation 10 dB and gain 28 dB, the BPSK receiver found **4 of 4 frames with 0 errors in 2,048 payload bits**, at Es/N0 13.7–15.3 dB. This matched the Es/N0 of about 15 dB predicted from the tone test."));
  c.push(H2("5.6 BPSK, QPSK and 16-QAM BER sweep"));
  c.push(P("Each modulation was sent at Pluto attenuation 0, 5, 10, 15 and 20 dB (15 runs), plus four earlier runs at 10 and 0 dB. Every run decoded 4 of 4 frames with 0 % clipping. Es/N0 is the receiver's data-aided estimate, averaged over the four frames."));
  const rows = [
    ["BPSK", "0", "21.8", "0 / 4096", "< 9.0e-4", "≈ 0", "—"], ["BPSK", "5", "17.2", "0 / 4096", "< 9.0e-4", "≈ 0", "—"], ["BPSK", "10", "10.0", "0 / 4096", "< 9.0e-4", "4.3e-6", "—"], ["BPSK", "15", "7.7", "1 / 4096", "6.2e-6 – 1.4e-3", "3.2e-4", "−0.19"], ["BPSK", "20", "4.3", "41 / 4096", "7.2e-3 – 1.4e-2", "1.0e-2", "−0.03"],
    ["QPSK", "0", "23.3", "0 / 4096", "< 9.0e-4", "≈ 0", "—"], ["QPSK", "5", "18.6", "0 / 4096", "< 9.0e-4", "≈ 0", "—"], ["QPSK", "10", "12.8", "0 / 4096", "< 9.0e-4", "5.9e-6", "—"], ["QPSK", "15", "6.8", "70 / 4096", "1.3e-2 – 2.2e-2", "1.4e-2", "0.33"], ["QPSK", "20", "5.1", "175 / 4096", "3.7e-2 – 4.9e-2", "3.6e-2", "0.38"],
    ["16-QAM", "0", "23.4", "0 / 4096", "< 9.0e-4", "≈ 0", "—"], ["16-QAM", "5", "17.1", "5 / 4096", "4.0e-4 – 2.8e-3", "5.0e-4", "0.75"], ["16-QAM", "10", "12.3", "123 / 4096", "2.5e-2 – 3.6e-2", "2.4e-2", "0.50"], ["16-QAM", "15", "8.0", "456 / 4096", "1.0e-1 – 1.2e-1", "9.9e-2", "0.59"], ["16-QAM", "20", "3.1", "957 / 4096", "2.2e-1 – 2.5e-1", "2.0e-1", "2.33"],
  ];
  c.push(...T(["Modulation", "Pluto att. (dB)", "Es/N0 (dB)", "Bit errors", "Measured BER, exact two-sided 95 % CI", "AWGN theory", "Implied loss (dB)"], rows, [0.12, 0.11, 0.11, 0.14, 0.22, 0.13, 0.17], 3));
  c.push(P("Es/N0 values are taken from the run records (`scripts/summarize_hardware_sweep.py`). The interval is the exact two-sided 95 % Clopper–Pearson interval, so a zero-error run appears as < 9.0 × 10⁻⁴ (its upper limit). Where the text quotes 7.3 × 10⁻⁴ for zero errors, that is the one-sided 95 % upper bound; both say the BER is small, not zero. **Implied loss** is how much higher Es/N0 theory would need to reach the measured BER: 0 means exactly on theory, positive means the hardware is worse."));
  c.push(...FIG("results/figures/hardware_ber_vs_theory.png", "All 19 OTA multimod runs: measured BER with exact 95 % intervals (circles and bars), zero-error runs at their 95 % bound (triangles), AWGN theory (lines)."));
  c.push(P("**What it shows.**"));
  c.push(...B([
    "**How close to theory, with uncertainty:** in 4 of the 9 runs with errors, the 95 % interval contains the theoretical BER. In the other 5 the hardware is slightly worse than theory (one of them by only 0.00002 in BER), which is the small implementation loss expected of a real receiver. The implied implementation loss is **−0.2 to +0.75 dB for every run above 4 dB Es/N0**. The one larger value, 2.3 dB for 16-QAM at 3.1 dB, is an artefact: at BER ≈ 0.23 the curve is almost flat, so a small BER difference converts to many dB, and the 16-QAM formula is an approximation that underestimates BER that low.",
    "The controller's thresholds (Part 2: 6.8 / 9.9 / 16.7 dB for BER ≤ 10⁻³) hold on air: 16-QAM at 17.1 dB gives 1.2 × 10⁻³, right at its threshold; QPSK is error-free at 11–23 dB and fails at 6.8 dB; BPSK gives 2.4 × 10⁻⁴ at 7.7 dB.",
    "At every power level the error rates rank BPSK < QPSK < 16-QAM, which is the trade-off adaptive modulation exploits.",
    "Es/N0 varied by about ±1.5 dB between runs at the same setting (e.g. 10.0 vs 12.8 dB at 10 dB attenuation), normal for an OTA link; this is why BER is plotted against the measured Es/N0, not the attenuation.",
  ]));
  c.push(H2("5.7 Earlier receive-only work and the first OTA attempts"));
  c.push(P("Before the transmission session, the RTL-SDR and Pluto were used receive-only: an FM-band scan (Figure 4), three-channel sensing at 500–502 MHz repeated five times per sensor (`results/hardware_stability/`), and a labelled capture dataset with spectral features. Two OTA attempts on the morning of 23 Nov received no burst (raw values 125–130, RMS 0.86 LSB). The most likely causes were the transmit path (the GNU Radio vector source was set not to repeat, so transmission could end before the capture) and a very low signal level at the receiver. Both were addressed before the afternoon session: the pure-Python cyclic transmitter keeps transmitting until stopped, and the level was raised step by step (Section 5.4)."));
  c.push(...FIG("results/figures/rtl_sdr_fm_spectrum.png", "RTL-SDR FM-band scan (88–108 MHz): first evidence that the receiver chain works.", 6.0));
  c.push(H2("5.8 Record correction"));
  c.push(P("The 23 Nov runs were started with `--rf-path conducted --attenuator-db 30`, but the real setup used antennas with no cable or attenuator. Rather than edit the measurements, `annotate_rf_path.py` added an `rf_path_correction` block (actual path: OTA) to the 26 affected records, keeping the original field so both what the runner was told and what was wired are visible. The runner now supports `--rf-path ota` directly."));

  c.push(H2("5.9 Closed-loop channel switching on real radios (28 Nov)"));
  c.push(P("`scripts/run_channel_switching_demo.py` closes the loop between sensing, the original controller and the transmitter. Every round:"));
  c.push(...NUM([
    "**Sense:** the Pluto sends a BPSK probe frame on each of three channels (865.7, 866.5 and 867.3 MHz, all inside 865–868 MHz); the RTL-SDR retunes to each and the receiver measures Es/N0.",
    "**Decide:** the unchanged `CalibratedCognitiveController` receives the three values (Es/N0 − 6.02 dB, its SNR scale) and returns a channel, a modulation and whether to switch.",
    "**Send:** the Pluto transmits a data burst (two frames, 2,048 payload bits) in that modulation on that channel; the RTL-SDR captures it and the receiver counts bit errors.",
  ]));
  c.push(P("Each channel's quality follows a scripted schedule of Pluto TX attenuation, three rounds per phase: **A, B, C** – a different channel is best (0 / 10 / 20 dB); **D** – all mediocre (10 / 15 / 20 dB); **E** – all poor (15 / 20 / 20 dB). Antennas were 1.5 m apart. All safety gates of the experiment runner applied; every one of the 288 bursts was started, read back (LO, gain, rate), captured and stopped. A burst took about 2.3 s, a 15-round session 140 s."));
  c.push(...FIG("results/figures/closed_loop_real_session.png", "Real-radio session 07:48 (no margin). Top: probe Es/N0 per channel and the controller's BER ≤ 10⁻³ thresholds. Middle: chosen channel (red: switch). Bottom: chosen modulation and data bit errors.", 4.7));
  c.push(H2("5.9.1 Sessions"));
  c.push(...T(["Session (28 Nov)", "Phases", "Safety margin", "Switches needed / made / unnecessary", "Highest-Es/N0 channel chosen", "Data bit errors", "Mean Es/N0, best channel at 0 dB"], [
    ["07:17", "A–D", "0 dB", "3 / 3 / 0", "12 / 12", "75 / 24,576", "17.5 dB"],
    ["07:41", "A–E", "0 dB", "3 / 3 / 0", "15 / 15", "83 / 30,720", "19.7 dB"],
    ["07:43", "A–E", "2 dB", "3 / 3 / 0", "15 / 15", "48 / 29,696", "18.5 dB"],
    ["07:48", "A–E", "0 dB", "3 / 3 / 0", "15 / 15", "26 / 30,720", "20.6 dB"],
    ["07:51", "A–E", "2 dB", "3 / 3 / 0", "15 / 15", "10 / 30,720", "19.5 dB"],
    ["**All**", "", "", "**15 / 15 / 0**", "**72 / 72**", "242 / 146,432", ""],
  ], [0.13, 0.08, 0.1, 0.2, 0.12, 0.17, 0.2], 3));
  c.push(P("Phase E was added after the first session, whose best channel never fell into the BPSK range. Two earlier attempts that morning are kept but excluded: one stopped before transmitting (a software bug, fixed and covered by a test) and one was interrupted by the operator."));
  c.push(P("**What it shows.**"));
  c.push(...B([
    "**The controller switches as designed on real radios.** In all 72 rounds it selected the channel with the highest measured probe Es/N0 (95 % interval 0.95–1.00), under the scripted channel-quality schedule. This is the criterion used throughout: best of the three probed channels, not an independently established optimum under natural interference. Every phase change that moved the best channel was followed by a switch in the very first round (15 / 15), and it never switched without reason (0 unnecessary switches), although probe Es/N0 moved by 1–3 dB from round to round. That is the switching cost doing its job.",
    "**It adapts the modulation as well as the channel.** 16-QAM on the 18–22 dB channels of phases A–C, QPSK at about 11 dB (phase D), BPSK at 3.6–8 dB (phase E). With the switch in phase D (from channel 2 at about 1 dB to channel 0 at about 11 dB) it changed both at once.",
    "**The scripted levels are reproducible but not exact:** Es/N0 at a given attenuation varied with a standard deviation of 1–2 dB, and the session mean at 0 dB drifted from 17.5 to 20.6 dB over 35 minutes. 9 of 216 probes at 20 dB found no frame; the controller treats such a channel as unusable.",
  ]));
  c.push(H2("5.9.2 Data bit errors"));
  c.push(...T(["Modulation", "Margin", "Rounds", "Bit errors", "BER, exact two-sided 95 % CI", "Mean data Es/N0", "AWGN theory at burst-average Es/N0"], [
    ["BPSK", "0 dB", "6", "101 / 12,288", "8.2e-3 (6.7e-3 – 1.0e-2)", "5.5 dB", "5.6e-3"],
    ["QPSK", "0 dB", "9", "10 / 18,432", "5.4e-4 (2.6e-4 – 1.0e-3)", "11.0 dB", "3.0e-4"],
    ["16-QAM", "0 dB", "27", "73 / 55,296", "1.3e-3 (1.0e-3 – 1.7e-3)", "19.5 dB", "1.0e-4"],
    ["BPSK", "2 dB", "12", "53 / 23,552", "2.3e-3 (1.7e-3 – 2.9e-3)", "8.5 dB", "7.9e-4"],
    ["QPSK", "2 dB", "4", "0 / 8,192", "< 4.5e-4", "18.1 dB", "≈ 0"],
    ["16-QAM", "2 dB", "14", "5 / 28,672", "1.7e-4 (5.7e-5 – 4.1e-4)", "19.4 dB", "2.7e-5"],
  ], [0.12, 0.09, 0.09, 0.15, 0.25, 0.15, 0.15], 3));
  c.push(...FIG("results/figures/closed_loop_repeatability.png", "Data BER per chosen modulation over all real sessions, with exact 95 % intervals; crosses: AWGN theory evaluated at each burst's average Es/N0, then averaged over rounds; it does not see the Es/N0 variation inside a burst.", 5.8));
  c.push(...B([
    "**BPSK and QPSK are close to theory** (within a factor of about 2, i.e. well under 1 dB), as in the 23 Nov sweep.",
    "**16-QAM is worse than its average Es/N0 suggests, and the reason is visible in the raw data.** Each data burst holds two frames. Re-decoding every capture frame by frame shows that 15 of 143 frames had an Es/N0 more than 3 dB below the other frame of the same burst (up to 8.5 dB lower). Those short dips carry **68 of the 78 16-QAM errors** (and 160 of all 242): for example, the 37 errors of the first round of 07:17 all sit in a frame at 11.4 dB, while the other frame of that burst was at 19.9 dB with no errors. The controller decides on the probe, a few seconds earlier, and 16-QAM has the least room for such a dip. Their cause (multipath change, movement near the antennas, a receiver transient) was not identified. The theory column uses each burst's average Es/N0, which cannot see these dips, so this is not a like-for-like comparison: the gap is not solely receiver implementation loss.",
    "**The safety margin works as intended, but this data cannot size its benefit.** With 2 dB the controller chose QPSK instead of 16-QAM near the cut-off and BPSK instead of QPSK in phase D, and BER was lower (9.6 × 10⁻⁴ against 2.1 × 10⁻³ overall); the cost was about 20 % of the throughput (mean 2.5 against 3.1 bits per symbol). However, the link itself drifted by 3 dB between sessions, the two later no-margin sessions had no 16-QAM errors at all (18 rounds), and in phase E both settings use BPSK, so most of the BER difference is link variation, not the margin. The simulation study (Part 1) remains the better estimate of the margin's effect; the hardware shows why a margin is needed: short dips of several dB are real.",
    "**At 3.6–5.5 dB even BPSK lost up to 3 % of bits** (phase E). The controller has no 'do not transmit' option, so it sends BPSK however poor the best channel is.",
  ]));
  c.push(H2("5.9.3 Verification"));
  c.push(P("`scripts/verify_closed_loop_captures.py` re-processed the raw data offline. All **288 captures re-decode to exactly the logged Es/N0, frame count and bit errors** (largest difference 0.000 dB); every burst's Pluto readback matches its frequency (within 1 Hz) and attenuation; and feeding the logged probe values to a fresh controller reproduces **every one of the 72 decisions** (channel, modulation and action). The demo software is covered by 19 tests with fake radios, the scan by 4, the summary by 2 and the audit by 2 (including one that checks it catches a tampered log)."));

  c.push(H2("5.10 What the channels are, and what they are not"));
  c.push(P("A faculty review pointed out that in the GNU Radio software-in-the-loop experiment (Part 1, Section 5.4) each of the three 'channels' is the same 1 kHz test tone with its own Gaussian noise source and an interference term at the same frequency, with no difference in frequency: in effect the same channel with different noise. That description is correct, and it matters for how each experiment is described:"));
  c.push(...B([
    "**GNU Radio experiment:** three logical channels that differ only in SNR. It tests the controller's decision logic on a running flowgraph, not RF channel behaviour.",
    "**Real-radio demo (this section):** three separate RF channels 0.8 MHz apart; the transmitter and receiver really retune, and every measurement is a real over-the-air capture. But the *difference in quality* between the channels is still produced by our own TX power, not by interference, fading or other users.",
    "**The real band was quiet.** A 3-minute passive scan (Figure 7) found each channel's mean power within 0.6 dB of the band floor and no wideband activity in any of the 90 sweeps. The narrow spikes are constant in every sweep and present outside the channels as well, which points to fixed tones from the receiver or the computer rather than other users; they were not identified. Left alone, the three channels would have looked the same to the controller.",
    "**The calibration data remain valid.** The GNU Radio calibration measures how packet success depends on SNR for each modulation; it does not depend on which channel the SNR occurs on. The 23 Nov sweep and this demo both found BPSK / QPSK error rates within about 1 dB of the AWGN behaviour the calibration assumes. What the calibration does not cover is interference that is not noise-like (narrowband, bursty or another modulated signal); the short dips of Section 5.9.2 are one example of real behaviour it does not model.",
  ]));
  c.push(...FIG("results/figures/band_scan_865_868.png", "Passive RTL-SDR scan of 864.5–868.5 MHz, 90 sweeps over 3 minutes, Pluto TX off. Shaded: the demo's channel bands.", 6.0));
  c.push(P("Channel quality differences caused by real interference (for example a second transmitter, or band-limited noise sent during the data burst on one channel) were not tested; this is the main open point of the hardware work."));

  c.push(H1("6. How to reproduce"));
  c.push(P("With hardware (Pluto TX antenna, RTL-SDR antenna, separation D metres):"));
  c.push(...CODE([
    "# TX LO on",
    "iio_attr -u ip:192.168.2.1 -o -c ad9361-phy altvoltage1 powerdown 0",
    "python scripts/run_hardware_experiment.py --enable-rf --tone --freq 866000000 \\",
    "    --rf-path ota --antenna-separation-m D --rx-gain 28 --attenuation 10",
    "python scripts/run_hardware_experiment.py --enable-rf --freq 866000000 \\",
    "    --rf-path ota --antenna-separation-m D --rx-gain 28 --attenuation 10 \\",
    "    --waveform results/baseband/multimod_v2/qpsk_framed_seed42.json",
    "# TX LO off",
    "iio_attr -u ip:192.168.2.1 -o -c ad9361-phy altvoltage1 powerdown 1",
  ]));
  c.push(P("Closed-loop channel switching (same setup; type TRANSMIT once per session):"));
  c.push(...CODE([
    "python scripts/scan_band.py --minutes 3          # receive only, TX LO off",
    "iio_attr -u ip:192.168.2.1 -o -c ad9361-phy altvoltage1 powerdown 0",
    "python scripts/run_channel_switching_demo.py --enable-rf --rf-path ota \\",
    "    --antenna-separation-m 1.5 [--margin-db 2]",
    "iio_attr -u ip:192.168.2.1 -o -c ad9361-phy altvoltage1 powerdown 1",
    "python scripts/summarize_closed_loop.py",
    "python scripts/verify_closed_loop_captures.py    # needs the raw captures",
  ]));
  c.push(P("Without hardware (from the saved captures and records):"));
  c.push(...CODE([
    "python scripts/run_hardware_experiment.py \\",
    "    --rx-file results/hardware/captures/rx_20261123_135940.cu8 \\",
    "    --waveform results/baseband/multimod_v2/qpsk_framed_seed42.json --no-save",
    "python scripts/summarize_hardware_sweep.py",
    "python -m pytest -q tests/test_run_hardware_experiment.py \\",
    "    tests/test_transmission_day.py tests/test_pluto_pyadi_tx.py \\",
    "    tests/test_channel_switching_demo.py tests/test_scan_band.py \\",
    "    tests/test_summarize_closed_loop.py tests/test_verify_closed_loop.py",
  ]));

  c.push(H1("7. Limitations"));
  c.push(...B([
    "BER sweep: one OTA session, one antenna arrangement; the antenna separation was not recorded.",
    "Each point is one 512 ms capture of 4,096 bits. A zero-error run only shows BER < 7.3 × 10⁻⁴ (one-sided 95 % upper bound; < 9.0 × 10⁻⁴ two-sided, as in the table); the 16-QAM 17.1 dB point rests on 5 errors.",
    "Indoor OTA link with no fading measurement; no conducted (cable + attenuator) comparison.",
    "Closed-loop demo: channel quality is scripted by TX power; no real interference, fading or second user was tested (Section 5.10). One room, one 1.5 m antenna spacing, 35 minutes.",
    "The controller decides on a probe sent seconds before the data; short Es/N0 dips of several dB in between caused most 16-QAM errors. It also has no 'do not transmit' option.",
    "Session-to-session drift (about 3 dB) prevents a precise hardware estimate of the safety margin's benefit.",
    "Raw closed-loop captures (330 MB) are not in the repository; they are kept as a separate backup, and the offline audit needs them.",
  ]));

  c.push(H1("8. Contribution summary"));
  c.push(P("The member responsible for Part 3 owns:"));
  c.push(...B([
    "the Pluto and RTL-SDR drivers, hardware constants and the pure-Python transmitter;",
    "the experiment runner with its safety and verification gates, and the record-correction tool;",
    "the receive-only sensing, FM scan and capture dataset;",
    "the OTA session: gain selection, tone test, BPSK frames and the 15-point BER sweep;",
    "the hardware BER analysis against theory, and the real captures used to test the DL classifier;",
    "the closed-loop channel-switching demo on the radios (5 sessions), the passive band scan, the multi-session summary and the offline audit of every capture and decision.",
  ]));
  return build(3, "Part3_SDR_Hardware_OTA_Report.docx", c);
};
