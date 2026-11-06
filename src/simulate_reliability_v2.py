
import numpy as np

from src.channel_model import ChannelModel
from src.controller import CognitiveController
from src.metrics import packet_success_probability, summarize_run

STEPS = 5000
SWITCH_DELAY_STEPS = 2
SEED = 2026
TARGET_PDR = 0.95


def run_simulation(min_dwell_steps=0):
    model = ChannelModel(seed=SEED)
    snr_trace = np.array([model.step() for _ in range(STEPS)])

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
        target = TARGET_PDR if strategy == "reliability_constrained" else None

        controller = CognitiveController(
            initial_channel=0,
            min_dwell_steps=min_dwell_steps,
            target_pdr=target,
            pdr_window=100,
            switch_delay_steps=SWITCH_DELAY_STEPS,
        )

        current_channel = 0
        cooldown = 0
        successes = []
        delivered_bits = 0.0
        switches = 0
        transmission_steps = 0
        predicted_pdr_sum = 0.0

        for t, channel_snrs in enumerate(snr_trace):
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
            predicted_pdr_sum / len(successes)
            if strategy == "reliability_constrained" and successes
            else None
        )

        results[strategy] = metrics

    return results


if __name__ == "__main__":
    for dwell in (0, 5, 10, 20):
        results = run_simulation(min_dwell_steps=dwell)

        print(f"\nMINIMUM DWELL TIME: {dwell} steps")
        print("-" * 108)
        print(
            f"{'Strategy':<25} {'PDR':>8} {'Throughput':>12} "
            f"{'Avail.':>9} {'Switches':>9} {'Packets':>9} {'Pred. PDR':>10}"
        )

        for name, metrics in results.items():
            predicted = metrics["mean_predicted_pdr"]
            predicted_text = f"{predicted:.1%}" if predicted is not None else "-"

            print(
                f"{name:<25}"
                f"{metrics['packet_delivery_ratio']:>7.1%} "
                f"{metrics['throughput_bits_per_step']:>12.3f} "
                f"{metrics['service_availability']:>8.1%} "
                f"{metrics['switches']:>9} "
                f"{metrics['attempted_packets']:>9} "
                f"{predicted_text:>10}"
            )
