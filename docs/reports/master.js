const { Paragraph, TextRun, PageBreak, BorderStyle } = require("docx");
const { runs, P, H1, H2, B, NUM, CODE, NOTE, T, FIG, build, resetFig } = require("./lib");

function masterCover() {
  const c = "1F3864";
  return [
    new Paragraph({ spacing: { before: 1400 }, children: [new TextRun({ text: "Master Report", size: 28, color: "666666" })] }),
    new Paragraph({ spacing: { before: 120, after: 240 }, children: [new TextRun({
      text: "Design and Implementation of a Cost-Aware Cognitive Radio Framework for Joint Channel Switching and Adaptive Modulation",
      size: 40, bold: true, color: c })] }),
    new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: c, space: 4 } }, children: [] }),
    new Paragraph({ spacing: { before: 240, after: 360 }, children: runs(
      "Simulation, GNU Radio physical layer, over-the-air SDR experiments (ADALM-Pluto → RTL-SDR) and ML / DL analysis.", { size: 22 }) }),
    ...T(["Part", "Scope", "Team member", "Roll number"], [
      ["1", "Simulation, cognitive control and ML analysis", "", ""],
      ["2", "Physical layer, calibration, receivers and DL classifier", "", ""],
      ["3", "SDR hardware integration and OTA experiments", "", ""],
    ], [0.08, 0.5, 0.24, 0.18], 0),
    new Paragraph({ spacing: { before: 360 }, children: [new TextRun({ text: "Date: ", bold: true }), new TextRun("28 November 2026")] }),
    new Paragraph({ spacing: { before: 120 }, children: [new TextRun({ text: "Code and data: ", bold: true }), new TextRun("https://github.com/Aadiii21/cognitive-radio")] }),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

module.exports = function master() {
  resetFig();
  const c = [...masterCover()];

  c.push(H1("Abstract"));
  c.push(P("A cognitive radio must decide which channel to use and how fast to transmit on it. Faster modulation carries more data but fails at lower signal quality, and moving to a better channel costs time. This project builds a controller that chooses the channel and the modulation (BPSK, QPSK or 16-QAM) by maximising expected delivered data, using packet-success curves measured with a GNU Radio receiver and an explicit switching cost. In a 630-run benchmark across three interference levels, the calibrated, cost-aware controller delivers the most data of seven strategies in every environment while keeping packet delivery at or above 99 %. The physical layer was then taken onto real radios: an ADALM-Pluto transmitter and an RTL-SDR receiver at 866 MHz. Over the air, the measured bit error rate of all three modulations followed theory within about 1 dB, confirming the controller's switching thresholds. With the loop closed on the radios, the controller sensed three real channels and chose the channel with the highest measured quality in 72 of 72 rounds over five sessions, switching in the first round after every change and never without reason, while adapting the modulation from 16-QAM down to BPSK; channel quality in this demo was set by transmit power rather than real interference. Finally, machine learning was used to analyse the benchmark (random forest, R² 0.997), and a convolutional neural network trained only on simulated signals identified the modulation of 98.5 % of real over-the-air signal windows. Sensitivity and robustness studies show that the controller's lead does not depend on its switching-cost setting and survives a realistic 1 dB hardware loss, provided the controller keeps a matching safety margin."));

  c.push(H1("1. Introduction"));
  c.push(P("Wireless channels change over time: interference comes and goes, and one channel may be clean while another is congested. A fixed radio either wastes capacity (by sending slowly on a good channel) or loses packets (by sending fast on a bad one). A **cognitive radio** senses its environment and adapts."));
  c.push(P("This project adapts two things jointly:"));
  c.push(...B([
    "**Modulation:** BPSK (1 bit/symbol), QPSK (2) or 16-QAM (4). Higher order means more data but less tolerance to noise.",
    "**Channel:** stay, or switch to one of three channels. Switching stops transmission for the handoff, so it is only worth it if the gain outweighs the cost.",
  ]));
  c.push(P("**Objectives.** (1) Build a controller that maximises delivered throughput while keeping packets reliable and accounting for switching cost. (2) Base its packet-success estimates on measured receiver behaviour rather than formulas. (3) Compare it fairly against simpler strategies. (4) Show that the physical-layer assumptions hold on real radios. (5) Use ML and DL to analyse and extend the results."));

  c.push(H1("2. System overview"));
  c.push(P("Figure 1 shows how the project works. The three colours are the three equal parts into which the work was divided, one per team member."));
  c.push(...FIG("docs/flowcharts/01_project_workflow.png", "Project workflow. Blue: Part 1 simulation and control. Green: Part 2 physical layer and DL. Orange: Part 3 hardware."));
  c.push(...T(["Part", "Scope", "Main outputs"], [
    ["1. Simulation, cognitive control and ML", "Channel model, 7 controller strategies, 630-run benchmark, paired statistics, simulated radio, GNU Radio software-in-the-loop experiment, ML analysis", "Benchmark CSV and figures, paired CIs, random-forest models"],
    ["2. Physical layer, calibration, receivers and DL", "GNU Radio packet receiver, packet-success and SNR calibration, synchronisation, on-air frames and receivers, BER thresholds, CNN classifier", "Logistic models, SNR map, BER curves and thresholds, trained CNN"],
    ["3. SDR hardware and OTA experiments", "Pluto / RTL-SDR drivers, safety gates, experiment runner, tone test, BPSK frames, BER sweep, closed-loop channel switching on the radios, band scan", "30 raw OTA captures, 27 run records, measured BER vs theory; 5 closed-loop sessions (288 bursts), audit of every capture and decision"],
  ], [0.26, 0.46, 0.28], 0));
  c.push(P("The parts depend on each other: Part 2's measured packet-success curves and SNR map are the inputs to Part 1's calibrated controller; Part 2's waveforms and receivers are what Part 3 transmits and decodes; Part 3's real captures are the test set for Part 2's DL classifier; Part 3's measured BER checks the thresholds that Part 1's controller relies on; and Part 3 runs Part 1's controller, unchanged, on the real radios. Each part has its own detailed report; Appendix A maps every code file to its outputs."));

  c.push(H1("3. Methodology"));
  c.push(H2("3.1 Channel model and strategies (Part 1)"));
  c.push(P("Three channels with base SNRs of 18, 13 and 9 dB suffer time-varying interference (AR(1), coefficient 0.85, plus 6–14 dB bursts); Low, Medium and High environments set the interference level. Seven strategies are compared on identical traces: fixed QPSK on one channel, adaptive modulation only (AMC), channel switching only, hybrid, reliability-constrained, cost-aware hybrid (switching penalty 0.15, minimum gain 0.10) and the **calibrated hybrid**, which uses the measured success curves. A handoff blocks transmission for 2 steps. Each run lasts 5,000 steps; 30 seeds per environment give 630 runs."));
  c.push(H2("3.2 Calibration (Part 2)"));
  c.push(P("A GNU Radio packet receiver (RRC pulse shaping, polyphase timing recovery, carrier recovery, pilots) was run 2,070 times across 23 noise levels per modulation, with constellations normalised to equal average power. A logistic curve P(success | v) = 1 / (1 + exp(−(a + b·v))) was fitted per modulation and validated leave-one-seed-out. A separate 1,530-measurement calibration with matched clean and noisy paths maps the noise voltage v to SNR in dB, so the controller can convert a measured SNR into a success probability."));
  c.push(H2("3.3 On-air waveforms and receivers (Part 2)"));
  c.push(P("For the radios, framed bursts were designed: a 64-symbol pilot for frequency-offset estimation, a 127-chip sync word, then 1,024 payload bits in BPSK, QPSK or Gray-coded 16-QAM, at 4 samples per symbol with RRC roll-off 0.35. The receivers remove DC, convert the RTL-SDR's 2.048 MS/s to the Pluto's 2.083 MS/s, estimate frequency offset in two stages, find the sync word, track phase per block, and report BER and data-aided Es/N0."));
  c.push(H2("3.4 Hardware and safety (Part 3)"));
  c.push(P("An ADALM-Pluto (pyadi-iio, cyclic buffer) transmitted at 866 MHz, inside the 865–868 MHz short-range-device band, and an RTL-SDR (gain 28 dB, chosen from an FM-station gain test) received over the air with antennas on both. The runner only transmits after explicit enabling, a declared RF path, a band check, the operator typing TRANSMIT and a successful readback of the Pluto's frequency, gain and sample rate; the transmitter is always stopped on exit. Every capture is saved with its metadata so it can be re-decoded offline."));
  c.push(H2("3.5 Machine learning and deep learning"));
  c.push(P("**ML (Part 1):** linear regression and a random forest predict each benchmark run's throughput and PDR from its environment and strategy, with seeds kept together in the train/test split. **DL (Part 2):** a 1-D CNN (85,859 parameters) classifies 512 raw IQ samples as BPSK, QPSK or 16-QAM. It is trained on 24,000 synthetic windows passed through a simulated RTL-SDR chain (noise, frequency offset, resampling, 8-bit quantisation) and tested on the real OTA captures, which it never saw in training. A higher-order-cumulant random forest is the classical baseline."));

  c.push(H1("4. Results"));
  c.push(H2("4.1 Controller benchmark"));
  c.push(...T(["Strategy", "Throughput Low", "Medium", "High", "PDR High", "Availability High"], [
    ["fixed", "2.000", "1.980", "1.644", "0.822", "1.000"],
    ["adaptive_modulation", "3.760", "3.086", "2.296", "0.880", "1.000"],
    ["channel_switching", "2.000", "1.970", "1.752", "0.981", "0.893"],
    ["hybrid", "3.760", "2.957", "2.192", "0.988", "0.796"],
    ["reliability_constrained", "2.122", "1.875", "1.481", "0.988", "0.809"],
    ["cost_aware_hybrid", "3.760", "2.972", "2.224", "0.988", "0.819"],
    ["**calibrated_hybrid**", "**3.999**", "**3.684**", "**2.986**", "0.991", "0.825"],
  ], [0.28, 0.15, 0.13, 0.13, 0.14, 0.17], 0));
  c.push(P("Throughput in bits per step, means over 30 seeds. The calibrated hybrid is best in every environment. Against the plain hybrid its gain is +0.24, +0.73 and +0.80 bits/step at low, medium and high interference, and every 95 % paired confidence interval excludes zero; at high interference it also makes 73 fewer switches. Strategies that stay on one channel keep full availability but lose packets as interference grows (fixed: PDR 0.822), while switching strategies keep PDR near 0.99 at the cost of handoff downtime."));
  c.push(...FIG("results/figures/throughput_comparison.png", "Mean throughput per strategy and interference level.", 5.8));
  c.push(P("**Sensitivity and robustness** (`scripts/sensitivity_analysis.py`, which first reproduces all 630 benchmark runs exactly). Sweeping the switching penalty from 0 to 0.6, the calibrated hybrid's worst setting still beats the cost-aware hybrid's best in every environment, so the result does not hinge on the chosen 0.15. A penalty of 0.25 would be better (high interference: throughput 3.03, availability 0.90, 242 switches, against 2.99, 0.83 and 437 at 0.15), while a penalty so high that the controller never switches drops PDR to 0.88. When the true packet success is made 1 dB worse than the controller's model (the loss measured on air), the calibrated hybrid still has the highest throughput, but its PDR falls to 0.97 / 0.93 (medium / high). A 1 dB safety margin restores it to 0.997 / 0.988 with no throughput cost."));
  c.push(P("In the GNU Radio software-in-the-loop experiment, a scripted three-phase interference schedule made a different channel strongest in each phase; the controller switched three times, each time to the strongest channel (100 % selection accuracy), with transmission available 97.6 % of the time. In that flowgraph the three channels are the same test tone with different noise and interference levels, not separate frequencies, so it tests the decision logic only; Section 4.4 shows switching between real RF channels."));

  c.push(H2("4.2 Calibration and synchronisation"));
  c.push(...FIG("results/figures/01_packet_success_calibration.png", "Measured packet success and logistic fits vs noise voltage.", 5.6));
  c.push(P("The logistic models reach leave-one-seed-out accuracy of 97.97 % (BPSK), 99.42 % (QPSK) and 99.86 % (16-QAM). 50 % success occurs at noise voltage 0.274, 0.182 and 0.077 respectively: 16-QAM fails first, as expected. Synchronisation corrects frequency offsets up to ±2 kHz (540 trials, 0 timing errors) and sample-rate offsets up to 20 ppm; short, strong multipath echoes (2–4 samples, amplitude ≥ 0.5) remain a limitation without an equaliser."));

  c.push(H2("4.3 BER thresholds and over-the-air validation"));
  c.push(P("On synthetic frames the on-air receiver reaches BER ≤ 10⁻³ at 6.80 dB (BPSK), 9.93 dB (QPSK) and 16.67 dB (16-QAM) Es/N0, within 0.2 dB of theory. These are the modulation-switching thresholds."));
  c.push(P("Over the air, a tone test confirmed the link (tone 25–50 dB above the noise in its bin, linear with power; receiver crystal offset −10.4 kHz, −12 ppm). The first BPSK frames decoded 4/4 with 0 errors at 14–15 dB Es/N0. A sweep of all three modulations over five Pluto power settings then gave the results in Figure 4: all 76 frames detected. Each BER carries an exact 95 % confidence interval; 4 of the 9 runs with errors contain the theoretical value, and the rest are slightly worse, with an implied implementation loss of −0.2 to +0.75 dB for every run above 4 dB Es/N0."));
  c.push(...FIG("results/figures/hardware_ber_vs_theory.png", "Over-the-air BER (19 runs) with exact 95 % intervals vs AWGN theory. Triangles: zero-error runs at their 95 % bound."));
  c.push(P("**The thresholds hold on air:** 16-QAM gives 1.2 × 10⁻³ at 17.1 dB, right at its 16.7 dB threshold; QPSK is error-free from 11 to 23 dB and fails at 6.8 dB; BPSK gives 2.4 × 10⁻⁴ at 7.7 dB. The physical-layer behaviour the controller assumes is therefore what real radios deliver."));

  c.push(H2("4.4 Closed-loop channel switching on real radios"));
  c.push(P("The loop was then closed on the hardware. Each round the Pluto sent a BPSK probe on three channels (865.7, 866.5 and 867.3 MHz), the RTL-SDR measured Es/N0 on each, the unchanged calibrated controller chose a channel and modulation, and the Pluto sent a data burst accordingly. Channel quality followed a scripted schedule of TX attenuation: a different channel best in phases A–C, all mediocre in D, all poor in E. Five sessions were run on 28 Nov (antennas 1.5 m apart), two of them with a 2 dB safety margin."));
  c.push(...B([
    "**Correct channel in 72 of 72 rounds** (95 % interval 0.95–1.00); all 15 needed switches made in the first round after the change, none unnecessary, despite 1–3 dB round-to-round variation in the probes.",
    "**Modulation adapted with the channel:** 16-QAM at 18–22 dB, QPSK at about 11 dB (phase D), BPSK at about 4–8 dB (phase E).",
    "**Data BER** was close to theory for BPSK and QPSK; 16-QAM was worse (1.3 × 10⁻³ against 1.0 × 10⁻⁴ expected) because of short Es/N0 dips of several dB within a burst, which carry 68 of its 78 errors.",
    "**Safety margin:** with 2 dB the controller chose more robust modulations near the cut-offs, at about 20 % less throughput; the BER difference cannot be attributed to the margin because the link drifted by about 3 dB between sessions.",
    "**Audit:** all 288 raw captures re-decode to exactly the logged values, every Pluto readback matches its burst, and replaying the logged probe values reproduces all 72 decisions.",
  ]));
  c.push(...FIG("results/figures/closed_loop_real_session.png", "One real-radio session: probe Es/N0 per channel, chosen channel (red: switch) and chosen modulation with bit errors.", 4.5));
  c.push(P("A passive scan of 865–868 MHz found all three channels within 0.6 dB of the noise floor: left alone, the real channels would have looked identical. The differences the controller reacted to were created by the scripted TX power, not by interference."));

  c.push(H2("4.5 Machine learning on the benchmark"));
  c.push(P("The random forest explains 99.7 % of the variance in throughput and 98.5 % in PDR on held-out seeds (linear regression: 92.4 % and 54.3 %). Performance is thus almost entirely determined by environment and strategy; seed-to-seed randomness is small, so the benchmark differences are systematic. PDR needs a non-linear model because it only drops for some strategies under heavy interference."));

  c.push(H2("4.6 Deep-learning modulation classifier"));
  c.push(...T(["Test", "CNN", "Cumulant baseline"], [
    ["Synthetic, 6 dB / 10 dB / ≥ 12 dB", "94.9 % / 99.7 % / 100 %", "38.3 % / 55.9 % / 71–98 %"],
    ["**Real OTA, 536 windows**", "**98.5 %**", "62.9 %"],
    ["Real OTA, 19 captures (majority vote)", "19 / 19", "—"],
  ], [0.4, 0.3, 0.3], 0));
  c.push(...FIG("results/dl/accuracy_vs_esn0.png", "Classification accuracy vs Es/N0: synthetic curves and each real OTA capture.", 5.6));
  c.push(P("Resampling whole captures (the windows are not independent) gives a 95 % interval of 96.2–99.8 %. All 8 wrong windows had confidence below 0.9, and every window above 0.9 was correct; the CNN also recognised all 36 windows of a BPSK frame format it never saw. One damaged frame (8.8 % BER) was, however, called 16-QAM with 0.99 confidence: on corrupted data the confidence cannot be trusted."));
  c.push(P("The real captures fall on the synthetic curve, so a model trained only on simulation works on real hardware. The few errors (QPSK ↔ 16-QAM) all occur at or below 8 dB Es/N0. The classical baseline fails mainly because the residual frequency offset rotates the constellation within a window; the CNN is robust to it."));

  c.push(H1("5. Discussion"));
  c.push(...B([
    "**Measured models beat formulas.** The only difference between the hybrid and the calibrated hybrid is where the packet-success estimate comes from; using measured curves raises throughput by 6 % (low), 25 % (medium) and 36 % (high interference) and reduces switching at high interference.",
    "**Switching is a trade-off, not a free win.** Against adaptive modulation alone at high interference, the calibrated hybrid gains reliability (PDR +0.11) and throughput (+0.69) but loses availability (−0.18) to handoffs. The cost-aware rule exists to keep that loss in check.",
    "**A calibrated controller needs a safety margin.** Running close to the thresholds is what earns its throughput, and also what makes it the most sensitive to a model that is slightly optimistic. Subtracting the measured implementation loss (about 1 dB) keeps both its throughput lead and its reliability.",
    "**Simulation and hardware agree.** The thresholds derived in simulation were confirmed on real radios, the controller made the same kind of decisions on the radios as in simulation, and a classifier trained in simulation transferred to real signals. Each part's results support the others'.",
    "**What the experiments do and do not show about channels.** The GNU Radio experiment's channels differ only in noise level; the hardware demo uses separate RF channels but sets their quality by transmit power. Both show that the controller reacts correctly to measured channel quality. Neither shows behaviour under real interference, fading or other users. The calibration itself is unaffected: it describes how packet success depends on SNR for each modulation, whichever channel the SNR occurs on, and the hardware BER followed it within about 1 dB.",
  ]));

  c.push(H1("6. Limitations"));
  c.push(...B([
    "On the radios, channel quality was scripted by TX power: real interference, fading and other users were not tested. One room, one 1.5 m antenna spacing, about 35 minutes of closed-loop operation.",
    "In the GNU Radio software-in-the-loop experiment the three channels are one test tone with different noise levels, not separate frequencies.",
    "The controller decides on a probe sent seconds before the data; short dips in between caused most 16-QAM errors on air. It has no 'do not transmit' option.",
    "The OTA BER sweep is one session at one frequency, with the antenna separation not recorded and 4,096 bits per point. A zero-error run only shows BER < 7.3 × 10⁻⁴.",
    "Calibration comes from GNU Radio's synthetic AWGN channel and is valid only inside the measured noise range.",
    "No equaliser for short multipath echoes; SRO correction validated to 20 ppm.",
    "The benchmark scores every strategy with the calibrated packet model that the calibrated hybrid itself uses; the robustness study shows what happens when reality is 1–2 dB worse.",
    "The benchmark keeps the original switching penalty 0.15, although 0.25 performs better.",
    "The DL test set shares one payload and one session; the CNN has no 'no signal' class, can be confidently wrong on damaged data, and is not used by the controller.",
  ]));

  c.push(H1("7. Conclusion and future work"));
  c.push(P("The project delivers a cost-aware cognitive radio controller grounded in measured receiver behaviour, shows that it outperforms six alternatives across interference levels, and validates its physical-layer assumptions on real SDR hardware, where it also switched channel and modulation correctly in closed loop. Machine learning confirms that the benchmark differences are systematic, and deep learning recognises real over-the-air modulations after training only in simulation."));
  c.push(P("Natural next steps are: adopting a switching penalty of about 0.25 and a safety margin equal to the measured implementation loss; testing the closed loop against real interference (a second transmitter or noise sent on one channel) and over longer periods and distances; deciding on the data frame's own quality as well as the probe, and adding a 'do not transmit' option; repeating the OTA sweep with recorded geometry, more bits per point and a conducted (cable and attenuator) reference; adding an equaliser; adding a 'no signal / unknown' class to the CNN; and using it for blind modulation detection or for sensing other users' signals."));

  c.push(H1("8. Team contributions"));
  c.push(...T(["Part", "Member", "Contribution"], [
    ["1", "", "Channel and handoff model; seven controller strategies including the cost-aware and calibrated controllers; 630-run benchmark, paired statistics and figures; simulated-radio and GNU Radio software-in-the-loop experiment; ML analysis of the benchmark; switching-penalty sensitivity and implementation-loss robustness studies."],
    ["2", "", "GNU Radio packet receiver and validation; packet-success and SNR calibration; synchronisation and multipath validation; on-air frame formats and receivers; synthetic BER thresholds; DL modulation classifier, baseline and stricter evaluation."],
    ["3", "", "Pluto and RTL-SDR drivers and pure-Python transmitter; experiment runner with safety and verification gates; receive-only sensing and dataset; OTA session (gain selection, tone test, BPSK frames, BER sweep); hardware BER analysis with confidence intervals and implied loss, and the captures used to test the CNN; closed-loop channel switching on the radios, band scan, multi-session summary and offline audit."],
  ], [0.08, 0.2, 0.72], 0));

  c.push(H1("Appendix A. Code-to-output map"));
  c.push(P("Every code file in the project, what it does, and what it produces, grouped by part. Red arrows show where one part's output feeds another. The individual maps in the part reports are easier to read; the SVG version in `docs/flowcharts/` can be zoomed."));
  c.push(...FIG("docs/flowcharts/05_code_map_all.png", "All code → outputs, three parts.", 6.27, 8.4));

  c.push(H1("Appendix B. Reproducing the results"));
  c.push(...CODE([
    "conda activate cognitive-radio && pip install -r requirements.txt",
    "export PYTHONPATH=.",
    "python src/multi_seed_experiment.py",
    "python src/paired_seed_analysis.py > results/paired_seed_analysis_current.txt",
    "python src/ml_analysis.py",
    "python scripts/ber_curves.py && python scripts/plot_ber_synthetic.py",
    "python scripts/summarize_hardware_sweep.py",
    "python scripts/train_modulation_classifier.py",
    "python scripts/evaluate_dl_strict.py",
    "python scripts/sensitivity_analysis.py",
    "python scripts/summarize_closed_loop.py",
    "python -m pytest -q tests",
  ]));
  c.push(P("Any saved OTA capture can be re-decoded without hardware with `scripts/run_hardware_experiment.py --rx-file …`. Transmission requires the steps in `docs/TRANSMISSION_DAY_RUNBOOK.md`. The closed-loop raw captures (330 MB) are kept outside the repository; with them, `scripts/verify_closed_loop_captures.py` re-checks every capture and decision."));

  c.push(H1("Appendix C. Data notes"));
  c.push(...B([
    "All benchmark numbers come from `results/calibrated_multi_seed_results.csv`. The 20 Nov project guide's channel_switching rows and the older `paired_seed_analysis_v3.txt` come from an earlier run and do not match it; the unchanged analysis script was re-run on the CSV (`paired_seed_analysis_current.txt`). The calibrated-hybrid comparisons are identical in both.",
    "The 22 Nov `RESULTS_AND_DISCUSSION.md` tables did not match the CSV and were regenerated; the old versions are kept in `docs/archive/`.",
    "The 23 Nov OTA runs were started with `--rf-path conducted --attenuator-db 30` but used antennas. The records carry an `rf_path_correction` block (actual: OTA); no measurement was changed.",
  ]));
  return build(0, "Master_Report.docx", c);
};
