#!/usr/bin/env python3
"""Project flowcharts (Graphviz): workflow + code-to-output maps.

    python scripts/make_flowcharts.py          # needs the `dot` binary (graphviz)

Writes docs/flowcharts/*.dot, *.svg and *.png:
  01_project_workflow      how the project works, end to end
  02_code_map_part1        Part 1 code -> outputs (simulation, control, ML)
  03_code_map_part2        Part 2 code -> outputs (PHY, calibration, receivers, DL)
  04_code_map_part3        Part 3 code -> outputs (SDR hardware, OTA experiments)
  05_code_map_all          all three parts in one chart
The PART_* tables below are the single source for the code maps and the reports.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "flowcharts"

COLORS = {  # (code fill, output fill, border)
    1: ("#DCE8F7", "#F2F7FC", "#2F5D8A"),
    2: ("#D9EFE4", "#F1F9F5", "#2E7D57"),
    3: ("#FBE5D0", "#FDF4EA", "#B8621B"),
}
TITLES = {
    1: "Part 1: Simulation, cognitive control and ML analysis",
    2: "Part 2: Physical layer, calibration, receivers and DL classifier",
    3: "Part 3: SDR hardware integration and OTA experiments",
}

# Each entry: (node id, code files, what it does, [outputs]); outputs: (label, meaning)
PART_1 = [
    ("chan", "src/channel_model.py\n(channel_model_v1.py: history)",
     "3-channel SNR traces with interference", []),
    ("metr", "src/metrics.py · src/switching.py",
     "PDR / throughput / availability; handoff delay", []),
    ("ctrl", "src/controller.py · controller_cost_aware.py\ncontroller_reliability_v1/v2.py · modulation_policy.py",
     "Baseline, AMC, switching, hybrid, cost-aware decisions", []),
    ("cal", "src/calibrated_controller.py",
     "Utility = rate x logistic packet success", []),
    ("sims", "src/simulate*.py · dwell_sweep.py",
     "Early strategy runs and parameter sweeps",
     [("results/baseline.txt · cost_aware.txt\nsimulate_v6.txt", "early strategy summaries"),
      ("results/reliability_sweep*.txt\ndwell_sweep*.txt", "effect of PDR target / dwell time")]),
    ("bench", "src/multi_seed_experiment.py",
     "630 runs: 3 environments x 30 seeds x 7 strategies",
     [("results/calibrated_multi_seed_results.csv", "main benchmark dataset (630 rows)")]),
    ("pair", "src/paired_seed_analysis.py",
     "Paired differences, 95 % CIs",
     [("results/paired_seed_analysis_v3.txt", "is strategy A really better than B?")]),
    ("anal", "src/analyze_benchmark.py · scripts/final_validation.sh",
     "Benchmark figures and tables",
     [("results/figures/throughput_comparison.png\npdr_comparison.png · switching_availability.png",
       "strategy comparison"),
      ("results/final/plots/ · tables/", "per-environment PDR, throughput, availability")]),
    ("ml", "src/ml_analysis.py",
     "Linear regression + random forest (seed-grouped split)",
     [("results/ml/", "how well conditions predict throughput / PDR")]),
    ("sens", "scripts/sensitivity_analysis.py",
     "Switching-penalty sweep; 1-2 dB implementation loss; safety margin",
     [("results/sensitivity/ (penalty_sweep, implementation_loss,\nsafety_margin .csv/.png)",
       "result holds for any penalty; 0.25 better; 1 dB margin restores PDR")]),
    ("srad", "src/radio/base.py · simulated_radio.py\nsrc/run_radio_controller.py",
     "Controller driving a simulated radio",
     [("console metrics (500 / 5,000 steps)", "control loop works end to end in software")]),
    ("grctl", "src/gnuradio_adapter.py · gnuradio_controller.py\ngnuradio_joint_controller.py · gnuradio/joint_cognitive_radio.py\n"
              "gnuradio/test_*control*, test_*switch*, test_channel_selector, test_transmission_gate",
     "Controller inside GNU Radio flowgraphs", []),
    ("exp", "experiments/automatic_interference.py\nanalyze_interference · calculate_* · finalize · plot_experiment",
     "Live 3-phase interference experiment",
     [("results/decision_trace.csv\nautomatic_interference_events.csv", "decision log over time"),
      ("results/final_experiment_metrics.csv\ncognitive_radio_experiment_final.png", "channel picked correctly? availability")]),
]
PART_1_EDGES = [("chan", "ctrl"), ("metr", "ctrl"), ("ctrl", "cal"), ("ctrl", "sims"), ("cal", "bench"),
                ("chan", "bench"), ("bench", "pair"), ("bench", "anal"), ("bench", "ml"), ("cal", "srad"), ("bench", "sens"),
                ("ctrl", "grctl"), ("grctl", "exp")]

PART_2 = [
    ("prx", "gnuradio/packet_receiver_general.py\n(packet_receiver_test*.py: history)",
     "BPSK/QPSK/16-QAM packet receiver",
     [("results/packet_receiver_*_validation.csv\npacket_receiver_seed_sweep.csv", "receiver decodes each modulation")]),
    ("dev", "gnuradio/first_signal · packet_link_test · ideal_16qam\npulse_shaping / timing / carrier_recovery_16qam\nchannel_transparency · channel_receiver_alignment",
     "Receiver development checks", []),
    ("calib", "gnuradio/calibrate_receiver.py\nrefine_calibration.py · expand_calibration.py",
     "Packet success vs noise voltage (equal power)",
     [("results/equal_power_modulation_calibration.csv (330)\nrefined_... (930) · expanded_... (2,070)",
       "packet success measured per modulation")]),
    ("logit", "gnuradio/analyze_calibration.py\nvalidate_logistic_models.py",
     "Logistic fit + leave-one-seed-out check",
     [("coefficients a, b per modulation\nBrier / log loss / accuracy", "packet-success model used by Part 1")]),
    ("snr", "gnuradio/measure_channel_snr.py · extend_*_snr.py\nsnr_measurement · receiver_snr_estimator\ntest_three_channel_estimators.py",
     "Noise voltage <-> SNR (matched paths)",
     [("results/channel_snr_calibration.csv (1,530)\nchannel_snr_extension*.csv", "SNR in dB for each noise voltage")]),
    ("ncal", "src/noise_calibration.py",
     "Interpolates SNR -> noise voltage", []),
    ("fac", "src/generate_faculty_results.py",
     "Calibration figures",
     [("results/figures/01_packet_success_calibration.png\n02_snr_noise_comparison.png", "calibration curves")]),
    ("sync", "src/receiver_sync.py · multipath_channel.py\nsrc/validate_*_sync.py · validate_*_correction.py\nvalidate_multipath.py · validate_reference_snr.py",
     "Timing / CFO / SRO / multipath synchronisation",
     [("results/synchronization/**\n*_sync_validation_*.csv", "sync accuracy under each impairment")]),
    ("wave", "src/radio/waveform_generator.py · bpsk_frame.py\nmultimod_frame.py · scripts/run_multimod_experiment.py",
     "Framed BPSK/QPSK/16-QAM waveforms",
     [("results/baseband/prepared/bpsk_frame_v2_seed42.*\nresults/baseband/multimod_v2/*", "TX files used by Part 3")]),
    ("rx", "src/radio/bpsk_receiver.py\nmultimod_receiver.py",
     "Frame sync, CFO, phase tracking, BER, Es/N0", []),
    ("ber", "scripts/ber_curves.py · plot_ber_synthetic.py\nsrc/radio/cognitive_controller.py",
     "Synthetic BER vs Es/N0, switching thresholds",
     [("results/analysis/ber_vs_snr_multimod_synthetic.csv\ncontroller_thresholds_synthetic.json\nresults/figures/ber_vs_esn0_synthetic.png",
       "BER<=1e-3 at 6.8 / 9.9 / 16.7 dB")]),
    ("dl", "src/dl/modulation_classifier.py\nscripts/train_modulation_classifier.py\nscripts/evaluate_dl_strict.py",
     "CNN: recognise modulation from IQ",
     [("results/dl/ (model, metrics.json, strict_evaluation.json, plots)", "98.5 % on real OTA (CI 96.2-99.8 %)")]),
]
PART_2_EDGES = [("dev", "prx"), ("prx", "calib"), ("calib", "logit"), ("snr", "ncal"), ("logit", "fac"),
                ("snr", "fac"), ("sync", "rx"), ("wave", "rx"), ("rx", "ber"), ("wave", "dl")]

PART_3 = [
    ("hcfg", "src/radio/hardware_config.py",
     "Pluto URI, rates, verified limits", []),
    ("tx", "src/radio/pluto_pyadi_tx.py (default)\npluto_tx_adapter.py · pluto_transmitter.py",
     "Pluto TX: cyclic buffer, gain, LO", []),
    ("rxh", "src/radio/rtl_sdr_sensor.py · rtl_capture.py\npluto_sensor.py",
     "RTL-SDR / Pluto receive and sensing", []),
    ("sense", "src/hardware_dual_sensor.py",
     "Power sensing on 3 channels",
     [("results/hardware_corrected/ · hardware_stability/\ndual_sensor_*.csv", "measured channel power, decisions")]),
    ("dset", "src/radio/capture_rtl_dataset.py\nsrc/extract_features.py",
     "RTL capture dataset + spectral features",
     [("data/raw · data/metadata\nresults/features/*.csv", "labelled captures and features")]),
    ("rplot", "src/plot_rtlsdr_scan.py · plot_rtlsdr_peaks.py\nplot_iq_comparison.py",
     "FM / spectrum survey plots",
     [("results/figures/rtl_sdr_*.png\nrtl_sdr_fm_scan.csv", "RTL-SDR works; spectrum view")]),
    ("run", "scripts/run_hardware_experiment.py",
     "Safe OTA runner: gates, TX, capture, decode",
     [("results/hardware/captures/*.cu8 + .json", "raw IQ + metadata per run"),
      ("results/hardware/experiment_results/*.json\nresults/hardware/day_01_*.log",
       "tone detection, frames, BER, Es/N0")]),
    ("annot", "scripts/annotate_rf_path.py",
     "Records the real RF path (OTA)",
     [("rf_path_correction in run JSONs", "honest labelling of 23 Nov runs")]),
    ("sweep", "scripts/summarize_hardware_sweep.py",
     "Hardware BER table, 95 % CIs, implied loss, figure",
     [("results/analysis/hardware_ber_runs.csv (19 runs)\nresults/figures/hardware_ber_vs_theory.png",
       "measured BER ~ AWGN theory; thresholds hold")]),
    ("cl", "scripts/run_channel_switching_demo.py",
     "Closed loop: probe 3 channels -> calibrated controller -> TX on chosen channel",
     [("results/hardware/closed_loop/session_*/\n(rounds.csv, session.json, session.png)", "channel switching on real radios: 5 sessions")]),
    ("clsum", "scripts/summarize_closed_loop.py · verify_closed_loop_captures.py",
     "Pool sessions with 95 % CIs; re-decode every capture, replay every decision",
     [("results/analysis/closed_loop_summary.json · closed_loop_verification.json\nresults/figures/closed_loop_repeatability.png",
       "best channel 72/72; 15/15 switches; audit OK")]),
    ("scan", "scripts/scan_band.py",
     "Passive scan of 865-868 MHz (receive only)",
     [("results/hardware/band_scan/scan_*/ (scan.png, summary.json)", "real channels quiet: within 0.6 dB of floor")]),
    ("pipe", "pipelines/integrated_pipeline.py\n(scripts/pluto_to_rtl_sdr_demo.py, test_pluto_tx_adapter.py: legacy)",
     "Software-mode pipeline; RF path disabled",
     [("results/pipeline/", "software-only run")]),
]
PART_3_EDGES = [("hcfg", "tx"), ("hcfg", "rxh"), ("rxh", "sense"), ("rxh", "dset"), ("rxh", "rplot"),
                ("tx", "run"), ("rxh", "run"), ("run", "annot"), ("run", "sweep"), ("tx", "cl"), ("rxh", "cl"),
                ("cl", "clsum"), ("rxh", "scan")]

PARTS = {1: (PART_1, PART_1_EDGES), 2: (PART_2, PART_2_EDGES), 3: (PART_3, PART_3_EDGES)}
CROSS_EDGES = [  # (part, node) -> (part, node), label
    ((2, "logit"), (1, "cal"), "packet-success model"),
    ((2, "ncal"), (1, "cal"), "SNR -> noise voltage"),
    ((2, "wave"), (3, "run"), "TX waveforms"),
    ((2, "rx"), (3, "run"), "receivers"),
    ((2, "ber"), (3, "sweep"), "theory / thresholds"),
    ((3, "run"), (2, "dl"), "real captures (test set)"),
    ((1, "cal"), (3, "cl"), "controller"),
]


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def part_body(n, prefix=""):
    entries, edges = PARTS[n]
    code_fill, out_fill, border = COLORS[n]
    lines = []
    for nid, code, does, outs in entries:
        lines.append(f'  {prefix}{nid} [shape=box, style="rounded,filled", fillcolor="{code_fill}", '
                     f'color="{border}", label="{esc(code)}\\n— {esc(does)}"];')
        for i, (label, meaning) in enumerate(outs):
            lines.append(f'  {prefix}{nid}_o{i} [shape=note, style=filled, fillcolor="{out_fill}", color="{border}", '
                         f'fontsize=9, label="{esc(label)}\\n→ {esc(meaning)}"];')
            lines.append(f'  {prefix}{nid} -> {prefix}{nid}_o{i} [color="{border}"];')
    # code column on the left, outputs on the right: a portrait-friendly 2-column chart
    lines.append("  { rank=same; " + " ".join(f"{prefix}{e[0]};" for e in entries) + " }")
    order = [f"{prefix}{e[0]}" for e in entries]
    for a, b in zip(order, order[1:]):
        lines.append(f"  {a} -> {b} [style=invis];")
    for a, b in edges:
        lines.append(f'  {prefix}{a} -> {prefix}{b} [style=dashed, color="#777777", constraint=false];')
    return lines


HEAD = ('digraph G {\n  graph [rankdir=LR, fontname="Helvetica", fontsize=16, labelloc=t, nodesep=0.25, '
        'ranksep=0.45, pad=0.3];\n  node [fontname="Helvetica", fontsize=10, margin="0.12,0.06"];\n'
        '  edge [arrowsize=0.7, fontname="Helvetica"];\n')
LEGEND = ('  legend [shape=plaintext, fontsize=9, label="Box = code (— what it does)   Note = output (→ what it shows)'
          '   Dashed = code dependency"];\n')


def code_map(n):
    return HEAD + f'  label="{TITLES[n]}: code → outputs";\n' + "\n".join(part_body(n)) + "\n" + LEGEND + "}\n"


def code_map_all():
    s = HEAD.replace("rankdir=LR", "rankdir=LR, newrank=true")
    s += '  label="Cognitive radio project: all code → outputs (3 parts)";\n'
    for n in (1, 2, 3):
        s += f'  subgraph cluster_p{n} {{\n  label="{TITLES[n]}"; style="rounded"; color="{COLORS[n][2]}"; fontsize=14;\n'
        s += "\n".join(part_body(n, prefix=f"p{n}_")) + "\n  }\n"
    for (pa, a), (pb, b), lab in CROSS_EDGES:
        s += f'  p{pa}_{a} -> p{pb}_{b} [color="#C0392B", penwidth=1.4, fontsize=9, fontcolor="#C0392B", label="{lab}"];\n'
    return s + LEGEND + "}\n"


def workflow():
    c = {n: COLORS[n] for n in COLORS}

    def box(nid, label, n, shape="box"):
        return (f'  {nid} [shape={shape}, style="rounded,filled", fillcolor="{c[n][0]}", color="{c[n][2]}", '
                f'label="{esc(label)}"];\n')

    s = ('digraph W {\n  graph [rankdir=TB, fontname="Helvetica", fontsize=18, labelloc=t, nodesep=0.35, ranksep=0.4, '
         'pad=0.3, newrank=true,\n  label="Cognitive radio project: how it works"];\n'
         '  node [fontname="Helvetica", fontsize=11, margin="0.15,0.07"];\n  edge [arrowsize=0.7, fontsize=9, fontname="Helvetica"];\n')
    s += '  start [shape=oval, style=filled, fillcolor="#EEEEEE", label="Goal: pick channel + modulation\\nthat maximise delivered data"];\n'
    s += f'  subgraph cluster_1 {{ label="{TITLES[1]}"; color="{c[1][2]}"; style=rounded;\n'
    s += box("w_chan", "Channel model: 3 channels,\ntime-varying interference", 1)
    s += box("w_ctrl", "Controllers: fixed, AMC, switching,\nhybrid, cost-aware, calibrated", 1)
    s += box("w_bench", "Benchmark: 630 runs\n(3 envs x 30 seeds x 7 strategies)", 1)
    s += box("w_stats", "Paired statistics + figures\nPDR, throughput, availability", 1)
    s += box("w_ml", "ML analysis: regression +\nrandom forest on benchmark", 1)
    s += box("w_srad", "Simulated radio + GNU Radio\nlive interference experiment", 1)
    s += "  }\n"
    s += f'  subgraph cluster_2 {{ label="{TITLES[2]}"; color="{c[2][2]}"; style=rounded;\n'
    s += box("w_rx", "GNU Radio packet receiver\nBPSK / QPSK / 16-QAM", 2)
    s += box("w_cal", "Calibration: packet success vs noise\n(2,070 trials) → logistic model", 2)
    s += box("w_snr", "Noise voltage ↔ SNR mapping\n(1,530 measurements)", 2)
    s += box("w_sync", "Synchronisation: timing, CFO,\nSRO, multipath (validated)", 2)
    s += box("w_wave", "Framed waveforms + receivers\n(pilot, sync word, payload)", 2)
    s += box("w_ber", "Synthetic BER vs Es/N0\n→ thresholds 6.8 / 9.9 / 16.7 dB", 2)
    s += box("w_dl", "DL classifier (CNN)\nIQ → BPSK / QPSK / 16-QAM", 2)
    s += "  }\n"
    s += f'  subgraph cluster_3 {{ label="{TITLES[3]}"; color="{c[3][2]}"; style=rounded;\n'
    s += box("w_tx", "ADALM-Pluto TX (pyadi-iio)\n865–868 MHz band, readback-verified", 3)
    s += box("w_air", "Over the air\n(antennas)", 3, shape="ellipse")
    s += box("w_rtl", "RTL-SDR capture\n2.048 MS/s, gain 28 dB", 3)
    s += box("w_tests", "Tone test → BPSK frames →\nBPSK/QPSK/16-QAM frames", 3)
    s += box("w_sweep", "15-run BER sweep\nmeasured BER vs theory", 3)
    s += box("w_cl", "Closed loop on the radios: probe 3 channels\n→ controller → TX on chosen channel (72 rounds)", 3)
    s += "  }\n"
    s += '  done [shape=oval, style=filled, fillcolor="#EEEEEE", label="Results → part reports → master report"];\n'
    edges = [
        ("start", "w_chan", ""), ("start", "w_rx", ""), ("start", "w_tx", ""),
        ("w_rx", "w_cal", ""), ("w_cal", "w_ctrl", "packet-success model"), ("w_snr", "w_ctrl", "SNR → noise"),
        ("w_chan", "w_ctrl", ""), ("w_ctrl", "w_bench", ""), ("w_bench", "w_stats", ""), ("w_bench", "w_ml", ""),
        ("w_ctrl", "w_srad", ""), ("w_sync", "w_wave", ""), ("w_wave", "w_ber", ""), ("w_wave", "w_tx", "TX files"),
        ("w_tx", "w_air", ""), ("w_air", "w_rtl", ""), ("w_rtl", "w_tests", "receivers (Part 2)"),
        ("w_tests", "w_sweep", ""), ("w_ber", "w_sweep", "compare"), ("w_wave", "w_dl", "training data"),
        ("w_rtl", "w_dl", "real test data"), ("w_rx", "w_snr", ""),
        ("w_stats", "done", ""), ("w_ml", "done", ""), ("w_sweep", "done", ""), ("w_dl", "done", ""),
        ("w_srad", "done", ""), ("w_ctrl", "w_cl", "controller (Part 1)"), ("w_rtl", "w_cl", ""),
        ("w_cl", "done", ""),
    ]
    for a, b, lab in edges:
        s += f'  {a} -> {b}' + (f' [label="{lab}"]' if lab else "") + ";\n"
    return s + "}\n"


def render(name, dot_src):
    OUT.mkdir(parents=True, exist_ok=True)
    dot_path = OUT / f"{name}.dot"
    dot_path.write_text(dot_src)
    for fmt, extra in (("svg", []), ("png", ["-Gdpi=170"])):
        subprocess.run(["dot", f"-T{fmt}", *extra, str(dot_path), "-o", str(OUT / f"{name}.{fmt}")], check=True)
    print(f"  {name}: .dot .svg .png")


def main():
    if not shutil.which("dot"):
        sys.exit("Graphviz 'dot' not found (Arch: pacman -S graphviz; Ubuntu: apt install graphviz).")
    render("01_project_workflow", workflow())
    for n in (1, 2, 3):
        render(f"0{n + 1}_code_map_part{n}", code_map(n))
    render("05_code_map_all", code_map_all())
    print(f"Written to {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
