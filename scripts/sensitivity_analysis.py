#!/usr/bin/env python3
"""Sensitivity and robustness checks for the controller benchmark (simulation only).

    python scripts/sensitivity_analysis.py --check       # reproduce the 630-run CSV at the original settings
    python scripts/sensitivity_analysis.py               # both studies below (~15-30 min)

Uses the unchanged benchmark components (src/multi_seed_experiment.py: channel
traces, common random numbers, controllers, calibrated packet model).

1. Switching-penalty sweep: the calibrated and cost-aware hybrids are re-run with
   switch_penalty in PENALTIES (the benchmark uses 0.15). Shows the throughput /
   availability / switching trade-off and whether the result depends on 0.15.
2. Implementation-loss robustness: the TRUE packet outcome is drawn at
   (SNR - loss) while every controller still believes its model at SNR. The OTA
   hardware showed about 1 dB loss against theory; 2 dB is a stress test.

Outputs in results/sensitivity/:
  penalty_sweep.csv, penalty_sweep.png
  implementation_loss.csv, implementation_loss.png
  summary.json
"""
import argparse
import csv
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import multi_seed_experiment as mse  # noqa: E402
from src.calibrated_controller import CalibratedCognitiveController  # noqa: E402
from src.channel_model import ChannelModel  # noqa: E402
from src.controller import CognitiveController  # noqa: E402
from src.controller_cost_aware import CognitiveController as CostAwareController  # noqa: E402
from src.metrics import summarize_run  # noqa: E402
from src.switching import SwitchingDelay  # noqa: E402

OUT = ROOT / "results" / "sensitivity"
PENALTIES = [0.0, 0.05, 0.10, 0.15, 0.25, 0.40, 0.60]
LOSSES_DB = [0.0, 1.0, 2.0]
ENVS = ["Low", "Medium", "High"]


def traces(seed, environment):
    s = mse.ENVIRONMENTS[environment]
    model = ChannelModel(seed=seed, volatility=s["volatility"], burst_probability=s["burst_probability"])
    snr = np.array([model.step() for _ in range(mse.STEPS)])
    rnd = np.random.default_rng(seed + 10000).random(mse.STEPS)
    return snr, rnd


def make_controller(strategy, penalty=0.15, min_gain=0.10):
    d = mse.SWITCH_DELAY_STEPS
    if strategy == "cost_aware_hybrid":
        return CostAwareController(initial_channel=0, switch_delay_steps=d, switch_penalty=penalty,
                                   min_utility_gain=min_gain)
    if strategy == "calibrated_hybrid":
        return CalibratedCognitiveController(initial_channel=0, switch_delay_steps=d, switch_penalty=penalty,
                                             min_utility_gain=min_gain)
    if strategy == "channel_switching":
        return mse.FixedQPSKChannelController(initial_channel=0, min_dwell_steps=0, switch_delay_steps=d)
    if strategy == "fixed":
        return None
    target = mse.TARGET_PDR if strategy == "reliability_constrained" else None
    return CognitiveController(initial_channel=0, min_dwell_steps=0, target_pdr=target, pdr_window=100,
                               switch_delay_steps=d)


NOISE_MAX = 0.45   # upper edge of the logistic calibration range
SNR_FLOOR = -5.0   # channel model's SNR floor; the controller's view is kept at or above it


def outcome_probability(snr_db, modulation, loss_db):
    """True packet success at (SNR - loss). Beyond the calibrated noise range (0.45 V) success is
    effectively zero for every modulation, so the noise is clipped to the range edge."""
    if loss_db == 0.0:
        return mse.calibrated_probability(snr_db, modulation)
    noise = min(mse.noise_for_snr(float(snr_db - loss_db), modulation, clip=True), NOISE_MAX)
    return mse.calibrated_packet_success(noise, modulation)


def run_strategy(snr_trace, random_values, strategy, penalty=0.15, loss_db=0.0, margin_db=0.0):
    """Same loop as multi_seed_experiment.run_once, for one strategy.

    loss_db: true packet success is taken at (SNR - loss).
    margin_db: the controller sees (SNR - margin), i.e. a safety margin in its decisions.
    """
    controller = make_controller(strategy, penalty)
    current_channel = 0
    switching_delay = SwitchingDelay(max(0, mse.SWITCH_DELAY_STEPS - 1))
    successes, delivered, switches, tx_steps = [], 0.0, 0, 0
    for t, channel_snrs in enumerate(snr_trace):
        if switching_delay.consume_step():
            continue
        if strategy == "fixed":
            current_channel, modulation, rate = 0, "QPSK", 2.0
        elif strategy == "adaptive_modulation":
            current_channel = 0
            modulation, _, rate = controller.choose_modulation(max(channel_snrs[current_channel] - margin_db, SNR_FLOOR))
        else:
            decision = controller.decide(np.maximum(channel_snrs - margin_db, SNR_FLOOR))
            current_channel = decision.channel
            if decision.action == "switch_channel":
                switches += 1
                switching_delay.start()
                continue
            if strategy == "channel_switching":
                modulation, rate = "QPSK", 2.0
            else:
                modulation, rate = decision.modulation, decision.data_rate
        snr = float(channel_snrs[current_channel])
        success = random_values[t] < outcome_probability(snr, modulation, loss_db)
        successes.append(success)
        tx_steps += 1
        if strategy == "reliability_constrained":
            controller.observe(success)
        if success:
            delivered += rate
    return summarize_run(successes=successes, delivered_bits=delivered, elapsed_steps=mse.STEPS,
                         switches=switches, attempted_packets=len(successes), transmission_steps=tx_steps)


def _job(args):
    seed, env, jobs = args
    snr, rnd = traces(seed, env)
    out = []
    for job in jobs:
        strategy, penalty, loss = job[:3]
        margin = job[3] if len(job) > 3 else 0.0
        r = run_strategy(snr, rnd, strategy, penalty, loss, margin)
        out.append({"environment": env, "seed": seed, "strategy": strategy, "switch_penalty": penalty,
                    "loss_db": loss, "margin_db": margin, **r})
    return out


def run_grid(jobs, seeds, workers):
    tasks = [(s, e, jobs) for e in ENVS for s in seeds]
    with Pool(workers) as p:
        return [row for chunk in p.map(_job, tasks) for row in chunk]


def check(workers):
    """Reproduce results/calibrated_multi_seed_results.csv exactly (all 7 strategies)."""
    import pandas as pd
    ref = pd.read_csv(ROOT / "results" / "calibrated_multi_seed_results.csv")
    rows = run_grid([(s, 0.15, 0.0) for s in mse.STRATEGIES], mse.SEEDS, workers)
    new = pd.DataFrame(rows)
    cols = ["packet_delivery_ratio", "throughput_bits_per_step", "service_availability", "switches"]
    m = ref.merge(new, on=["environment", "seed", "strategy"], suffixes=("_ref", "_new"))
    worst = max(float(np.max(np.abs(m[c + "_ref"] - m[c + "_new"]))) for c in cols)
    print(f"check: {len(m)} of {len(ref)} runs matched; largest difference {worst:.2e}")
    return len(m) == len(ref) and worst < 1e-9


def ci95(x):
    x = np.asarray(x, float)
    from scipy.stats import t
    h = t.ppf(0.975, len(x) - 1) * x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0.0
    return float(x.mean()), float(h)


def summarize(rows, keys):
    groups = {}
    for r in rows:
        groups.setdefault(tuple(r[k] for k in keys), []).append(r)
    out = []
    for k, g in sorted(groups.items(), key=lambda kv: (ENVS.index(kv[0][0]),) + kv[0][1:]):
        rec = dict(zip(keys, k))
        for c in ("throughput_bits_per_step", "packet_delivery_ratio", "service_availability", "switches"):
            m, h = ci95([r[c] for r in g])
            rec[c] = round(m, 4)
            rec[c + "_ci95"] = round(h, 4)
        rec["seeds"] = len(g)
        out.append(rec)
    return out


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def plot_penalty(summary, path):
    """Throughput, availability and PDR vs switching penalty (rows) per environment (columns)."""
    plt = _plt()
    metrics = [("throughput_bits_per_step", "Throughput (bits/step)"),
               ("service_availability", "Availability"), ("packet_delivery_ratio", "PDR")]
    colors = {"calibrated_hybrid": "#2F5D8A", "cost_aware_hybrid": "#B8621B"}
    fig, axes = plt.subplots(3, 3, figsize=(10, 7.2), sharex=True)
    for j, env in enumerate(ENVS):
        for i, (col, lab) in enumerate(metrics):
            ax = axes[i, j]
            for strat, c in colors.items():
                pts = sorted([r for r in summary if r["environment"] == env and r["strategy"] == strat],
                             key=lambda r: r["switch_penalty"])
                x = [r["switch_penalty"] for r in pts]
                y = [r[col] for r in pts]
                e = [r[col + "_ci95"] for r in pts]
                ax.errorbar(x, y, yerr=e, fmt="o-", ms=3.5, lw=1.2, capsize=2, color=c,
                            label=strat.replace("_", " "))
            ax.axvline(0.15, color="#999", ls=":", lw=0.9)
            ax.grid(alpha=0.3)
            if j == 0:
                ax.set_ylabel(lab, fontsize=9)
            if i == 0:
                ax.set_title(f"{env} interference", fontsize=10)
            if i == 2:
                ax.set_xlabel("Switching penalty")
            ax.tick_params(labelsize=8)
    axes[0, 0].legend(fontsize=8, loc="center right")
    fig.suptitle("Switching-penalty sweep (dotted line: 0.15 used in the benchmark; bars: 95 % CI over 30 seeds)",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def plot_loss(summary, path):
    plt = _plt()
    strategies = list(mse.STRATEGIES)
    colors = {0.0: "#9DB9D5", 1.0: "#2F5D8A", 2.0: "#1B3550"}
    w = 0.27
    fig, axes = plt.subplots(2, 3, figsize=(11, 6.2), sharey="row")
    for i, (col, lab) in enumerate([("throughput_bits_per_step", "Throughput (bits/step)"),
                                    ("packet_delivery_ratio", "PDR")]):
        for j, env in enumerate(ENVS):
            ax = axes[i, j]
            for k, loss in enumerate(LOSSES_DB):
                ys = [next(r[col] for r in summary if r["environment"] == env and r["strategy"] == s
                           and r["loss_db"] == loss) for s in strategies]
                ax.bar(np.arange(len(strategies)) + (k - 1) * w, ys, w, color=colors[loss],
                       label=f"{loss:g} dB loss")
            ax.set_xticks(range(len(strategies)), [s.replace("_", "\n") for s in strategies], fontsize=6)
            ax.grid(alpha=0.3, axis="y")
            if i == 0:
                ax.set_title(f"{env} interference", fontsize=10)
            if j == 0:
                ax.set_ylabel(lab)
            if col == "packet_delivery_ratio":
                ax.set_ylim(0.75, 1.01)
    h, l = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=3, fontsize=9, bbox_to_anchor=(0.5, 0.95), frameon=False)
    fig.suptitle("Robustness: true packet success taken at (SNR - loss); controllers unaware", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, dpi=200)
    plt.close(fig)


def replot():
    import pandas as pd
    plot_penalty(pd.read_csv(OUT / "penalty_sweep.csv").to_dict("records"), OUT / "penalty_sweep.png")
    plot_loss(pd.read_csv(OUT / "implementation_loss.csv").to_dict("records"), OUT / "implementation_loss.png")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="only reproduce the benchmark CSV")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--loss-only", action="store_true", help="skip the penalty sweep")
    ap.add_argument("--margin-only", action="store_true", help="only the safety-margin study")
    ap.add_argument("--replot", action="store_true", help="redraw the figures from the CSVs")
    a = ap.parse_args(argv)
    if a.check:
        sys.exit(0 if check(a.workers) else 1)
    OUT.mkdir(parents=True, exist_ok=True)

    if a.replot:
        replot()
        return
    if a.margin_only:
        margin_study(a.workers)
        return
    if a.loss_only:
        import pandas as pd
        pen = pd.read_csv(OUT / "penalty_sweep.csv").to_dict("records")
    else:
        pen = None
    print("Penalty sweep ..." if pen is None else "Penalty sweep: reusing penalty_sweep.csv")
    jobs = [(s, p, 0.0) for s in ("calibrated_hybrid", "cost_aware_hybrid") for p in PENALTIES]
    if pen is None:
        rows = run_grid(jobs, mse.SEEDS, a.workers)
        pen = summarize(rows, ["environment", "strategy", "switch_penalty"])
        write_csv(OUT / "penalty_sweep.csv", pen)
    plot_penalty(pen, OUT / "penalty_sweep.png")

    print("Implementation-loss robustness ...")
    jobs = [(s, 0.15, l) for s in mse.STRATEGIES for l in LOSSES_DB]
    rows2 = run_grid(jobs, mse.SEEDS, a.workers)
    loss = summarize(rows2, ["environment", "strategy", "loss_db"])
    write_csv(OUT / "implementation_loss.csv", loss)
    plot_loss(loss, OUT / "implementation_loss.png")

    # paired: calibrated vs best other strategy, per environment and loss
    paired = {}
    for env in ENVS:
        for l in LOSSES_DB:
            cal = {r["seed"]: r["throughput_bits_per_step"] for r in rows2
                   if r["environment"] == env and r["loss_db"] == l and r["strategy"] == "calibrated_hybrid"}
            others = [s for s in mse.STRATEGIES if s != "calibrated_hybrid"]
            best = max(others, key=lambda s: np.mean([r["throughput_bits_per_step"] for r in rows2
                                                      if r["environment"] == env and r["loss_db"] == l
                                                      and r["strategy"] == s]))
            oth = {r["seed"]: r["throughput_bits_per_step"] for r in rows2
                   if r["environment"] == env and r["loss_db"] == l and r["strategy"] == best}
            d = [cal[s] - oth[s] for s in cal]
            m, h = ci95(d)
            paired[f"{env}_{l:g}dB"] = {"best_other": best, "delta": round(m, 4), "ci95": round(h, 4)}
    (OUT / "summary.json").write_text(json.dumps({"penalties": PENALTIES, "losses_db": LOSSES_DB,
                                                  "calibrated_vs_best_other": paired}, indent=2))
    print(json.dumps(paired, indent=1))
    margin_study(a.workers)


def margin_study(workers):
    """3. Calibrated hybrid with a safety margin equal to the loss (controller sees SNR - margin)."""
    print("Safety margin ...")
    jobs = [("calibrated_hybrid", 0.15, l, m) for l in LOSSES_DB for m in (0.0, 1.0, 2.0) if m <= l]
    rows = run_grid(jobs, mse.SEEDS, workers)
    summ = summarize(rows, ["environment", "loss_db", "margin_db"])
    write_csv(OUT / "safety_margin.csv", summ)
    for r in summ:
        print(f"  {r['environment']:6s} loss {r['loss_db']:g} margin {r['margin_db']:g}: "
              f"thr {r['throughput_bits_per_step']:.3f}  PDR {r['packet_delivery_ratio']:.3f}  "
              f"avail {r['service_availability']:.3f}")


if __name__ == "__main__":
    main()
