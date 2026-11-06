import numpy as np

from src.channel_model import ChannelModel
from src.controller import CognitiveController
from src.metrics import packet_success_probability, summarize_run
from src.switching import SwitchingDelay


STEPS = 5000
SWITCH_DELAY_STEPS = 2
SEED = 2026
TARGET_PDR = 0.95

ENVIRONMENTS = {
    "Low": {"volatility": 0.5, "burst_probability": 0.03},
    "Medium": {"volatility": 1.5, "burst_probability": 0.08},
    "High": {"volatility": 3.0, "burst_probability": 0.15},
}


def run_simulation(
    min_dwell_steps=0,
    volatility=1.5,
    burst_probability=0.08,
    switch_delay_steps=SWITCH_DELAY_STEPS,
    target_pdr=TARGET_PDR,
):
    model = ChannelModel(
        seed=SEED,
        volatility=volatility,
        burst_probability=burst_probability,
    )

    snr_trace = np.array([model.step() for _ in range(STEPS)])

    # Common random numbers make strategy comparisons reproducible.
    rng = np.random.default_rng(SEED + 1)
    random_values = rng.random(STEPS)

    strategies = (
        "fixed",
        "adaptive_modulation",
        "channel_switching",
        "hybrid",
        "reliability_constrained",
    )

    results = {}

    for strategy in strategies:
        target = (
            target_pdr
            if strategy == "reliability_constrained"
            else None
        )

        controller = CognitiveController(
            initial_channel=0,
            min_dwell_steps=min_dwell_steps,
            target_pdr=target,
            pdr_window=100,
            switch_delay_steps=switch_delay_steps,
        )

        current_channel = 0

        # The decision step itself is unavailable. The helper tracks
        # only the remaining interruption steps.
        switching_delay = SwitchingDelay(
            max(0, switch_delay_steps - 1)
        )

        successes = []
        delivered_bits = 0.0
        switches = 0
        transmission_steps = 0
        predicted_pdr_sum = 0.0

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

                if strategy == "reliability_constrained":
                    predicted_pdr_sum += decision.predicted_pdr

            snr = channel_snrs[current_channel]
            probability = packet_success_probability(snr, modulation)
            success = random_values[t] < probability

            successes.append(success)
            transmission_steps += 1

            if strategy == "reliability_constrained":
                controller.observe(success)

            if success:
                delivered_bits += rate

        metrics = summarize_run(
            successes=successes,
            delivered_bits=delivered_bits,
            elapsed_steps=STEPS,
            switches=switches,
            attempted_packets=len(successes),
            transmission_steps=transmission_steps,
        )

        metrics["mean_predicted_pdr"] = (
            predicted_pdr_sum / transmission_steps
            if (
                strategy == "reliability_constrained"
                and transmission_steps
            )
            else None
        )

        results[strategy] = metrics

    return results


if __name__ == "__main__":
    for environment, settings in ENVIRONMENTS.items():
        print(f"\n{'=' * 76}")
        print(f"Environment: {environment} | {settings}")
        print("=" * 76)

        results = run_simulation(**settings)

        print(
            f"{'Strategy':25s} {'PDR':>8s} {'Throughput':>12s} "
            f"{'Availability':>13s} {'Switches':>9s}"
        )

        for strategy, metrics in results.items():
            print(
                f"{strategy:25s} "
                f"{metrics['packet_delivery_ratio']:8.3f} "
                f"{metrics['throughput_bits_per_step']:12.3f} "
                f"{metrics['service_availability']:13.3f} "
                f"{metrics['switches']:9d}"
            )
