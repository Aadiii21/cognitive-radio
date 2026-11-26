const { P, H1, H2, B, NUM, CODE, NOTE, T, FIG, cover, build, resetFig } = require("./lib");

module.exports = function part1() {
  resetFig();
  const c = [];
  c.push(...cover(1, "Simulation, Cognitive Control and ML Analysis",
    "The decision-making side of the cognitive radio: the channel model, the controllers that choose a channel and a modulation, the 630-run benchmark that compares seven strategies, the paired statistics, the software-in-the-loop experiments and the machine-learning analysis of the results."));

  c.push(H1("1. Purpose of this part"));
  c.push(P("A cognitive radio must decide, at every time step, **which channel** to use and **which modulation** (BPSK, QPSK or 16-QAM) to send on it. A faster modulation carries more bits per symbol but fails at lower SNR; switching to a better channel costs time because transmission stops during the handoff. Part 1 builds and evaluates the decision logic that balances these effects."));
  c.push(P("The central idea is the **expected utility**: nominal data rate × estimated packet-success probability. The controller picks the channel and modulation with the highest utility, and only switches channel when the gain outweighs the switching cost."));
  c.push(...B([
    "**Input from Part 2:** the packet-success model (logistic curves fitted to GNU Radio receiver trials) and the SNR → noise-voltage calibration.",
    "**Output to the project:** the controller design, the benchmark showing which strategy is best in each interference level, and the ML analysis of those results.",
    "**Link to Part 3:** the modulation-switching thresholds used by the controller were checked against real over-the-air BER measurements in Part 3.",
  ]));

  c.push(H1("2. Where this part fits"));
  c.push(P("Figure 1 shows the whole project. Part 1 is the blue block on the left: it consumes the calibration from Part 2 and produces the benchmark, statistics and ML results."));
  c.push(...FIG("docs/flowcharts/01_project_workflow.png", "Project workflow. Blue: Part 1 (this report). Green: Part 2. Orange: Part 3."));

  c.push(H1("3. Code in this part"));
  c.push(P("Figure 2 maps every Part 1 code file to the outputs it produces. Dashed arrows show which code uses which; solid arrows lead to output files."));
  c.push(...FIG("docs/flowcharts/02_code_map_part1.png", "Part 1 code → outputs map.", 6.27, 7.6));
  c.push(H2("3.1 Code files and their role"));
  c.push(...T(["File(s)", "Role"], [
    ["src/channel_model.py", "Three candidate channels with base SNRs 18, 13 and 9 dB. Interference keeps 0.85 of its previous value plus Gaussian variation, with occasional 6–14 dB bursts; 1 dB measurement noise; SNR clipped to −5…30 dB. Seeded and reproducible. (channel_model_v1.py is the earlier version, kept for history.)"],
    ["src/metrics.py", "Packet-delivery ratio (PDR), throughput per step, service availability, switch count; also the early, uncalibrated packet-success model."],
    ["src/switching.py", "SwitchingDelay: during a handoff, transmission is blocked for a set number of steps (2 in the benchmark)."],
    ["src/controller.py", "Main controller: picks modulation by rate × success probability; optional PDR target, rolling PDR, hysteresis, dwell time and switch cost. Returns a Decision."],
    ["src/controller_cost_aware.py", "Discounts the alternative channel's utility by a switching penalty (0.15) and requires a minimum utility gain (0.10) before switching."],
    ["src/calibrated_controller.py", "Extends the cost-aware controller with the empirical models from Part 2: SNR → noise voltage → logistic packet success for each modulation."],
    ["src/controller_reliability_v1.py, _v2.py\nsrc/modulation_policy.py", "Reliability-constrained controller experiments (first meet a PDR target, then maximise rate) and a fixed-threshold modulation helper."],
    ["src/simulate.py, simulate_baseline.py, simulate_cost_aware.py, simulate_reliability_v1/v2.py, dwell_sweep.py", "Earlier simulation runners and parameter sweeps (dwell time, reliability target), kept for the development record."],
    ["src/multi_seed_experiment.py", "Final benchmark: one 5,000-step trace per seed and environment, shared by all strategies; 3 environments × 30 seeds × 7 strategies = 630 runs."],
    ["src/paired_seed_analysis.py", "Matches strategies on the same seed and environment and reports paired differences with 95 % t-confidence intervals."],
    ["src/analyze_benchmark.py, scripts/final_validation.sh", "Benchmark summary table and figures; the shell script regenerates final plots and per-environment tables."],
    ["src/ml_analysis.py", "Machine-learning analysis of the benchmark: linear regression and random forest with a seed-grouped train/test split."],
    ["src/radio/base.py, simulated_radio.py\nsrc/run_radio_controller.py", "Radio abstraction (RadioInterface) and a simulated radio; runs the calibrated controller against it as if it were real hardware."],
    ["src/gnuradio_adapter.py, gnuradio_controller.py, gnuradio_joint_controller.py, gnuradio/joint_cognitive_radio.py and the gnuradio/test_* control-path scripts", "Puts the controller inside GNU Radio: SNR streams in, channel / modulation / transmit-enable messages out, with a handoff countdown."],
    ["experiments/automatic_interference.py, analyze_interference.py, calculate_metrics.py, calculate_availability.py, finalize_experiment.py, plot_experiment.py", "Software-in-the-loop experiment: a three-phase interference schedule drives the GNU Radio flowgraph; the scripts parse the log and compute metrics and plots."],
  ], [0.36, 0.64], 1));

  c.push(H1("4. Outputs and what they signify"));
  c.push(...T(["Output", "Produced by", "Contents", "What it signifies"], [
    ["results/calibrated_multi_seed_results.csv", "multi_seed_experiment.py", "630 rows: environment, seed, strategy, PDR, throughput, availability, switches, attempts", "The main evidence: how each strategy performs under matched conditions"],
    ["results/figures/benchmark_summary.csv\nthroughput_comparison.png, pdr_comparison.png, switching_availability.png", "analyze_benchmark.py", "Mean and SD of each metric per strategy and environment; bar charts", "Which strategy delivers most data, and what it costs in handoffs and downtime"],
    ["results/final/plots/, results/final/tables/", "final_validation.sh", "Per-environment tables and plots of PDR, throughput, availability, switching overhead", "Report-ready versions of the benchmark"],
    ["results/paired_seed_analysis_current.txt", "paired_seed_analysis.py (re-run 25 Nov)", "Paired deltas and 95 % CIs for every strategy pair", "Whether a difference between two strategies is statistically real"],
    ["results/ml/ (model_comparison.csv, feature_importance_*.csv, performance_by_environment.csv, plots/)", "ml_analysis.py", "R², MAE and RMSE of each model; permutation importance; actual-vs-predicted and residual plots", "How strongly the environment and strategy determine throughput and PDR"],
    ["results/sensitivity/ (penalty_sweep, implementation_loss, safety_margin .csv/.png, summary.json)", "scripts/sensitivity_analysis.py", "Means and 95 % CIs over 30 seeds for each penalty, loss and margin", "Whether the result depends on the chosen penalty and survives a less-than-ideal radio"],
    ["results/decision_trace.csv, automatic_interference_events.csv, final_experiment_metrics.csv, cognitive_radio_experiment_final.png", "experiments/*", "Time-stamped SNR, channel, modulation and enable state; summary metrics", "The controller picks the best channel in real time inside GNU Radio"],
    ["results/baseline.txt, cost_aware.txt, simulate_v6.txt, dwell_sweep*.txt, reliability_sweep*.txt", "earlier runners", "Console summaries", "Development history; shows how the design was tuned"],
  ], [0.27, 0.17, 0.30, 0.26], 1));

  c.push(H1("5. Results"));
  c.push(H2("5.1 The seven strategies"));
  c.push(...T(["Strategy", "Channel", "Modulation"], [
    ["fixed", "stays on channel 0", "fixed QPSK"],
    ["adaptive_modulation (AMC)", "stays on channel 0", "best modulation for the current SNR"],
    ["channel_switching", "best channel", "fixed QPSK"],
    ["hybrid", "best channel", "adaptive"],
    ["reliability_constrained", "best channel", "fastest modulation that meets a PDR target"],
    ["cost_aware_hybrid", "switches only if the gain beats the switching cost", "adaptive"],
    ["calibrated_hybrid", "cost-aware switching", "adaptive, using the calibrated packet-success models"],
  ], [0.3, 0.36, 0.34], 1));

  c.push(H2("5.2 Benchmark (630 runs)"));
  c.push(P("Means over 30 seeds, computed from `results/calibrated_multi_seed_results.csv`. Throughput is delivered bits per time step; availability is the fraction of steps when transmission was allowed."));
  const env = {
    Low: [["fixed", "1.000", "2.000", "1.000", "0"], ["adaptive_modulation", "1.000", "3.760", "1.000", "0"], ["channel_switching", "1.000", "2.000", "1.000", "0"], ["hybrid", "1.000", "3.760", "1.000", "0.3"], ["reliability_constrained", "1.000", "2.122", "0.999", "3.0"], ["cost_aware_hybrid", "1.000", "3.760", "1.000", "0"], ["**calibrated_hybrid**", "1.000", "**3.999**", "1.000", "0.5"]],
    Medium: [["fixed", "0.990", "1.980", "1.000", "0"], ["adaptive_modulation", "0.997", "3.086", "1.000", "0"], ["channel_switching", "1.000", "1.970", "0.985", "37.2"], ["hybrid", "1.000", "2.957", "0.928", "181.1"], ["reliability_constrained", "1.000", "1.875", "0.918", "206.1"], ["cost_aware_hybrid", "1.000", "2.972", "0.939", "151.6"], ["**calibrated_hybrid**", "0.999", "**3.684**", "0.933", "167.1"]],
    High: [["fixed", "0.822", "1.644", "1.000", "0"], ["adaptive_modulation", "0.880", "2.296", "1.000", "0"], ["channel_switching", "0.981", "1.752", "0.893", "266.6"], ["hybrid", "0.988", "2.192", "0.796", "509.2"], ["reliability_constrained", "0.988", "1.481", "0.809", "478.1"], ["cost_aware_hybrid", "0.988", "2.224", "0.819", "452.1"], ["**calibrated_hybrid**", "0.991", "**2.986**", "0.825", "436.6"]],
  };
  const rows = [];
  for (const e of ["Low", "Medium", "High"]) for (const r of env[e]) rows.push([e, ...r]);
  c.push(...T(["Interference", "Strategy", "PDR", "Throughput", "Availability", "Switches"], rows, [0.14, 0.32, 0.12, 0.15, 0.15, 0.12], 1));
  c.push(P("**What it shows.** With low interference every strategy delivers all packets, so throughput depends only on the modulation chosen; the calibrated hybrid is highest (3.999 of a possible 4 bits/step). With medium and high interference, staying on one channel loses packets (fixed: PDR 0.822 at high interference), while switching restores reliability (PDR ≈ 0.99) at the cost of downtime. The **calibrated hybrid gives the highest throughput in all three environments**, because its calibrated success curves let it use higher-order modulation safely and switch less often than the plain hybrid."));
  c.push(...FIG("results/figures/throughput_comparison.png", "Mean throughput per strategy and interference level (analyze_benchmark.py)."));
  c.push(...FIG("results/figures/switching_availability.png", "Switch count and service availability: the cost of channel switching."));

  c.push(H2("5.3 Paired statistics"));
  c.push(P("Each pair of strategies runs on identical channel traces, so their difference is measured per seed and its 95 % confidence interval is computed from 30 pairs. Selected results (positive = first strategy higher):"));
  c.push(...T(["Comparison", "Interference", "Throughput Δ (95 % CI)", "Other differences"], [
    ["calibrated_hybrid vs hybrid", "Low", "+0.239 (+0.230, +0.248)", "PDR and availability unchanged"],
    ["calibrated_hybrid vs hybrid", "Medium", "+0.727 (+0.714, +0.740)", "availability +0.006; switches −14.0; PDR −0.001"],
    ["calibrated_hybrid vs hybrid", "High", "+0.795 (+0.781, +0.809)", "availability +0.029; switches −72.6; PDR +0.003"],
    ["calibrated_hybrid vs adaptive_modulation", "High", "+0.690 (+0.672, +0.708)", "PDR +0.112; availability −0.175 (handoff downtime)"],
    ["cost_aware_hybrid vs hybrid", "Medium", "+0.015 (+0.012, +0.017)", "switches −29.5; availability +0.012"],
  ], [0.32, 0.14, 0.25, 0.29], 1));
  c.push(P("**What it shows.** Every interval excludes zero, so the calibrated hybrid's throughput gain is not chance. Against AMC-only at high interference it trades availability for much better reliability: a genuine reliability / throughput / availability trade-off rather than a free win."));

  c.push(H2("5.4 Software-in-the-loop GNU Radio experiment"));
  c.push(P("The controller ran inside the GNU Radio flowgraph while a scripted schedule made a different channel strongest in each of three phases. `results/final_experiment_metrics.csv` records 312 decisions over 31.0 s: **3 channel switches, all to the strongest channel (100 % selection accuracy)**, transmission available 97.6 % of the time (0.76 s disabled during handoffs), and every controller event selected 16-QAM because the strongest channel stayed near 23 dB."));
  c.push(...FIG("results/cognitive_radio_experiment_final.png", "Measured SNR, selected channel and transmission state during the three-phase interference experiment.", 6.27, 5.2));
  c.push(P("The simulated-radio run (`run_radio_controller.py`, recorded in the 20 Nov project guide) exercises the same controller through the RadioInterface: over 5,000 steps at high interference, PDR 0.991, availability 0.832 and 420 switches; the unavailable steps equal exactly two per switch, confirming the handoff accounting."));

  c.push(H2("5.5 Machine-learning analysis of the benchmark"));
  c.push(P("`src/ml_analysis.py` asks how well the experimental conditions (environment and strategy, one-hot encoded) predict each run's throughput and PDR. Seeds are kept together in the train/test split so that runs sharing a channel trace never appear on both sides (no leakage)."));
  c.push(...T(["Target", "Model", "MAE", "RMSE", "R²"], [
    ["Throughput", "Mean-value baseline", "0.728", "0.801", "0.000"],
    ["Throughput", "Linear regression", "0.176", "0.220", "0.924"],
    ["Throughput", "Random forest", "0.029", "0.045", "**0.997**"],
    ["PDR", "Mean-value baseline", "0.025", "0.045", "0.000"],
    ["PDR", "Linear regression", "0.024", "0.030", "0.543"],
    ["PDR", "Random forest", "0.002", "0.006", "**0.985**"],
  ], [0.2, 0.32, 0.16, 0.16, 0.16], 1));
  c.push(P("**What it shows.** The random forest explains 99.7 % of the throughput variance and 98.5 % of the PDR variance, so performance is almost fully determined by the environment and strategy, and seed-to-seed randomness is small: the benchmark differences are systematic. The linear model does much worse on PDR (R² 0.543) because PDR interacts non-linearly: it only drops for some strategies in high interference. Permutation importance puts **environment_Low** first for throughput (0.36), followed by the choice of strategy."));
  c.push(...FIG("results/ml/plots/throughput_bits_per_step_actual_vs_predicted.png", "Random forest: predicted vs actual throughput on held-out seeds.", 5.0));

  c.push(H2("5.6 Sensitivity and robustness"));
  c.push(P("Two questions an examiner would ask: does the result depend on the hand-picked switching penalty (0.15), and does it survive if the real radio is a little worse than the model? `scripts/sensitivity_analysis.py` answers both using the unchanged benchmark components. As a check, it first reproduces all 630 benchmark runs exactly (largest difference 1 × 10⁻¹⁶)."));
  c.push(P("**Switching-penalty sweep** (penalty 0 to 0.6, 30 seeds per point):"));
  c.push(...T(["Interference", "Penalty", "Throughput", "PDR", "Availability", "Switches"], [
    ["Medium", "0.15 (benchmark)", "3.684", "0.9987", "0.933", "167"],
    ["Medium", "**0.25**", "**3.733**", "0.9973", "**0.987**", "**33**"],
    ["Medium", "0.60 (never switches)", "3.803", "0.9952", "1.000", "0"],
    ["High", "0.15 (benchmark)", "2.986", "0.991", "0.825", "437"],
    ["High", "**0.25**", "**3.028**", "0.990", "**0.903**", "**242**"],
    ["High", "0.60 (never switches)", "2.936", "**0.876**", "1.000", "0"],
  ], [0.16, 0.26, 0.15, 0.13, 0.15, 0.15], 1));
  c.push(...B([
    "**The main result does not depend on the penalty:** the calibrated hybrid's worst setting beats the cost-aware hybrid's best setting in every environment.",
    "**0.15 is not the best setting.** At 0.25 the calibrated hybrid gets more throughput, much higher availability and far fewer switches, for a negligible PDR cost. The benchmark keeps 0.15 for consistency with the original results; 0.25 is the recommended setting.",
    "**Too high a penalty means the controller never switches** and reliability collapses at high interference (PDR 0.876). Switching mainly buys reliability; most of the throughput gain comes from the calibrated modulation choice.",
  ]));
  c.push(...FIG("results/sensitivity/penalty_sweep.png", "Throughput, availability and PDR vs switching penalty (bars: 95 % CI over 30 seeds; dotted line: 0.15)."));
  c.push(P("**Implementation loss.** The over-the-air tests (Part 3) showed the real link up to about 0.75 dB worse than theory. To test the effect, the true packet success was drawn at SNR − loss (1 dB realistic, 2 dB stress test) while every controller still trusted its model."));
  c.push(...FIG("results/sensitivity/implementation_loss.png", "Throughput and PDR of all seven strategies with 0, 1 and 2 dB implementation loss."));
  c.push(...T(["1 dB loss", "Throughput Medium / High", "PDR Medium / High"], [
    ["calibrated hybrid, no margin", "3.575 / 2.812", "0.969 / 0.933"],
    ["**calibrated hybrid, 1 dB safety margin**", "**3.600 / 2.877**", "**0.997 / 0.988**"],
    ["best other strategy (AMC)", "3.085 / 2.282", "0.996 / 0.866"],
  ], [0.42, 0.29, 0.29], 1));
  c.push(P("**What it shows.** The calibrated hybrid keeps the highest throughput under both 1 and 2 dB loss. It is, however, the most sensitive strategy, because it deliberately runs close to the modulation thresholds: without a margin its PDR falls to 0.969 / 0.933 at 1 dB loss. Making the controller subtract a safety margin equal to the measured loss restores PDR to 0.997 / 0.988 and even raises throughput, because fewer packets fail. With 2 dB loss and a 2 dB margin, PDR is 0.996 / 0.981. **Lesson:** a calibrated controller should carry a margin equal to the hardware's measured implementation loss."));

  c.push(H1("6. How to reproduce"));
  c.push(...CODE([
    "export PYTHONPATH=.",
    "python src/multi_seed_experiment.py",
    "python src/paired_seed_analysis.py > results/paired_seed_analysis_current.txt",
    "python src/analyze_benchmark.py",
    "python src/ml_analysis.py",
    "bash scripts/final_validation.sh",
    "python src/run_radio_controller.py",
    "python scripts/sensitivity_analysis.py --check",
    "python scripts/sensitivity_analysis.py",
    "python -m pytest -q tests/test_controller.py tests/test_cost_aware_controller.py \\",
    "    tests/test_radio_interface.py",
  ]));
  c.push(P("In order: the 630-run benchmark, paired statistics, figures, ML analysis, the full validation script (tests, final plots and tables), the simulated-radio run, the check that the sensitivity harness reproduces the benchmark, the sensitivity and robustness studies (about 30 minutes on a laptop), and the Part 1 unit tests."));

  c.push(H1("7. Limitations"));
  c.push(...B([
    "The benchmark is a calibrated **simulation**: packet outcomes are drawn from the fitted success curves, not decoded packet by packet. A hardware closed loop (controller driving the radios) was removed from the project scope on 23 Nov.",
    "The logistic models are only valid inside the calibrated noise range; outside it the controller clips to the nearest calibrated value.",
    "`channel_switching` uses fixed QPSK, not fixed BPSK as described in the 6 Nov plan.",
    "**Data note:** the 20 Nov guide's channel_switching rows (e.g. Medium: throughput 1.855, availability 0.928, 181 switches) and the older `paired_seed_analysis_v3.txt` do not match the current 630-row CSV; they come from an earlier run. This report uses the CSV and a fresh re-run of the unchanged paired-analysis script (`paired_seed_analysis_current.txt`). The calibrated-hybrid comparisons are identical in both.",
    "The ML models describe this benchmark; they do not predict performance on new radios or channel models.",
    "The benchmark scores every strategy with the calibrated packet model, which the calibrated hybrid itself uses, so it is judged on the model it knows. Section 5.6 tests what happens when reality is 1–2 dB worse than that model: it still leads in throughput, but needs a safety margin to keep its reliability.",
    "The benchmark uses switching penalty 0.15; the sweep shows 0.25 is better. The original results were kept unchanged for consistency.",
  ]));

  c.push(H1("8. Contribution summary"));
  c.push(P("The member responsible for Part 1 owns:"));
  c.push(...B([
    "the channel model, metrics and handoff model;",
    "the seven controller strategies, including the cost-aware and calibrated controllers;",
    "the 630-run multi-seed benchmark, paired statistics and benchmark figures;",
    "the radio abstraction and simulated-radio integration, and the GNU Radio software-in-the-loop experiment;",
    "the machine-learning analysis of the benchmark results;",
    "the switching-penalty sensitivity study and the implementation-loss / safety-margin robustness study.",
  ]));
  return build(1, "Part1_Simulation_Control_ML_Report.docx", c);
};
