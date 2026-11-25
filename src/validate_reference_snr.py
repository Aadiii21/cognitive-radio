#!/usr/bin/env python3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.radio.waveform_generator import generate_waveform 


import csv
from datetime import datetime
from pathlib import Path

import numpy as np

from src.radio.waveform_generator import generate_waveform


MODULATIONS = ("BPSK", "QPSK", "16QAM")
TARGET_SNRS = (5.0, 10.0, 15.0)

REPETITIONS = 20
SYMBOLS = 65536
SPS = 4
SAMPLE_RATE = 2_400_000
ROLLOFF = 0.35


def add_awgn(clean, target_snr_db, rng):
    signal_power = float(np.mean(np.abs(clean) ** 2))
    noise_power = signal_power / (10 ** (target_snr_db / 10))

    noise = np.sqrt(noise_power / 2) * (
        rng.standard_normal(len(clean))
        + 1j * rng.standard_normal(len(clean))
    )

    return clean + noise.astype(np.complex64)


def estimate_reference_snr(clean, received):
    clean = np.asarray(clean, dtype=np.complex128)
    received = np.asarray(received, dtype=np.complex128)

    if clean.shape != received.shape or clean.size == 0:
        raise ValueError("Reference and received IQ must have equal nonzero size")

    if not np.isfinite(clean).all() or not np.isfinite(received).all():
        raise ValueError("Non-finite IQ samples detected")

    # Least-squares complex channel-gain estimate.
    gain = np.vdot(clean, received) / np.vdot(clean, clean)

    reconstructed = gain * clean
    residual = received - reconstructed

    signal_power = float(np.mean(np.abs(reconstructed) ** 2))
    noise_power = float(np.mean(np.abs(residual) ** 2))

    if signal_power <= 0 or noise_power <= 0:
        raise ValueError("Invalid estimated signal or noise power")

    return 10 * np.log10(signal_power / noise_power)


def main():
    output_dir = Path("results")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"reference_snr_validation_{timestamp}.csv"

    rows = []

    modulation_indices = {
        modulation: index
        for index, modulation in enumerate(MODULATIONS)
    }

    for modulation in MODULATIONS:
        for repetition in range(REPETITIONS):

            seed = 42000 + modulation_indices[modulation] * 1000 + repetition

            clean, _, _ = generate_waveform(
                modulation,
                SYMBOLS,
                SPS,
                ROLLOFF,
                seed,
            )

            for snr_index, target_snr in enumerate(TARGET_SNRS):
                rng = np.random.default_rng(
                    seed + 100000 + snr_index
                )

                received = add_awgn(clean, target_snr, rng)

                measured = estimate_reference_snr(clean, received)
                error = measured - target_snr

                rows.append({
                    "modulation": modulation,
                    "target_snr_db": target_snr,
                    "measured_snr_db": measured,
                    "error_db": error,
                    "absolute_error_db": abs(error),
                    "seed": seed,
                    "repetition": repetition + 1,
                    "samples": len(clean),
                })

    fields = list(rows[0].keys())

    with output_path.open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print("\n===== REFERENCE SNR VALIDATION =====")
    print("Channel model: Ideal sample-aligned AWGN")
    print("Modulations:", ", ".join(MODULATIONS))
    print("Repetitions per condition:", REPETITIONS)
    print("Total trials:", len(rows))

    print("\nTarget | Mean measured | MAE | RMSE | Max error")

    all_pass = True

    for target in TARGET_SNRS:
        subset = [
            row for row in rows
            if row["target_snr_db"] == target
        ]

        errors = np.array([r["error_db"] for r in subset])
        absolute = np.abs(errors)

        mean_measured = np.mean([
            r["measured_snr_db"] for r in subset
        ])

        mae = float(np.mean(absolute))
        rmse = float(np.sqrt(np.mean(errors ** 2)))
        max_error = float(np.max(absolute))

        passed = max_error <= 0.5
        all_pass &= passed

        print(
            f"{target:5.1f} | "
            f"{mean_measured:12.4f} | "
            f"{mae:.4f} | "
            f"{rmse:.4f} | "
            f"{max_error:.4f} "
            f"{'PASS' if passed else 'FAIL'}"
        )

    print("\nOverall:", "PASS" if all_pass else "FAIL")
    print("Results:", output_path)

    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

