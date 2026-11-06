import numpy as np

from src.channel_model import ChannelModel
from src.controller import CognitiveController
from src.metrics import (
    packet_success_probability,
    summarize_run,
)

STEPS = 5000
SWITCH_DELAY_STEPS = 2
SEED = 2026


def run_simulation():
    # All strategies experience the same channel conditions.
    model = ChannelModel(seed=SEED)
    snr_trace = np.array([model.step() for _ in range(STEPS)])

    # Shared random draws reduce noise when comparing strategies.
    rng = np.random.default_rng(SEED + 1)
    random_values = rng.random(STEPS)

    strategies = (
        "fixed",
        "adaptive_modulation",
        "channel_switching",
        "hybrid",
    )

    results = {}

    for strategy in strategies:
        controller = CognitiveController(initial_channel=0)
        current_channel = 0
        cooldown = 0

        successes = []
        delivered_bits = 0.0
        switches = 0
        transmission_steps = 0

        for t, channel_snrs in enumerate(snr_trace):
            # No packet can be sent during a channel-switch interruption.
            if cooldown > 0:
                cooldown -= 1
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
                    cooldown = SWITCH_DELAY_STEPS - 1
                    continue

                if strategy == "channel_switching":
                    modulation, rate = "QPSK", 2.0
                else:
                    modulation = decision.modulation
                    rate = decision.data_rate

            # One attempted packet per available transmission time step.
            snr = channel_snrs[current_channel]
            probability = packet_success_probability(snr, modulation)
            success = random_values[t] < probability

            successes.append(success)
            transmission_steps += 1

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


if __name__ == "__main__":
    results = run_simulation()

    print(f"\nSimulation duration: {STEPS} time steps")
    print(f"Switch interruption: {SWITCH_DELAY_STEPS} steps per switch")
    print("\nPERFORMANCE RESULTS")
    print("-" * 105)
    print(
        f"{'Strategy':<24} {'PDR':>9} {'Throughput':>13} "
        f"{'Availability':>13} {'Switches':>10} {'Packets':>10}"
    )
    print("-" * 105)

    for name, metrics in results.items():
        print(
            f"{name:<24}"
            f"{metrics['packet_delivery_ratio']:>8.1%} "
            f"{metrics['throughput_bits_per_step']:>13.3f} "
            f"{metrics['service_availability']:>12.1%} "
            f"{metrics['switches']:>10} "
            f"{metrics['attempted_packets']:>10}"
        )
