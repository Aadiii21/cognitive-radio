import numpy as np
from scipy.stats import t

from src.multi_seed_experiment import (
    ENVIRONMENTS,
    run_once,
)

SEEDS = range(2026, 2056)
COMPARISONS = [
    ("adaptive_modulation", "fixed"),
    ("channel_switching", "fixed"),
    ("hybrid", "adaptive_modulation"),
    ("reliability_constrained", "fixed"),
    ("reliability_constrained", "adaptive_modulation"),
    ("cost_aware_hybrid", "hybrid"),
    ("cost_aware_hybrid", "channel_switching"),
    ("cost_aware_hybrid", "fixed"),
    ("cost_aware_hybrid", "adaptive_modulation"),
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
    mean = differences.mean()
    sd = differences.std(ddof=1)
    margin = t.ppf(0.975, df=n - 1) * sd / np.sqrt(n)

    return mean, sd, mean - margin, mean + margin


def main():
    print(f"Paired-seed analysis: {len(SEEDS)} seeds per environment")
    print("Positive differences favor the first strategy.")
    print("Intervals are 95% paired t-confidence intervals.")
    print()

    for environment in ENVIRONMENTS:
        outcomes = {}

        for seed in SEEDS:
            results = run_once(seed, environment)

            for strategy, metrics in results.items():
                outcomes.setdefault(strategy, []).append(metrics)

        print(f"=== {environment} interference ===")

        for first, second in COMPARISONS:
            for metric_name, key in METRICS.items():
                differences = [
                    a[key] - b[key]
                    for a, b in zip(
                        outcomes[first],
                        outcomes[second],
                    )
                ]

                mean, sd, lower, upper = paired_summary(differences)

                print(
                    f"{first} vs {second} | {metric_name:12s} "
                    f"delta={mean:+.4f} "
                    f"SD={sd:.4f} "
                    f"95% CI=[{lower:+.4f}, {upper:+.4f}]"
                )

        print()


if __name__ == "__main__":
    main()
