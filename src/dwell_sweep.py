import numpy as np

from src.multi_seed_experiment import (
    ENVIRONMENTS,
    SEEDS,
    run_once,
)

DWELL_VALUES = (0, 5, 10, 20)

SWEEP_STRATEGIES = (
    "channel_switching",
    "hybrid",
    "reliability_constrained",
)


def main():
    all_results = []

    for environment in ENVIRONMENTS:
        for dwell in DWELL_VALUES:
            for seed in SEEDS:
                results = run_once(
                    seed,
                    environment,
                    min_dwell_steps=dwell,
                )

                for strategy in SWEEP_STRATEGIES:
                    all_results.append({
                        "environment": environment,
                        "dwell": dwell,
                        "seed": seed,
                        "strategy": strategy,
                        **results[strategy],
                    })

    print(
        f"{'Environment':10s} {'Dwell':>5s} {'Strategy':25s} "
        f"{'PDR':>7s} {'Throughput':>11s} "
        f"{'Availability':>12s} {'Switches':>9s}"
    )

    for environment in ENVIRONMENTS:
        for dwell in DWELL_VALUES:
            for strategy in SWEEP_STRATEGIES:
                group = [
                    row for row in all_results
                    if row["environment"] == environment
                    and row["dwell"] == dwell
                    and row["strategy"] == strategy
                ]

                pdr = np.mean([
                    row["packet_delivery_ratio"] for row in group
                ])
                throughput = np.mean([
                    row["throughput_bits_per_step"] for row in group
                ])
                availability = np.mean([
                    row["service_availability"] for row in group
                ])
                switches = np.mean([
                    row["switches"] for row in group
                ])

                print(
                    f"{environment:10s} {dwell:5d} {strategy:25s} "
                    f"{pdr:7.3f} {throughput:11.3f} "
                    f"{availability:12.3f} {switches:9.1f}"
                )


if __name__ == "__main__":
    main()
