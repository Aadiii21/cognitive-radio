import csv
from pathlib import Path

import numpy as np

from src.channel_model import ChannelModel
from src.controller import CognitiveController
from src.controller_cost_aware import CognitiveController as CostAwareController
from src.calibrated_controller import (
    CalibratedCognitiveController,
    calibrated_packet_success,
)
from src.noise_calibration import noise_for_snr
from src.metrics import summarize_run
from src.switching import SwitchingDelay


ROOT = Path(__file__).resolve().parents[1]

STEPS = 5000
SWITCH_DELAY_STEPS = 2
TARGET_PDR = 0.95

SEEDS = list(range(2026, 2056))

ENVIRONMENTS = {
    "Low": {"volatility": 0.5, "burst_probability": 0.03},
    "Medium": {"volatility": 1.5, "burst_probability": 0.08},
    "High": {"volatility": 3.0, "burst_probability": 0.15},
}

STRATEGIES = (
    "fixed",
    "adaptive_modulation",
    "channel_switching",
    "hybrid",
    "reliability_constrained",
    "cost_aware_hybrid",
    "calibrated_hybrid",
)


def calibrated_probability(snr_db, modulation):
    """Evaluate all strategies using the same empirical packet model."""
    noise = noise_for_snr(
        float(snr_db),
        modulation,
        clip=True,
    )
    return calibrated_packet_success(noise, modulation)


class FixedQPSKChannelController(CognitiveController):
    """Select channels using calibrated QPSK utility only."""

    def channel_utility(self, snr):
        modulation = "QPSK"
        rate = 2.0
        probability = calibrated_probability(snr, modulation)

        return rate * probability, modulation, rate, probability


def run_once(seed, environment, min_dwell_steps=0):
    settings = ENVIRONMENTS[environment]

    model = ChannelModel(
        seed=seed,
        volatility=settings["volatility"],
        burst_probability=settings["burst_probability"],
    )

    snr_trace = np.array([
        model.step() for _ in range(STEPS)
    ])

    # Common random numbers: identical channel and packet randomness
    # across every strategy for this seed and environment.
    packet_rng = np.random.default_rng(seed + 10000)
    random_values = packet_rng.random(STEPS)

    results = {}

    for strategy in STRATEGIES:
        target = (
            TARGET_PDR
            if strategy == "reliability_constrained"
            else None
        )

        if strategy == "cost_aware_hybrid":
            controller = CostAwareController(
                initial_channel=0,
                switch_delay_steps=SWITCH_DELAY_STEPS,
                switch_penalty=0.15,
                min_utility_gain=0.10,
            )

        elif strategy == "calibrated_hybrid":
            controller = CalibratedCognitiveController(
                initial_channel=0,
                switch_delay_steps=SWITCH_DELAY_STEPS,
                switch_penalty=0.15,
                min_utility_gain=0.10,
            )

        elif strategy == "channel_switching":
            controller = FixedQPSKChannelController(
                initial_channel=0,
                min_dwell_steps=min_dwell_steps,
                switch_delay_steps=SWITCH_DELAY_STEPS,
            )

        elif strategy != "fixed":
            controller = CognitiveController(
                initial_channel=0,
                min_dwell_steps=min_dwell_steps,
                target_pdr=target,
                pdr_window=100,
                switch_delay_steps=SWITCH_DELAY_STEPS,
            )
        else:
            controller = None

        current_channel = 0
        switching_delay = SwitchingDelay(
            max(0, SWITCH_DELAY_STEPS - 1)
        )

        successes = []
        delivered_bits = 0.0
        switches = 0
        transmission_steps = 0

        for t, channel_snrs in enumerate(snr_trace):

            if switching_delay.consume_step():
                continue

            if strategy == "fixed":
                current_channel = 0
                modulation, rate = "QPSK", 2.0

            elif strategy == "adaptive_modulation":
                current_channel = 0
                modulation, _, rate = controller.choose_modulation(
                    channel_snrs[current_channel]
                )

            else:
                decision = controller.decide(channel_snrs)
                current_channel = decision.channel

                if decision.action == "switch_channel":
                    switches += 1
                    switching_delay.start()
                    continue

                if strategy == "channel_switching":
                    modulation, rate = "QPSK", 2.0
                else:
                    modulation = decision.modulation
                    rate = decision.data_rate

            snr = float(channel_snrs[current_channel])

            # Identical empirical evaluation model for every strategy.
            probability = calibrated_probability(snr, modulation)
            success = random_values[t] < probability

            successes.append(success)
            transmission_steps += 1

            if strategy == "reliability_constrained":
                controller.observe(success)

            if success:
                delivered_bits += rate

        results[strategy] = summarize_run(
            successes=successes,
            delivered_bits=delivered_bits,
            elapsed_steps=STEPS,
            switches=switches,
            attempted_packets=len(successes),
            transmission_steps=transmission_steps,
        )

    return results


def mean_sd(values):
    values = np.asarray(values, dtype=float)

    if len(values) < 2:
        return float(values.mean()), 0.0

    return (
        float(values.mean()),
        float(values.std(ddof=1)),
    )


def save_results(rows):
    output = ROOT / "results" / "calibrated_multi_seed_results.csv"
    output.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        raise ValueError("No experiment results to save.")

    with output.open("w", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0].keys()),
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved results: {output}")


def main():
    rows = []

    for environment in ENVIRONMENTS:
        for seed in SEEDS:
            results = run_once(seed, environment)

            for strategy, metrics in results.items():
                rows.append({
                    "environment": environment,
                    "seed": seed,
                    "strategy": strategy,
                    **metrics,
                })

    print(f"Seeds per environment: {len(SEEDS)}")
    print(f"Steps per run: {STEPS}")
    print(f"Total strategy runs: {len(rows)}")
    print("Packet evaluation: calibrated GNU Radio models")
    print()

    header = (
        f"{'Environment':10s} {'Strategy':25s} "
        f"{'PDR mean±SD':>17s} "
        f"{'Throughput mean±SD':>23s} "
        f"{'Availability mean±SD':>24s} "
        f"{'Switches mean±SD':>19s}"
    )
    print(header)

    for environment in ENVIRONMENTS:
        for strategy in STRATEGIES:
            group = [
                row for row in rows
                if row["environment"] == environment
                and row["strategy"] == strategy
            ]

            pdr_mean, pdr_sd = mean_sd([
                row["packet_delivery_ratio"] for row in group
            ])
            throughput_mean, throughput_sd = mean_sd([
                row["throughput_bits_per_step"] for row in group
            ])
            availability_mean, availability_sd = mean_sd([
                row["service_availability"] for row in group
            ])
            switches_mean, switches_sd = mean_sd([
                row["switches"] for row in group
            ])

            print(
                f"{environment:10s} {strategy:25s} "
                f"{pdr_mean:.3f}±{pdr_sd:.3f} "
                f"{throughput_mean:8.3f}±{throughput_sd:.3f} "
                f"{availability_mean:9.3f}±{availability_sd:.3f} "
                f"{switches_mean:7.1f}±{switches_sd:.1f}"
            )

    save_results(rows)


if __name__ == "__main__":
    main()
