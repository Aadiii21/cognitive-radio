#!/usr/bin/env python3

import csv
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.signal import correlate

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.radio.waveform_generator import generate_waveform


MODULATIONS = ("BPSK", "QPSK", "16QAM")
TARGET_SNRS = (5.0, 10.0, 15.0)

REPETITIONS = 20
SYMBOLS = 65536
SPS = 4
ROLLOFF = 0.35
MAX_DELAY = 256


def estimate_snr_with_timing_sync(reference, received):
    reference = np.asarray(reference, dtype=np.complex128)
    received = np.asarray(received, dtype=np.complex128)

    if len(received) < len(reference):
        raise ValueError("Received buffer is shorter than reference")

    if not np.isfinite(reference).all() or not np.isfinite(received).all():
        raise ValueError("Non-finite IQ samples detected")

    correlation = correlate(
        received,
        reference,
        mode="valid",
        method="fft",
    )

    detected_delay = int(np.argmax(np.abs(correlation)))

    aligned = received[
        detected_delay:detected_delay + len(reference)
    ]

    # Least-squares complex channel-gain estimation.
    gain = np.vdot(reference, aligned) / np.vdot(reference, reference)

    reconstructed = gain * reference
    residual = aligned - reconstructed

    signal_power = float(np.mean(np.abs(reconstructed) ** 2))
    noise_power = float(np.mean(np.abs(residual) ** 2))

    if signal_power <= 0 or noise_power <= 0:
        raise ValueError("Invalid signal or noise power")

    measured_snr = 10.0 * np.log10(signal_power / noise_power)

    return float(measured_snr), detected_delay


def main():
    output_dir = PROJECT_ROOT / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"timing_sync_validation_{timestamp}.csv"

    rows = []

    for mod_index, modulation in enumerate(MODULATIONS):
        for repetition in range(REPETITIONS):

            seed = 52000 + mod_index * 1000 + repetition

            reference, _, _ = generate_waveform(
                modulation,
                SYMBOLS,
                SPS,
                ROLLOFF,
                seed,
            )

            reference = np.asarray(reference, dtype=np.complex128)
            signal_power = float(np.mean(np.abs(reference) ** 2))

            for snr_index, target_snr in enumerate(TARGET_SNRS):

                rng = np.random.default_rng(
                    seed + 200000 + snr_index
                )

                delay = int(rng.integers(0, MAX_DELAY + 1))
                gain_amplitude = float(rng.uniform(0.5, 1.5))
                phase = float(rng.uniform(-np.pi, np.pi))

                gain = gain_amplitude * np.exp(1j * phase)

                # Correct noise power: define SNR after channel gain.
                received_signal_power = (
                    signal_power * gain_amplitude ** 2
                )

                noise_power = (
                    received_signal_power
                    / (10.0 ** (target_snr / 10.0))
                )

                noise = np.sqrt(noise_power / 2.0) * (
                    rng.standard_normal(len(reference) + MAX_DELAY)
                    + 1j * rng.standard_normal(len(reference) + MAX_DELAY)
                )

                received = noise.astype(np.complex128)

                received[
                    delay:delay + len(reference)
                ] += gain * reference

                measured, detected_delay = estimate_snr_with_timing_sync(
                    reference,
                    received,
                )

                error = measured - target_snr

                rows.append({
                    "modulation": modulation,
                    "target_snr_db": target_snr,
                    "measured_snr_db": measured,
                    "error_db": error,
                    "absolute_error_db": abs(error),
                    "actual_delay_samples": delay,
                    "detected_delay_samples": detected_delay,
                    "timing_correct": delay == detected_delay,
                    "gain_amplitude": gain_amplitude,
                    "phase_rad": phase,
                    "repetition": repetition + 1,
                    "seed": seed,
                })

    fields = list(rows[0].keys())

    with output_path.open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print("\n===== TIMING SYNCHRONIZATION VALIDATION =====")
    print("Channel: Timing delay + complex gain + phase + AWGN")
    print("CFO: Not yet introduced")
    print("Total trials:", len(rows))

    print("\nSNR | MAE | RMSE | Max error | Timing errors")

    all_pass = True

    for target in TARGET_SNRS:
        subset = [
            row for row in rows
            if row["target_snr_db"] == target
        ]

        errors = np.array([row["error_db"] for row in subset])
        absolute = np.abs(errors)

        timing_errors = sum(
            not row["timing_correct"] for row in subset
        )

        mae = float(np.mean(absolute))
        rmse = float(np.sqrt(np.mean(errors ** 2)))
        max_error = float(np.max(absolute))

        passed = (
            mae <= 0.1
            and max_error <= 0.5
            and timing_errors == 0
        )

        all_pass &= passed

        print(
            f"{target:4.0f} | {mae:.4f} | {rmse:.4f} | "
            f"{max_error:.4f} | {timing_errors} "
            f"{'PASS' if passed else 'FAIL'}"
        )

    print("\nOverall:", "PASS" if all_pass else "FAIL")
    print("Results:", output_path)

    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
