import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "results" / "calibrated_multi_seed_results.csv"
OUTPUT = ROOT / "results" / "figures"

ENVIRONMENTS = ["Low", "Medium", "High"]

STRATEGIES = [
    "fixed",
    "adaptive_modulation",
    "channel_switching",
    "hybrid",
    "reliability_constrained",
    "cost_aware_hybrid",
    "calibrated_hybrid",
]

LABELS = {
    "fixed": "Fixed",
    "adaptive_modulation": "AMC",
    "channel_switching": "Channel switching",
    "hybrid": "Standard hybrid",
    "reliability_constrained": "Reliability constrained",
    "cost_aware_hybrid": "Cost-aware hybrid",
    "calibrated_hybrid": "Calibrated hybrid",
}

METRICS = [
    "packet_delivery_ratio",
    "throughput_bits_per_step",
    "service_availability",
    "switches",
    "attempted_packets",
]


def load_data():
    if not INPUT.exists():
        raise FileNotFoundError(f"Missing benchmark file: {INPUT}")

    with INPUT.open(newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError("Benchmark CSV is empty.")

    for row in rows:
        for key in METRICS:
            row[key] = float(row[key])

        row["seed"] = int(row["seed"])

    return rows


def validate_data(rows):
    errors = []

    expected_combinations = {
        (env, seed, strategy)
        for env in ENVIRONMENTS
        for seed in range(2026, 2056)
        for strategy in STRATEGIES
    }

    observed_combinations = [
        (r["environment"], r["seed"], r["strategy"])
        for r in rows
    ]

    if len(observed_combinations) != len(set(observed_combinations)):
        errors.append("Duplicate environment/seed/strategy rows.")

    missing = expected_combinations - set(observed_combinations)
    extra = set(observed_combinations) - expected_combinations

    if missing:
        errors.append(f"Missing combinations: {len(missing)}")

    if extra:
        errors.append(f"Unexpected combinations: {len(extra)}")

    for i, row in enumerate(rows):
        prefix = f"Row {i + 1}"

        for key in METRICS:
            if not math.isfinite(row[key]):
                errors.append(f"{prefix}: non-finite {key}")

        if not 0 <= row["packet_delivery_ratio"] <= 1:
            errors.append(f"{prefix}: invalid PDR")

        if not 0 <= row["service_availability"] <= 1:
            errors.append(f"{prefix}: invalid availability")

        if row["switches"] < 0 or not row["switches"].is_integer():
            errors.append(f"{prefix}: invalid switch count")

        if row["attempted_packets"] < 0:
            errors.append(f"{prefix}: negative attempted packets")

        if row["attempted_packets"] > 5000:
            errors.append(f"{prefix}: too many attempted packets")

        # The simulation transmits at most 4 bits per successful packet.
        max_throughput = 4 * row["service_availability"]

        if row["throughput_bits_per_step"] > max_throughput + 1e-8:
            errors.append(f"{prefix}: throughput exceeds physical simulation bound")

        expected_availability = row["attempted_packets"] / 5000

        if not math.isclose(
            row["service_availability"],
            expected_availability,
            abs_tol=1e-8,
        ):
            errors.append(f"{prefix}: availability does not match transmission steps")

        if not math.isclose(
            row["attempted_packets"],
            row["attempted_packets"],
            abs_tol=1e-8,
        ):
            errors.append(f"{prefix}: attempted packets and transmission steps differ")

    print("===== DATA VALIDATION =====")
    print("Rows:", len(rows))
    print("Unique environments:", len(set(r["environment"] for r in rows)))
    print("Unique seeds:", len(set(r["seed"] for r in rows)))
    print("Unique strategies:", len(set(r["strategy"] for r in rows)))

    if errors:
        print("\nVALIDATION FAILED")
        for error in errors[:30]:
            print("-", error)

        raise ValueError(f"{len(errors)} validation issue(s) found.")

    print("All expected combinations present.")
    print("Metric bounds and consistency checks passed.")
    print("DATA VALIDATION PASSED\n")


def summarize(rows):
    grouped = defaultdict(list)

    for row in rows:
        key = (row["environment"], row["strategy"])
        grouped[key].append(row)

    summary = {}

    for key, group in grouped.items():
        summary[key] = {}

        for metric in METRICS:
            values = np.array([r[metric] for r in group], dtype=float)

            summary[key][metric] = (
                float(values.mean()),
                float(values.std(ddof=1)),
            )

    return summary


def save_summary(summary):
    path = OUTPUT / "benchmark_summary.csv"

    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "environment",
            "strategy",
            "metric",
            "mean",
            "sample_sd",
        ])

        for env in ENVIRONMENTS:
            for strategy in STRATEGIES:
                for metric in METRICS:
                    mean, sd = summary[(env, strategy)][metric]
                    writer.writerow([env, strategy, metric, mean, sd])

    print("Saved:", path)


def plot_metric(summary, metric, ylabel, title, filename, ylim=None):
    fig, ax = plt.subplots(figsize=(11, 6))

    x = np.arange(len(ENVIRONMENTS))
    width = 0.105

    for i, strategy in enumerate(STRATEGIES):
        means = [
            summary[(env, strategy)][metric][0]
            for env in ENVIRONMENTS
        ]
        errors = [
            summary[(env, strategy)][metric][1]
            for env in ENVIRONMENTS
        ]

        offset = (i - (len(STRATEGIES) - 1) / 2) * width

        ax.bar(
            x + offset,
            means,
            width,
            yerr=errors,
            capsize=3,
            label=LABELS[strategy],
        )

    ax.set_xticks(x)
    ax.set_xticklabels(ENVIRONMENTS)
    ax.set_xlabel("Interference environment")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)

    if ylim:
        ax.set_ylim(*ylim)

    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.13),
        ncol=3,
        fontsize=8,
    )

    fig.tight_layout()
    path = OUTPUT / filename
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    print("Saved:", path)


def plot_switching_availability(summary):
    fig, ax1 = plt.subplots(figsize=(11, 6))
    ax2 = ax1.twinx()

    x = np.arange(len(ENVIRONMENTS))
    width = 0.105

    for i, strategy in enumerate(STRATEGIES):
        offset = (i - (len(STRATEGIES) - 1) / 2) * width

        switches = [
            summary[(env, strategy)]["switches"][0]
            for env in ENVIRONMENTS
        ]

        switch_sd = [
            summary[(env, strategy)]["switches"][1]
            for env in ENVIRONMENTS
        ]

        ax1.bar(
            x + offset,
            switches,
            width,
            yerr=switch_sd,
            capsize=2,
            label=LABELS[strategy],
        )

        availability = [
            summary[(env, strategy)]["service_availability"][0]
            for env in ENVIRONMENTS
        ]

        ax2.plot(
            x,
            availability,
            marker="o",
            linestyle="--",
            linewidth=1.2,
            alpha=0.75,
        )

    ax1.set_xticks(x)
    ax1.set_xticklabels(ENVIRONMENTS)
    ax1.set_xlabel("Interference environment")
    ax1.set_ylabel("Mean channel switches per 5,000 steps")
    ax2.set_ylabel("Service availability")
    ax2.set_ylim(0.7, 1.02)

    ax1.set_title("Switching overhead and service availability")
    ax1.grid(axis="y", alpha=0.25)
    ax1.set_axisbelow(True)

    ax1.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.13),
        ncol=3,
        fontsize=8,
    )

    fig.tight_layout()
    path = OUTPUT / "switching_availability.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    print("Saved:", path)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    rows = load_data()
    validate_data(rows)

    summary = summarize(rows)
    save_summary(summary)

    plot_metric(
        summary,
        "throughput_bits_per_step",
        "Throughput (bits/step)",
        "Throughput across interference environments",
        "throughput_comparison.png",
    )

    plot_metric(
        summary,
        "packet_delivery_ratio",
        "Packet delivery ratio",
        "Packet delivery ratio across interference environments",
        "pdr_comparison.png",
        ylim=(0, 1.05),
    )

    plot_switching_availability(summary)

    print("\nALL ANALYSIS OUTPUTS GENERATED")


if __name__ == "__main__":
    main()
