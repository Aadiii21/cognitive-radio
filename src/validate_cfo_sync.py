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

SAMPLE_RATE = 2_400_000
MAX_DELAY = 256
MAX_CFO_HZ = 2000.0
COARSE_CFO_STEP_HZ = 50.0
PREAMBLE_SAMPLES = 8192
CFO_BLOCK_SIZE = 256


def joint_timing_cfo_acquisition(reference, received):
    """Coarse CFO search combined with known-preamble timing detection."""

    preamble = reference[:PREAMBLE_SAMPLES]
    search_length = len(preamble) + MAX_DELAY

    search_buffer = received[:search_length]
    indices = np.arange(search_length, dtype=np.float64)

    candidates = np.arange(
        -MAX_CFO_HZ,
        MAX_CFO_HZ + COARSE_CFO_STEP_HZ,
        COARSE_CFO_STEP_HZ,
    )

    best_score = -np.inf
    best_delay = None
    best_cfo = None

    for candidate in candidates:
        derotation = np.exp(
            -1j * 2.0 * np.pi * candidate * indices / SAMPLE_RATE
        )

        corrected = search_buffer * derotation

        correlation = correlate(
            corrected,
            preamble,
            mode="valid",
            method="fft",
        )

        delay = int(np.argmax(np.abs(correlation)))
        score = float(np.abs(correlation[delay]))

        if score > best_score:
            best_score = score
            best_delay = delay
            best_cfo = float(candidate)

    return best_delay, best_cfo


def refine_cfo(reference, received, sample_rate):
    """Estimate CFO from the phase slope of block-wise correlations."""

    reference = np.asarray(reference, dtype=np.complex128)
    received = np.asarray(received, dtype=np.complex128)

    if reference.shape != received.shape:
        raise ValueError("Reference and received lengths differ")

    phases = []
    centers = []
    weights = []

    for start in range(0, len(reference) - CFO_BLOCK_SIZE + 1,
                       CFO_BLOCK_SIZE):

        end = start + CFO_BLOCK_SIZE

        ref_block = reference[start:end]
        rx_block = received[start:end]

        correlation = np.vdot(ref_block, rx_block)

        if abs(correlation) < 1e-12:
            continue

        phases.append(np.angle(correlation))
        centers.append(start + (CFO_BLOCK_SIZE - 1) / 2.0)
        weights.append(abs(correlation))

    if len(phases) < 10:
        raise ValueError("Insufficient correlation blocks for CFO estimation")

    phases = np.unwrap(np.asarray(phases))
    centers = np.asarray(centers)
    weights = np.asarray(weights)

    # Weighted linear regression: phase = intercept + slope * sample index.
    slope, intercept = np.polyfit(
        centers,
        phases,
        1,
        w=np.sqrt(weights),
    )

    return float(slope * sample_rate / (2.0 * np.pi))


def estimate_snr(reference, received):
    """Estimate SNR after synchronization and CFO correction."""

    gain = np.vdot(reference, received) / np.vdot(reference, reference)

    reconstructed = gain * reference
    residual = received - reconstructed

    signal_power = float(np.mean(np.abs(reconstructed) ** 2))
    noise_power = float(np.mean(np.abs(residual) ** 2))

    if signal_power <= 0 or noise_power <= 0:
        raise ValueError("Invalid signal or noise power")

    return float(10.0 * np.log10(signal_power / noise_power))


def main():
    output_dir = PROJECT_ROOT / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"cfo_sync_validation_{timestamp}.csv"

    rows = []

    for mod_index, modulation in enumerate(MODULATIONS):
        for repetition in range(REPETITIONS):

            seed = 62000 + mod_index * 1000 + repetition

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
                    seed + 300000 + snr_index
                )

                delay = int(rng.integers(0, MAX_DELAY + 1))
                gain_amplitude = float(rng.uniform(0.5, 1.5))
                phase = float(rng.uniform(-np.pi, np.pi))
                actual_cfo = float(rng.uniform(-MAX_CFO_HZ, MAX_CFO_HZ))

                gain = gain_amplitude * np.exp(1j * phase)

                indices = np.arange(len(reference), dtype=np.float64)

                rotation = np.exp(
                    1j * 2.0 * np.pi * actual_cfo
                    * indices / SAMPLE_RATE
                )

                clean_received = gain * reference * rotation

                received_signal_power = (
                    signal_power * gain_amplitude ** 2
                )

                noise_power = (
                    received_signal_power / (10.0 ** (target_snr / 10.0))
                )

                noise = np.sqrt(noise_power / 2.0) * (
                    rng.standard_normal(len(reference) + MAX_DELAY)
                    + 1j * rng.standard_normal(len(reference) + MAX_DELAY)
                )

                received = noise.astype(np.complex128)

                received[delay:delay + len(reference)] += clean_received

                # Stage 1: Joint coarse timing and CFO acquisition.
                detected_delay, coarse_cfo = joint_timing_cfo_acquisition(
                    reference,
                    received,
                )

                aligned = received[
                    detected_delay:detected_delay + len(reference)
                ]

                # Stage 2: Fine CFO estimation using block correlations.
                fine_cfo = refine_cfo(
                    reference,
                    aligned,
                    SAMPLE_RATE,
                )

                # Stage 3: CFO correction.
                correction = np.exp(
                    -1j * 2.0 * np.pi * fine_cfo
                    * indices / SAMPLE_RATE
                )

                corrected = aligned * correction

                # Stage 4: Reference-based SNR estimation.
                measured_snr = estimate_snr(reference, corrected)

                snr_error = measured_snr - target_snr
                cfo_error = fine_cfo - actual_cfo

                rows.append({
                    "modulation": modulation,
                    "target_snr_db": target_snr,
                    "measured_snr_db": measured_snr,
                    "snr_error_db": snr_error,
                    "absolute_snr_error_db": abs(snr_error),
                    "actual_cfo_hz": actual_cfo,
                    "coarse_cfo_hz": coarse_cfo,
                    "estimated_cfo_hz": fine_cfo,
                    "cfo_error_hz": cfo_error,
                    "absolute_cfo_error_hz": abs(cfo_error),
                    "actual_delay_samples": delay,
                    "detected_delay_samples": detected_delay,
                    "timing_correct": delay == detected_delay,
                    "gain_amplitude": gain_amplitude,
                    "phase_rad": phase,
                    "repetition": repetition + 1,
                    "seed": seed,
                })

    with output_path.open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print("\n===== BLOCK-CORRELATION CFO VALIDATION =====")
    print("Channel: Timing + gain + phase + CFO + AWGN")
    print("CFO range:", f"+/-{MAX_CFO_HZ:.0f} Hz")
    print("Block size:", CFO_BLOCK_SIZE, "samples")
    print("Total trials:", len(rows))

    print(
        "\nSNR | SNR MAE | Max SNR error | "
        "CFO MAE (Hz) | Max CFO error | Timing errors"
    )

    all_pass = True

    for target in TARGET_SNRS:
        subset = [
            row for row in rows
            if row["target_snr_db"] == target
        ]

        snr_errors = np.array([
            row["snr_error_db"] for row in subset
        ])

        cfo_errors = np.array([
            row["cfo_error_hz"] for row in subset
        ])

        timing_errors = sum(
            not row["timing_correct"] for row in subset
        )

        snr_mae = float(np.mean(np.abs(snr_errors)))
        max_snr_error = float(np.max(np.abs(snr_errors)))
        cfo_mae = float(np.mean(np.abs(cfo_errors)))
        max_cfo_error = float(np.max(np.abs(cfo_errors)))

        passed = (
            snr_mae <= 0.1
            and max_snr_error <= 0.5
            and cfo_mae <= 10.0
            and timing_errors == 0
        )

        all_pass &= passed

        print(
            f"{target:4.0f} | {snr_mae:7.4f} | "
            f"{max_snr_error:13.4f} | {cfo_mae:12.4f} | "
            f"{max_cfo_error:14.4f} | {timing_errors} "
            f"{'PASS' if passed else 'FAIL'}"
        )

    print("\nOverall:", "PASS" if all_pass else "FAIL")
    print("Results:", output_path)

    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
