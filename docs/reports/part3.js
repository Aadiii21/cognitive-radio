const { P, H1, H2, B, NUM, CODE, NOTE, T, FIG, cover, build, resetFig } = require("./lib");

module.exports = function part3() {
  resetFig();
  const c = [];
  c.push(...cover(3, "SDR Hardware Integration and Over-the-Air Experiments",
    "The real-radio side of the project: driving an ADALM-Pluto transmitter and an RTL-SDR receiver from Python, the safety and verification gates, receive-only sensing work, and the over-the-air (OTA) experiments at 866 MHz: tone test, BPSK frames and a 15-point BER sweep for BPSK, QPSK and 16-QAM compared with theory."));

  c.push(H1("1. Purpose of this part"));
  c.push(P("Parts 1 and 2 are simulation and signal processing on a computer. Part 3 shows that the signals and receivers work on **real radios**: a waveform from Part 2 is transmitted by the Pluto, travels over the air, is captured by the RTL-SDR, and is decoded by Part 2's receivers. The measured bit error rate is then compared with theory and with the modulation-switching thresholds that the controller uses."));
  c.push(...B([
    "**Uses from Part 2:** the framed TX waveforms, the BPSK and multimod receivers, and the synthetic BER thresholds.",
    "**Gives to Part 2:** 19 real OTA captures, the test set for the DL classifier.",
    "**Gives to the project:** evidence that the modulation thresholds behind the controller hold on a real link.",
  ]));
  c.push(NOTE("**Scope.** On 23 Nov the team removed the hardware closed loop (controller driving the radios in real time) from the project scope. Part 3 is open-loop: transmit known frames, receive them, measure BER and Es/N0."));

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
    ["BPSK", "0", "21.8", "0 / 4096", "< 7.3e-4", "≈ 0"], ["BPSK", "5", "17.2", "0 / 4096", "< 7.3e-4", "≈ 0"], ["BPSK", "10", "10.0", "0 / 4096", "< 7.3e-4", "4.3e-6"], ["BPSK", "15", "7.7", "1 / 4096", "2.4e-4", "3.2e-4"], ["BPSK", "20", "4.3", "41 / 4096", "1.0e-2", "1.0e-2"],
    ["QPSK", "0", "23.3", "0 / 4096", "< 7.3e-4", "≈ 0"], ["QPSK", "5", "18.6", "0 / 4096", "< 7.3e-4", "≈ 0"], ["QPSK", "10", "12.8", "0 / 4096", "< 7.3e-4", "5.9e-6"], ["QPSK", "15", "6.9", "70 / 4096", "1.7e-2", "1.4e-2"], ["QPSK", "20", "5.1", "175 / 4096", "4.3e-2", "3.6e-2"],
    ["16-QAM", "0", "23.5", "0 / 4096", "< 7.3e-4", "1.1e-11"], ["16-QAM", "5", "17.1", "5 / 4096", "1.2e-3", "5.0e-4"], ["16-QAM", "10", "12.4", "123 / 4096", "3.0e-2", "2.4e-2"], ["16-QAM", "15", "8.0", "456 / 4096", "1.1e-1", "9.9e-2"], ["16-QAM", "20", "3.2", "957 / 4096", "2.3e-1", "2.0e-1"],
  ];
  c.push(...T(["Modulation", "Pluto att. (dB)", "Es/N0 (dB)", "Bit errors", "Measured BER", "AWGN theory"], rows, [0.15, 0.15, 0.14, 0.18, 0.19, 0.19], 3));
  c.push(...FIG("results/figures/hardware_ber_vs_theory.png", "All 19 OTA multimod runs: measured BER (circles), zero-error runs at their 95 % bound (triangles), AWGN theory (lines)."));
  c.push(P("**What it shows.**"));
  c.push(...B([
    "Every run with errors lies within about 1–2.5× of AWGN theory at its measured Es/N0, an implementation loss below 1 dB. BPSK at 4.3 dB matches theory exactly (1.0 × 10⁻²).",
    "The controller's thresholds (Part 2: 6.8 / 9.9 / 16.7 dB for BER ≤ 10⁻³) hold on air: 16-QAM at 17.1 dB gives 1.2 × 10⁻³, right at its threshold; QPSK is error-free at 11–23 dB and fails at 6.9 dB; BPSK gives 2.4 × 10⁻⁴ at 7.7 dB.",
    "At every power level the error rates rank BPSK < QPSK < 16-QAM, which is the trade-off adaptive modulation exploits.",
    "Es/N0 varied by about ±1.5 dB between runs at the same setting (e.g. 10.0 vs 12.8 dB at 10 dB attenuation), normal for an OTA link; this is why BER is plotted against the measured Es/N0, not the attenuation.",
  ]));
  c.push(H2("5.7 Earlier receive-only work and the first OTA attempts"));
  c.push(P("Before the transmission session, the RTL-SDR and Pluto were used receive-only: an FM-band scan (Figure 4), three-channel sensing at 500–502 MHz repeated five times per sensor (`results/hardware_stability/`), and a labelled capture dataset with spectral features. Two OTA attempts on the morning of 23 Nov received no burst (raw values 125–130, RMS 0.86 LSB). The most likely causes were the transmit path (the GNU Radio vector source was set not to repeat, so transmission could end before the capture) and a very low signal level at the receiver. Both were addressed before the afternoon session: the pure-Python cyclic transmitter keeps transmitting until stopped, and the level was raised step by step (Section 5.4)."));
  c.push(...FIG("results/figures/rtl_sdr_fm_spectrum.png", "RTL-SDR FM-band scan (88–108 MHz): first evidence that the receiver chain works.", 6.0));
  c.push(H2("5.8 Record correction"));
  c.push(P("The 23 Nov runs were started with `--rf-path conducted --attenuator-db 30`, but the real setup used antennas with no cable or attenuator. Rather than edit the measurements, `annotate_rf_path.py` added an `rf_path_correction` block (actual path: OTA) to the 26 affected records, keeping the original field so both what the runner was told and what was wired are visible. The runner now supports `--rf-path ota` directly."));

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
  c.push(P("Without hardware (from the saved captures and records):"));
  c.push(...CODE([
    "python scripts/run_hardware_experiment.py \\",
    "    --rx-file results/hardware/captures/rx_20261123_135940.cu8 \\",
    "    --waveform results/baseband/multimod_v2/qpsk_framed_seed42.json --no-save",
    "python scripts/summarize_hardware_sweep.py",
    "python -m pytest -q tests/test_run_hardware_experiment.py \\",
    "    tests/test_transmission_day.py tests/test_pluto_pyadi_tx.py",
  ]));

  c.push(H1("7. Limitations"));
  c.push(...B([
    "One OTA session, one antenna arrangement; the antenna separation was not recorded.",
    "Each point is one 512 ms capture of 4,096 bits. A zero-error run only shows BER < 7.3 × 10⁻⁴ (95 %); the 16-QAM 17.1 dB point rests on 5 errors.",
    "Indoor OTA link with no fading measurement; no conducted (cable + attenuator) comparison.",
    "Open loop only: the controller did not drive the radios (closed loop removed from scope).",
    "Single frequency (866 MHz); the controller's channel switching was not exercised on hardware.",
  ]));

  c.push(H1("8. Contribution summary"));
  c.push(P("The member responsible for Part 3 owns:"));
  c.push(...B([
    "the Pluto and RTL-SDR drivers, hardware constants and the pure-Python transmitter;",
    "the experiment runner with its safety and verification gates, and the record-correction tool;",
    "the receive-only sensing, FM scan and capture dataset;",
    "the OTA session: gain selection, tone test, BPSK frames and the 15-point BER sweep;",
    "the hardware BER analysis against theory, and the real captures used to test the DL classifier.",
  ]));
  return build(3, "Part3_SDR_Hardware_OTA_Report.docx", c);
};
