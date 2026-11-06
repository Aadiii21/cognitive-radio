import numpy as np


def packet_success_probability(snr_db, modulation):
    """Simplified, uncalibrated packet-success model."""
    thresholds = {
        "BPSK": 4.0,
        "QPSK": 8.0,
        "16-QAM": 16.0,
    }

    margin = snr_db - thresholds[modulation]
    return float(1.0 / (1.0 + np.exp(-0.9 * margin)))


def evaluate_packet(snr_db, modulation, rng):
    probability = packet_success_probability(snr_db, modulation)
    return bool(rng.random() < probability)


def summarize_run(successes, delivered_bits, elapsed_steps, switches,
                  attempted_packets, transmission_steps):
    pdr = sum(successes) / len(successes) if successes else 0.0

    return {
        "packet_delivery_ratio": pdr,
        "throughput_bits_per_step": (
            delivered_bits / elapsed_steps if elapsed_steps else 0.0
        ),
        "service_availability": (
            transmission_steps / elapsed_steps if elapsed_steps else 0.0
        ),
        "switches": switches,
        "attempted_packets": attempted_packets,
    }
