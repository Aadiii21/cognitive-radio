#!/usr/bin/env python3
"""
Sample Rate Offset (SRO) Synchronization Validation

Tests the timing recovery and SNR estimation under controlled sample-rate
mismatch between transmitter and receiver.

Uses the existing reference-based SNR estimator with correlation-based
timing detection to evaluate degradation from SRO.
"""

import csv
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.signal import correlate, resample_poly

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.radio.waveform_generator import generate_waveform


# ============================================================
# Configuration
# ============================================================
MODULATIONS = ("BPSK", "QPSK", "16QAM")
TARGET_SNRS = (5.0, 10.0, 15.0)

REPETITIONS = 20
SYMBOLS = 65536
SPS = 4
ROLLOFF = 0.35
SAMPLE_RATE = 2_400_000
MAX_DELAY = 256

# SRO values in PPM (parts per million)
SRO_PPM_VALUES = (0, 5, 10, 20, 50)


# ============================================================
# Core Functions
# ============================================================
def apply_sro(signal, sro_ppm, rng):
    """
    Apply sample rate offset by resampling.
    
    SRO in PPM means the receiver clock runs at (1 + SRO/1e6) relative
    to transmitter. To simulate this, we resample the signal.
    """
    if sro_ppm == 0:
        return signal
    
    # Resample: up by (1 + SRO/1e6), down by 1
    # This simulates the receiver sampling at a slightly different rate
    rate = 1.0 + sro_ppm / 1_000_000.0
    
    # Use polyphase resampling for precision
    # up/down factors approximate the ratio
    up = 1000000 + int(round(sro_ppm))
    down = 1000000
    
    # Resample
    resampled = resample_poly(signal, up, down)
    
    # Truncate or pad to original length for consistent processing
    if len(resampled) > len(signal):
        resampled = resampled[:len(signal)]
    elif len(resampled) < len(signal):
        pad = np.zeros(len(signal), dtype=signal.dtype)
        pad[:len(resampled)] = resampled
        resampled = pad
    
    return resampled


def add_awgn(clean, target_snr_db, rng):
    """Add AWGN to achieve target SNR."""
    signal_power = float(np.mean(np.abs(clean) ** 2))
    noise_power = signal_power / (10 ** (target_snr_db / 10))

    noise = np.sqrt(noise_power / 2) * (
        rng.standard_normal(len(clean))
        + 1j * rng.standard_normal(len(clean))
    )

    return clean + noise.astype(np.complex64)


def estimate_snr_with_timing_sync(reference, received):
    """Correlation-based timing sync + reference-based SNR estimation."""
    reference = np.asarray(reference, dtype=np.complex128)
    received = np.asarray(received, dtype=np.complex128)

    if len(received) < len(reference):
        raise ValueError("Received buffer is shorter than reference")

    if not np.isfinite(reference).all() or not np.isfinite(received).all():
        raise ValueError("Non-finite IQ samples detected")

    # Correlation-based timing detection
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

    # Least-squares complex channel-gain estimation
    gain = np.vdot(reference, aligned) / np.vdot(reference, reference)

    reconstructed = gain * reference
    residual = aligned - reconstructed

    signal_power = float(np.mean(np.abs(reconstructed) ** 2))
    noise_power = float(np.mean(np.abs(residual) ** 2))

    if signal_power <= 0 or noise_power <= 0:
        raise ValueError("Invalid signal or noise power")

    measured_snr = 10.0 * np.log10(signal_power / noise_power)

    return float(measured_snr), detected_delay, float(np.abs(gain))


def run_sro_validation():
    output_dir = PROJECT_ROOT / "results" / "synchronization"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"sro_validation_{timestamp}.csv"

    rows = []
    total_trials = len(MODULATIONS) * REPETITIONS * len(TARGET_SNRS) * len(SRO_PPM_VALUES)
    trial = 0

    print(f"Running SRO validation: {total_trials} total trials...")

    for mod_index, modulation in enumerate(MODULATIONS):
        for repetition in range(REPETITIONS):
            seed = 72000 + mod_index * 1000 + repetition

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
                for sro_ppm in SRO_PPM_VALUES:
                    trial += 1
                    if trial % 100 == 0:
                        print(f"  Progress: {trial}/{total_trials}")

                    rng = np.random.default_rng(
                        seed + 400000 + snr_index * 10 + SRO_PPM_VALUES.index(sro_ppm)
                    )

                    delay = int(rng.integers(0, MAX_DELAY + 1))
                    gain_amplitude = float(rng.uniform(0.5, 1.5))
                    phase = float(rng.uniform(-np.pi, np.pi))
                    gain = gain_amplitude * np.exp(1j * phase)

                    # Apply channel: timing delay + complex gain
                    clean_received = np.zeros(len(reference) + MAX_DELAY, dtype=np.complex128)
                    clean_received[delay:delay + len(reference)] = gain * reference

                    # Apply SRO
                    clean_received = apply_sro(clean_received, sro_ppm, rng)

                    # Add AWGN at target SNR
                    received_signal_power = signal_power * gain_amplitude ** 2
                    noise_power = received_signal_power / (10.0 ** (target_snr / 10.0))

                    noise = np.sqrt(noise_power / 2.0) * (
                        rng.standard_normal(len(clean_received))
                        + 1j * rng.standard_normal(len(clean_received))
                    )

                    received = clean_received + noise.astype(np.complex128)

                    # Estimate SNR with timing synchronization
                    try:
                        measured_snr, detected_delay, detected_gain = estimate_snr_with_timing_sync(
                            reference, received
                        )
                        snr_error = measured_snr - target_snr
                        timing_correct = (delay == detected_delay)
                    except Exception as e:
                        measured_snr = np.nan
                        snr_error = np.nan
                        detected_delay = -1
                        detected_gain = np.nan
                        timing_correct = False

                    rows.append({
                        "modulation": modulation,
                        "target_snr_db": target_snr,
                        "measured_snr_db": measured_snr if not np.isnan(measured_snr) else "",
                        "snr_error_db": snr_error if not np.isnan(snr_error) else "",
                        "absolute_snr_error_db": abs(snr_error) if not np.isnan(snr_error) else "",
                        "sro_ppm": sro_ppm,
                        "actual_delay_samples": delay,
                        "detected_delay_samples": detected_delay,
                        "timing_correct": timing_correct,
                        "detected_gain_amplitude": detected_gain,
                        "actual_gain_amplitude": gain_amplitude,
                        "phase_rad": phase,
                        "repetition": repetition + 1,
                        "seed": seed,
                    })

    # Write results
    fields = list(rows[0].keys())
    with output_path.open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    print("\n===== SRO VALIDATION SUMMARY =====")
    print(f"Total trials: {len(rows)}")
    print(f"SRO values tested (PPM): {SRO_PPM_VALUES}")

    print("\nSRO (PPM) | Modulation | Target SNR | MAE (dB) | Max Error | Timing Errors")
    all_pass = True

    for sro in SRO_PPM_VALUES:
        sro_rows = [r for r in rows if r["sro_ppm"] == sro]
        for modulation in MODULATIONS:
            mod_rows = [r for r in sro_rows if r["modulation"] == modulation]
            for target in TARGET_SNRS:
                subset = [r for r in mod_rows if r["target_snr_db"] == target]
                if not subset:
                    continue

                valid = [r for r in subset if r["snr_error_db"] != ""]
                if not valid:
                    continue

                errors = np.array([r["snr_error_db"] for r in valid])
                absolute = np.abs(errors)
                timing_errors = sum(not r["timing_correct"] for r in valid)

                mae = float(np.mean(absolute))
                max_error = float(np.max(absolute))

                passed = (mae <= 0.5 and max_error <= 1.0 and timing_errors == 0)
                all_pass &= passed

                print(
                    f"{sro:8d} | {modulation:10s} | {target:9.1f} | "
                    f"{mae:7.4f} | {max_error:9.4f} | {timing_errors:13d} "
                    f"{'PASS' if passed else 'FAIL'}"
                )

    print(f"\nOverall: {'PASS' if all_pass else 'FAIL'}")
    print(f"Results saved to: {output_path}")

    return all_pass


if __name__ == "__main__":
    success = run_sro_validation()
    if not success:
        raise SystemExit(1)