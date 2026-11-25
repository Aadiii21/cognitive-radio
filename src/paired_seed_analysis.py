import csv
from pathlib import Path

import numpy as np
from scipy.stats import t

from src.multi_seed_experiment import ENVIRONMENTS


ROOT = Path(__file__).resolve().parents[1]
RESULTS_FILE = ROOT / "results" / "calibrated_multi_seed_results.csv"

COMPARISONS = [
    ("calibrated_hybrid", "hybrid"),
    ("calibrated_hybrid", "channel_switching"),
    ("calibrated_hybrid", "adaptive_modulation"),
    ("calibrated_hybrid", "fixed"),
    ("hybrid", "adaptive_modulation"),
    ("cost_aware_hybrid", "hybrid"),
]

METRICS = {
    "PDR": "packet_delivery_ratio",
    "Throughput": "throughput_bits_per_step",
    "Availability": "service_availability",
    "Switches": "switches",
}


def paired_summary(differences):
    differences = np.asarray(differences, dtype=float)
    n = len(differences)

    if n < 2:
        raise ValueError("At least two paired observations are required.")

    mean = differences.mean()
    sd = differences.std(ddof=1)
    margin = t.ppf(0.975, df=n - 1) * sd / np.sqrt(n)

    return mean, sd, mean - margin, mean + margin


def main():
    with RESULTS_FILE.open(newline="") as file:
        rows = list(csv.DictReader(file))

    print("Paired-seed analysis")
    print(f"Results: {RESULTS_FILE}")
    print("Positive differences favor the first strategy.")
    print("Intervals are 95% paired t-confidence intervals.")
    print()

    for environment in ENVIRONMENTS:
        env_rows = [
            row for row in rows
            if row["environment"] == environment
        ]

        outcomes = {}

        for row in env_rows:
            outcomes.setdefault(row["strategy"], {})[
                int(row["seed"])
            ] = row

        print(f"=== {environment} interference ===")

        for first, second in COMPARISONS:
            if first not in outcomes or second not in outcomes:
                continue

            common_seeds = sorted(
                set(outcomes[first]) & set(outcomes[second])
            )

            for metric_name, key in METRICS.items():
                differences = [
                    float(outcomes[first][seed][key])
                    - float(outcomes[second][seed][key])
                    for seed in common_seeds
                ]

                mean, sd, lower, upper = paired_summary(differences)

                print(
                    f"{first} vs {second} | {metric_name:12s} "
                    f"n={len(common_seeds):2d} "
                    f"delta={mean:+.4f} "
                    f"SD={sd:.4f} "
                    f"95% CI=[{lower:+.4f}, {upper:+.4f}]"
                )

        print()


if __name__ == "__main__":
    main()
